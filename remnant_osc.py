"""
remnant_osc.py — Modulo OSC per Remnant
Invia messaggi OSC a SuperCollider durante la generazione e la riproduzione.

Integrazione in contimbre_explorer.py:
    from remnant_osc import RemnantOSC
    osc = RemnantOSC()
    osc.send_gestures(gestures_data, duration)

Dipendenze:
    pip install python-osc

Protocollo (porta 57121 → SC):
    /remnant/gesture  [gestureIdx(i), category(s), tension(f), azimuth(f)]
    /remnant/event    [instrName(s), t(f), azimuth(f), tension(f), gestureIdx(i), category(s)]
    /remnant/update   [gestureIdx(i), instrName(s), azimuth(f), tension(f)]
    /remnant/param    [key(s), value(f)]
    /remnant/stop     [gestureIdx(i), instrName(s)]
    /remnant/panic
"""

import threading
import time
import math

try:
    from pythonosc import udp_client
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False
    print("[RemnantOSC] python-osc non installato. Installa con: pip install python-osc")


# ─── Mappatura azimuth UMAP-Y → gradi ────────────────────────────────────────

def y_to_azimuth(y: float, y_min: float, y_max: float) -> float:
    """Stessa funzione di contimbre_explorer.py — mantenuta in sync."""
    if y_max == y_min:
        return 180.0
    return round((y - y_min) / (y_max - y_min) * 360.0, 1)


# ─── Classe principale ───────────────────────────────────────────────────────

class RemnantOSC:
    """
    Gestisce la comunicazione OSC tra Remnant (Python/Dash) e SuperCollider.

    Utilizzo base:
        osc = RemnantOSC(host="127.0.0.1", port=57121)
        osc.send_gestures(gestures_data, duration=120)

    Utilizzo con playback schedulato:
        osc.play(gestures_data, start_time=None)  # parte subito
        osc.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 57121):
        self.host   = host
        self.port   = port
        self.client = None
        self._play_thread:  threading.Thread | None = None
        self._stop_event:   threading.Event         = threading.Event()
        self._update_thread: threading.Thread | None = None

        if _OSC_AVAILABLE:
            try:
                self.client = udp_client.SimpleUDPClient(host, port)
                print(f"[RemnantOSC] Client OSC pronto → {host}:{port}")
            except Exception as e:
                print(f"[RemnantOSC] Errore init client: {e}")
        else:
            print("[RemnantOSC] Modalità dry-run (python-osc non disponibile)")

    # ── Invio messaggi base ──────────────────────────────────────────────────

    def _send(self, address: str, *args):
        """Invia un messaggio OSC. No-op se python-osc non è installato."""
        if self.client is None:
            print(f"[OSC dry-run] {address} {list(args)}")
            return
        try:
            self.client.send_message(address, list(args))
        except Exception as e:
            print(f"[RemnantOSC] Errore invio {address}: {e}")

    def panic(self):
        """Ferma immediatamente tutti i synth in SC."""
        self._stop_event.set()
        self._send("/remnant/panic")
        print("[RemnantOSC] PANIC inviato.")

    def send_param(self, key: str, value: float):
        """Aggiorna un parametro globale in SC (es. masterVol, bpm)."""
        self._send("/remnant/param", key, float(value))

    def send_gesture_header(self, gesture_idx: int, category: str,
                             tension: float, azimuth: float):
        """Annuncia un nuovo gesto a SC."""
        self._send("/remnant/gesture",
                   int(gesture_idx), str(category),
                   float(tension), float(azimuth))

    def send_event(self, instr: str, t: float, azimuth: float,
                   tension: float, gesture_idx: int, category: str):
        """Invia un singolo evento sonoro a SC."""
        self._send("/remnant/event",
                   str(instr), float(t), float(azimuth),
                   float(tension), int(gesture_idx), str(category))

    def send_update(self, gesture_idx: int, instr: str,
                    azimuth: float, tension: float):
        """Aggiornamento modulazione continua per un synth attivo."""
        self._send("/remnant/update",
                   int(gesture_idx), str(instr),
                   float(azimuth), float(tension))

    def send_stop(self, gesture_idx: int, instr: str = "*"):
        """Ferma l'elaborazione di uno strumento/gesto."""
        self._send("/remnant/stop", int(gesture_idx), str(instr))

    # ── Invio composizione completa ──────────────────────────────────────────

    def send_gestures(self, gestures_data: list, duration: float,
                      df_y_min: float = 0.0, df_y_max: float = 1.0,
                      bpm: float = 60.0):
        """
        Invia l'intera composizione a SC senza scheduling.
        Utile per pre-caricare i synth prima dell'esecuzione.

        gestures_data: lista di dict dal formato gestures-store di Remnant
        """
        self.send_param("bpm", bpm)

        for g in gestures_data:
            idx      = g.get("index", 0)
            cat      = g.get("lachenmann", "Neutro")
            tension  = float(g.get("tension", 0.5))
            events   = g.get("events_timed", [])

            # Calcola azimuth medio del gesto per l'header
            azimuths = []
            for ev in events:
                sound = ev.get("sound", {})
                y     = float(sound.get("y", 0.5))
                az    = y_to_azimuth(y, df_y_min, df_y_max)
                azimuths.append(az)
            mean_az = sum(azimuths) / len(azimuths) if azimuths else 180.0

            self.send_gesture_header(idx, cat, tension, mean_az)

            for ev in events:
                sound  = ev.get("sound", {})
                instr  = sound.get("instrument", "unknown")
                t      = float(ev.get("t", 0.0))
                y      = float(sound.get("y", 0.5))
                az     = y_to_azimuth(y, df_y_min, df_y_max)
                self.send_event(instr, t, az, tension, idx, cat)

        print(f"[RemnantOSC] Composizione inviata: "
              f"{len(gestures_data)} gesti, {duration:.1f}s")

    # ── Playback schedulato ──────────────────────────────────────────────────

    def play(self, gestures_data: list, df_y_min: float = 0.0,
             df_y_max: float = 1.0, bpm: float = 60.0,
             start_time: float | None = None):
        """
        Esegue la composizione in tempo reale, schedulando ogni evento
        secondo il suo campo 't' (secondi dall'inizio).

        start_time: epoch time assoluto di partenza (None = subito)
        """
        if self._play_thread and self._play_thread.is_alive():
            print("[RemnantOSC] Playback già in corso. Usa stop() prima.")
            return

        self._stop_event.clear()
        t0 = start_time if start_time is not None else time.time()

        self.send_param("bpm", bpm)

        # Raccoglie tutti gli eventi in ordine cronologico
        all_events = []
        for g in gestures_data:
            idx     = g.get("index", 0)
            cat     = g.get("lachenmann", "Neutro")
            tension = float(g.get("tension", 0.5))
            for ev in g.get("events_timed", []):
                sound = ev.get("sound", {})
                all_events.append({
                    "t":       float(ev.get("t", 0.0)),
                    "instr":   sound.get("instrument", "unknown"),
                    "y":       float(sound.get("y", 0.5)),
                    "tension": tension,
                    "idx":     idx,
                    "cat":     cat,
                    "t_end":   float(g.get("t_end", 0.0)),
                })
        all_events.sort(key=lambda e: e["t"])

        def _runner():
            print(f"[RemnantOSC] Playback avviato: "
                  f"{len(all_events)} eventi, t0={t0:.2f}")
            for ev in all_events:
                if self._stop_event.is_set():
                    break
                # Aspetta l'onset
                wait = (t0 + ev["t"]) - time.time()
                if wait > 0:
                    self._stop_event.wait(timeout=wait)
                if self._stop_event.is_set():
                    break

                az = y_to_azimuth(ev["y"], df_y_min, df_y_max)
                self.send_event(
                    ev["instr"], ev["t"], az,
                    ev["tension"], ev["idx"], ev["cat"]
                )

                # Schedula stop alla fine del gesto
                dur = ev["t_end"] - ev["t"]
                if dur > 0:
                    threading.Timer(
                        dur,
                        lambda i=ev["idx"], s=ev["instr"]: self.send_stop(i, s)
                    ).start()

            print("[RemnantOSC] Playback completato.")

        self._play_thread = threading.Thread(target=_runner, daemon=True)
        self._play_thread.start()

    def stop(self):
        """Interrompe il playback schedulato e invia stop a tutti i gesti."""
        self._stop_event.set()
        self._send("/remnant/panic")
        print("[RemnantOSC] Playback fermato.")

    # ── Modulazione continua ─────────────────────────────────────────────────

    def start_continuous_modulation(self, gestures_data: list,
                                     df_y_min: float = 0.0,
                                     df_y_max: float = 1.0,
                                     update_hz: float = 10.0):
        """
        Thread di modulazione continua: aggiorna azimuth/tension dei synth
        attivi a update_hz Hz. Simula il moto browniano come LFO sull'azimuth.
        """
        if self._update_thread and self._update_thread.is_alive():
            return

        interval = 1.0 / max(update_hz, 1.0)

        def _modulate():
            phase = {}
            while not self._stop_event.is_set():
                for g in gestures_data:
                    idx     = g.get("index", 0)
                    cat     = g.get("lachenmann", "Neutro")
                    tension = float(g.get("tension", 0.5))
                    for ev in g.get("events_timed", []):
                        sound = ev.get("sound", {})
                        instr = sound.get("instrument", "unknown")
                        key   = (idx, instr)
                        y     = float(sound.get("y", 0.5))
                        az    = y_to_azimuth(y, df_y_min, df_y_max)

                        # LFO lento sull'azimuth (±15° a bassa tensione, ±5° ad alta)
                        phase[key] = phase.get(key, 0.0) + interval * (0.05 + tension * 0.1)
                        az_mod     = az + math.sin(phase[key]) * (15 * (1 - tension) + 5)
                        az_mod     = az_mod % 360

                        self.send_update(idx, instr, az_mod, tension)

                time.sleep(interval)

        self._update_thread = threading.Thread(target=_modulate, daemon=True)
        self._update_thread.start()
        print(f"[RemnantOSC] Modulazione continua avviata ({update_hz} Hz)")

    def stop_continuous_modulation(self):
        """Ferma il thread di modulazione continua."""
        self._stop_event.set()
        print("[RemnantOSC] Modulazione continua fermata.")


# ─── Integrazione Dash ───────────────────────────────────────────────────────
# Aggiungi queste righe in contimbre_explorer.py:
#
#   from remnant_osc import RemnantOSC
#   osc = RemnantOSC()
#
# Nel callback generate():
#   osc.send_gestures(gestures_serial, duration, df_active["y"].min(), df_active["y"].max())
#
# Aggiungi un bottone "▶ Play OSC" e un bottone "■ Stop":
#
#   @app.callback(
#       Output("osc-status", "children"),
#       Input("osc-play-btn", "n_clicks"),
#       State("gestures-store", "data"),
#       State("duration-slider", "value"),
#       prevent_initial_call=True,
#   )
#   def osc_play(n_clicks, gestures_data, duration):
#       if not gestures_data:
#           return "Genera prima una composizione."
#       osc.play(gestures_data, df_y_min=df_full["y"].min(), df_y_max=df_full["y"].max())
#       return f"▶ OSC play — {len(gestures_data)} gesti"
#
#   @app.callback(
#       Output("osc-status", "children", allow_duplicate=True),
#       Input("osc-stop-btn", "n_clicks"),
#       prevent_initial_call=True,
#   )
#   def osc_stop(n_clicks):
#       osc.stop()
#       return "■ OSC fermato"


# ─── CLI di test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Remnant OSC sender")
    parser.add_argument("--host",  default="127.0.0.1")
    parser.add_argument("--port",  default=57121, type=int)
    parser.add_argument("--score", help="Path a brownian_score.json")
    parser.add_argument("--panic", action="store_true")
    args = parser.parse_args()

    osc = RemnantOSC(args.host, args.port)

    if args.panic:
        osc.panic()

    elif args.score:
        with open(args.score) as f:
            score = json.load(f)

        # Converti dal formato score al formato gestures_data
        gestures_data = []
        for g in score.get("gestures", []):
            events_timed = []
            for ev in g.get("events", []):
                events_timed.append({
                    "t":     ev["t"],
                    "sound": {
                        "instrument": ev["instrument"],
                        "y":          ev["azimuth"] / 360.0,  # inverti azimuth→y
                    },
                })
            gestures_data.append({
                "index":        g["index"],
                "lachenmann":   g.get("lachenmann", "Neutro"),
                "tension":      g.get("tension", 0.5),
                "t_start":      g["t_start"],
                "t_end":        g["t_end"],
                "events_timed": events_timed,
            })

        print(f"Score caricato: {len(gestures_data)} gesti")
        osc.play(gestures_data, bpm=score.get("bpm", 60))

        # Aspetta il completamento
        try:
            while osc._play_thread and osc._play_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            osc.stop()

    else:
        # Test rapido con evento fittizio
        print("Test: invio evento Klang (azimuth=90, tension=0.7)...")
        osc.send_gesture_header(0, "Klang", 0.7, 90.0)
        osc.send_event("violin", 0.0, 90.0, 0.7, 0, "Klang")
        time.sleep(2)
        osc.send_update(0, "violin", 180.0, 0.9)
        time.sleep(1)
        osc.send_stop(0, "violin")
        print("Test completato.")
