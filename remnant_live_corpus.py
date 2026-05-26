"""
remnant_live_corpus.py — Corpus live per Remnant
Riceve nuovi segmenti da SuperCollider via OSC,
stima la trasformazione affine features→UMAP,
aggiorna la mappa in Remnant/Dash in tempo reale.

Integrazione in contimbre_explorer.py:
    from remnant_live_corpus import LiveCorpus
    live_corpus = LiveCorpus(osc_out_port=57121)
    live_corpus.start(df_umap)   # df_umap = DataFrame con colonne x, y

Dipendenze: python-osc, numpy, scikit-learn
"""

import threading
import time
import numpy as np

try:
    from pythonosc import udp_client, dispatcher, osc_server
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False
    print("[LiveCorpus] python-osc non installato.")


class LiveCorpus:
    """
    Gestisce il corpus live in Python:
    - ascolta /remnant/live/new_segment da SC
    - mantiene la lista dei segmenti con coordinate UMAP stimate
    - stima e invia la trasformazione affine features→UMAP a SC
    - invia i limiti UMAP al boot
    - espone i dati per la visualizzazione in Dash

    Utilizzo:
        corpus = LiveCorpus()
        corpus.start(df_umap)
        # ... nel callback Dash:
        segments = corpus.get_segments()
    """

    def __init__(self,
                 sc_host:       str = "127.0.0.1",
                 sc_port:       int = 57121,
                 listen_port:   int = 57122,
                 n_features:    int = 20):

        self.sc_host     = sc_host
        self.sc_port     = sc_port
        self.listen_port = listen_port
        self.n_features  = n_features

        self.client      = None
        self._server     = None
        self._thread     = None
        self._lock       = threading.Lock()

        # Corpus: lista di dict {idx, x, y, t}
        self._segments: list[dict] = []

        # Callback chiamata quando arriva un nuovo segmento
        # firma: callback(idx, x, y)
        self.on_new_segment = None

        if _OSC_AVAILABLE:
            self.client = udp_client.SimpleUDPClient(sc_host, sc_port)
            print(f"[LiveCorpus] OSC client → {sc_host}:{sc_port}")

    # ── Avvio ────────────────────────────────────────────────────────────────

    def start(self, df_umap):
        """
        Avvia il server OSC in ascolto e invia la calibrazione UMAP a SC.
        df_umap: DataFrame con colonne 'x', 'y' (lo spazio UMAP ConTimbre)
        """
        self._calibrate_umap(df_umap)

        if not _OSC_AVAILABLE:
            print("[LiveCorpus] python-osc non disponibile, modalità dry-run.")
            return

        disp = dispatcher.Dispatcher()
        disp.map("/remnant/live/new_segment", self._on_new_segment)
        disp.map("/remnant/live/query_result", self._on_query_result)

        self._server = osc_server.ThreadingOSCUDPServer(
            ("0.0.0.0", self.listen_port), disp
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        print(f"[LiveCorpus] In ascolto su porta {self.listen_port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            print("[LiveCorpus] Server OSC fermato.")

    # ── Calibrazione ─────────────────────────────────────────────────────────

    def _calibrate_umap(self, df_umap):
        """
        Invia i limiti UMAP a SC e stima la trasformazione affine
        features→UMAP tramite regressione lineare sul corpus ConTimbre.
        """
        x_min = float(df_umap["x"].min())
        x_max = float(df_umap["x"].max())
        y_min = float(df_umap["y"].min())
        y_max = float(df_umap["y"].max())

        self.umap_x_min = x_min
        self.umap_x_max = x_max
        self.umap_y_min = y_min
        self.umap_y_max = y_max

        if self.client:
            self.client.send_message(
                "/remnant/live/calibrate",
                [x_min, x_max, y_min, y_max]
            )
            print(f"[LiveCorpus] UMAP calibrato: "
                  f"x=[{x_min:.2f}..{x_max:.2f}] y=[{y_min:.2f}..{y_max:.2f}]")

        # Stima proiezione affine se il DataFrame ha le feature audio
        feature_cols = [
            "spectral_center", "spectral_complexity",
            "pitch", "dynamic_num",
            "duration", "absolute_intensity"
        ]
        available = [c for c in feature_cols if c in df_umap.columns]
        if len(available) >= 2:
            self._estimate_affine_projection(df_umap, available)

    def _estimate_affine_projection(self, df_umap, feature_cols):
        """
        Stima A (2×nFeat), bias (2,), mean (nFeat,), scale (nFeat,)
        con regressione lineare Ridge sul corpus ConTimbre.
        Invia i parametri a SC via /remnant/live/umap_params.
        """
        try:
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import StandardScaler

            X = df_umap[feature_cols].fillna(0).values
            Y = df_umap[["x", "y"]].values

            scaler = StandardScaler()
            X_std  = scaler.fit_transform(X)

            reg = Ridge(alpha=1.0)
            reg.fit(X_std, Y)

            means  = scaler.mean_.tolist()
            scales = scaler.scale_.tolist()
            A0     = reg.coef_[0].tolist()   # pesi per x
            A1     = reg.coef_[1].tolist()   # pesi per y
            bias   = reg.intercept_.tolist()

            # Pad a n_features (SC si aspetta esattamente 20 valori)
            nF = self.n_features
            def _pad(lst): return (lst + [0.0] * nF)[:nF]

            params = _pad(means) + _pad(scales) + _pad(A0) + _pad(A1) + bias

            if self.client:
                self.client.send_message("/remnant/live/umap_params", params)
                print(f"[LiveCorpus] Proiezione affine inviata a SC "
                      f"({len(feature_cols)} features)")

            self._affine = dict(means=means, scales=scales, A0=A0, A1=A1, bias=bias,
                                feature_cols=feature_cols)
        except Exception as e:
            print(f"[LiveCorpus] Stima proiezione fallita: {e}")
            self._affine = None

    # ── OSC handlers ─────────────────────────────────────────────────────────

    def _on_new_segment(self, address, *args):
        """
        Ricevuto da SC quando un nuovo segmento è stato analizzato.
        args: [segIdx(int), x(float), y(float)]
        """
        if len(args) < 3:
            return
        idx = int(args[0])
        x   = float(args[1])
        y   = float(args[2])

        with self._lock:
            # Aggiorna o aggiunge
            existing = next((s for s in self._segments if s["idx"] == idx), None)
            if existing:
                existing.update(x=x, y=y, t=time.time())
            else:
                self._segments.append(dict(idx=idx, x=x, y=y, t=time.time()))

        print(f"[LiveCorpus] Nuovo segmento {idx} → UMAP ({x:.2f}, {y:.2f})")

        if self.on_new_segment:
            self.on_new_segment(idx, x, y)

    def _on_query_result(self, address, *args):
        """
        SC ha scelto 'contimbre' o 'live' per un punto browniano.
        Utile per logging e per aggiornare la UI Dash.
        """
        if not args:
            return
        choice = str(args[0])
        print(f"[LiveCorpus] Query → {choice} {list(args[1:])}")

    # ── API dati ─────────────────────────────────────────────────────────────

    def get_segments(self) -> list[dict]:
        """Restituisce la lista dei segmenti live con coordinate UMAP."""
        with self._lock:
            return list(self._segments)

    def get_count(self) -> int:
        with self._lock:
            return len(self._segments)

    def clear(self):
        with self._lock:
            self._segments.clear()
        if self.client:
            self.client.send_message("/remnant/live/clear", [])
        print("[LiveCorpus] Corpus azzerato.")

    def set_weight(self, weight: float):
        """Imposta il peso live/ConTimbre in SC (0=solo ConTimbre, 1=solo live)."""
        weight = max(0.0, min(1.0, weight))
        if self.client:
            self.client.send_message("/remnant/live/weight", [float(weight)])

    def set_recording(self, on: bool):
        """Attiva/disattiva la registrazione live in SC."""
        if self.client:
            self.client.send_message("/remnant/live/record", [int(on)])
        print(f"[LiveCorpus] Registrazione {'AVVIATA' if on else 'FERMATA'}")

    def play_at(self, x: float, y: float, tension: float, azimuth: float):
        """Richiede a SC il playback ibrido a un punto UMAP."""
        if self.client:
            self.client.send_message(
                "/remnant/live/play",
                [float(x), float(y), float(tension), float(azimuth)]
            )

    # ── Plotly trace per Dash ─────────────────────────────────────────────────

    def get_dash_trace(self) -> dict:
        """
        Restituisce un dict Plotly Scattergl per visualizzare
        i segmenti live sulla mappa UMAP in contimbre_explorer.py.

        Utilizzo nel callback generate():
            live_trace = live_corpus.get_dash_trace()
            if live_trace:
                fig.add_trace(go.Scattergl(**live_trace))
        """
        segs = self.get_segments()
        if not segs:
            return None

        import plotly.graph_objects as go

        xs    = [s["x"] for s in segs]
        ys    = [s["y"] for s in segs]
        texts = [f"live seg {s['idx']}" for s in segs]

        return dict(
            x=xs, y=ys,
            mode="markers",
            marker=dict(
                size=10,
                symbol="diamond",
                color="#FF6B35",
                opacity=0.7,
                line=dict(color="white", width=1.2),
            ),
            text=texts,
            hovertemplate="<b>%{text}</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>",
            name="corpus live",
            legendgroup="live",
        )


# ─── Integrazione Dash — snippet da aggiungere in contimbre_explorer.py ──────
#
# All'inizio del file, dopo gli import:
#
#   from remnant_live_corpus import LiveCorpus
#   from remnant_osc import RemnantOSC
#
#   osc         = RemnantOSC()
#   live_corpus = LiveCorpus()
#
# Dopo che df_full è caricato:
#
#   live_corpus.start(df_full)
#
# Nel layout, aggiungere nel pannello sinistro (dopo _hr()):
#
#   _label("Corpus Live"),
#   html.Div([
#       _btn("● Rec",  "live-rec-btn",  color="#E05C5C"),
#       _btn("■ Stop", "live-stop-btn", outline=True),
#       _btn("Azzera", "live-clear-btn", outline=True),
#   ], style={"display": "flex", "gap": "6px"}),
#   html.Div([
#       html.Span("Live weight", style={"fontFamily":"monospace","fontSize":"10px","color":"#555"}),
#       dcc.Slider(id="live-weight-slider", min=0, max=1, step=0.05, value=0,
#                  marks=None, tooltip={"always_visible": False}),
#   ]),
#   html.Div(id="live-status", style={"fontFamily":"monospace","fontSize":"10px","color":"#E05C5C"}),
#
# Callback:
#
#   @app.callback(
#       Output("live-status","children"),
#       Input("live-rec-btn","n_clicks"),
#       Input("live-stop-btn","n_clicks"),
#       Input("live-clear-btn","n_clicks"),
#       Input("live-weight-slider","value"),
#       prevent_initial_call=True,
#   )
#   def live_controls(rec, stop, clear, weight):
#       ctx = dash.callback_context
#       if not ctx.triggered: raise dash.exceptions.PreventUpdate
#       btn = ctx.triggered[0]["prop_id"]
#       if "live-rec-btn"   in btn: live_corpus.set_recording(True);  return f"● {live_corpus.get_count()} seg"
#       if "live-stop-btn"  in btn: live_corpus.set_recording(False); return f"■ {live_corpus.get_count()} seg"
#       if "live-clear-btn" in btn: live_corpus.clear();               return "azzerato"
#       if "live-weight"    in btn: live_corpus.set_weight(weight);    return f"w={weight:.2f}"
#       raise dash.exceptions.PreventUpdate
#
# Nel callback generate(), aggiungere dopo la costruzione di fig:
#
#   live_trace = live_corpus.get_dash_trace()
#   if live_trace:
#       import plotly.graph_objects as go
#       fig.add_trace(go.Scattergl(**live_trace))


if __name__ == "__main__":
    # Test standalone
    import pandas as pd

    # DataFrame fittizio
    df_test = pd.DataFrame({
        "x": np.random.randn(100),
        "y": np.random.randn(100),
        "spectral_center": np.random.rand(100) * 4000 + 500,
        "spectral_complexity": np.random.rand(100),
        "pitch": np.random.rand(100) * 60 + 40,
        "dynamic_num": np.random.randint(1, 8, 100).astype(float),
    })

    corpus = LiveCorpus()
    corpus.on_new_segment = lambda idx, x, y: print(f"  → callback: seg {idx} ({x:.2f},{y:.2f})")
    corpus.start(df_test)

    print("In ascolto. Premi Ctrl+C per uscire.")
    try:
        while True:
            time.sleep(1)
            if corpus.get_count() > 0:
                print(f"  corpus: {corpus.get_count()} segmenti")
    except KeyboardInterrupt:
        corpus.stop()
