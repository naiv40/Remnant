"""
Remnant — Algorithmic composition and live performance system.
Multiple Brownian motion with stochastic parameter evolution.
Instrument family filter. On-demand UMAP recomputation.
Dependencies: dash, plotly, pandas, numpy, scikit-learn, umap-learn
Launch: python3 contimbre_explorer.py
"""

import re
import json
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import subprocess
import os
from sklearn.preprocessing import StandardScaler
import umap as umap_lib

# ─── Data ───────────────────────────────────────────────────────────────────

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
UMAP_FULL_PATH = os.path.join(BASE_DIR, "umap_full_coords.csv")
UMAP_ORIG_PATH = "/tmp/contimbre_full.tsv"
SBCL_SCRIPT    = "/tmp/gen_brownian.lisp"
SCORE_PATH     = os.path.join(BASE_DIR, "brownian_score.json")
SCORES_DIR     = os.path.join(BASE_DIR, "scores")
os.makedirs(SCORES_DIR, exist_ok=True)

df_full = pd.read_csv(UMAP_FULL_PATH)

# Dataset corrente (modificato dal filtro)
df = df_full.copy()
X_MIN, X_MAX = df["x"].min(), df["x"].max()
Y_MIN, Y_MAX = df["y"].min(), df["y"].max()

ALL_FAMILIES   = sorted(df_full["family"].unique())
ALL_INSTRUMENTS = sorted(df_full["instrument"].unique())

# ─── Thoresen Dynamic Forms (Aural Sonology ch. 8) ──────────────────────────

# Le quattro direzioni temporali di Thoresen.
# Ogni direzione definisce un comportamento del percorso browniano nel piano UMAP:
#   Forward   → drift toward high spectral_center + spectral_complexity zone
#   Backward  → drift toward low spectral_center + spectral_complexity zone
#   Presence  → halved volatility, no directional drift (stability)
#   Neutral   → pure Brownian motion

DYNAMIC_FORM_CATEGORIES = ["Neutral", "Forward", "Backward", "Presence"]

DYNAMIC_FORM_COLORS = {
    "Forward":  "#378ADD",   # blue — rising tension, arrow →
    "Backward": "#E05C5C",   # red — release, arrow ←
    "Presence": "#5CB85C",   # green — stability, circle ○
    "Neutral":  "#888888",   # grey — indeterminate, dash —
}

# Simboli Aural Sonology per la partitura grafica
# Forward  → triangle-right   Backward → triangle-left
# Presence → circle           Neutral  → line-ew (dash)
DYNAMIC_FORM_SYMBOL = {
    "Forward":  ("triangle-right", 9),
    "Backward": ("triangle-left",  9),
    "Presence": ("circle-open",    8),
    "Neutral":  ("line-ew",        8),
}

# Aural Sonology accent functions — computed automatically per event
# release_point   = primo evento del gesto  (★ triangolo su)
# goal_point      = evento a massima tensione (● cerchio pieno)
# termination_pt  = last event of the field    (▼ triangle down)
# warning_point   = penultimo evento se Forward (◇ diamante)
ACCENT_SYMBOL = {
    "release":     ("triangle-up",   10, "#111111"),
    "goal":        ("circle",        11, "#111111"),
    "termination": ("triangle-down", 10, "#111111"),
    "warning":     ("diamond-open",   9, "#444444"),
    "none":        (None,             0, None),
}

def compute_accent_function(ev_idx, n_events, tensions, direction):
    """Return the accent function for event ev_idx.
    goal_point = index of maximum tension.
    warning_point = second-to-last event if direction is Forward.
    Functions are not mutually exclusive: release and goal can coincide
    (first event is also tension peak) — a priority list is returned.
    """
    if n_events == 0:
        return "none"
    goal_idx = int(np.argmax(tensions)) if len(tensions) > 0 else 0

    accents = []
    if ev_idx == 0:
        accents.append("release")
    if ev_idx == n_events - 1:
        accents.append("termination")
    if ev_idx == goal_idx:
        accents.append("goal")
    if direction == "Forward" and ev_idx == n_events - 2 and n_events > 3:
        accents.append("warning")

    if not accents:
        return "none"
    # Priorità: goal > release > termination > warning
    for priority in ("goal", "release", "termination", "warning"):
        if priority in accents:
            return priority
    return "none"


def compute_dynamic_form_attractor(direction, df_active):
    """Return the UMAP attractor point for the given direction.

    Forward  → centroid of upper spectral_center quartile
    Backward → centroid of lower spectral_center quartile
    Presence → None (no attractor, reduced volatility)
    Neutral  → None
    """
    if direction in ("Neutral", "Presence") or "spectral_center" not in df_active.columns:
        return None
    sc = df_active["spectral_center"].fillna(0)
    if direction == "Forward":
        mask = sc >= sc.quantile(0.75)
    else:  # Backward
        mask = sc <= sc.quantile(0.25)
    sub = df_active[mask]
    if len(sub) == 0:
        return None
    return (float(sub["x"].mean()), float(sub["y"].mean()))


def compute_tension_profile(path, df_active, direction):
    """Compute tension for each path step based on direction.

    Forward  → rising tension along the field (t_rel)
    Backward → decreasing tension (1 - t_rel)
    Presence → low, stable tension (~0.2)
    Neutral  → tension from Brownian volatility (distance from previous point)
    """
    n = len(path)
    if n == 0:
        return []
    tensions = []
    for i, (px, py) in enumerate(path):
        t_rel = i / max(n - 1, 1)
        if direction == "Forward":
            base = 0.2 + 0.8 * t_rel
        elif direction == "Backward":
            base = 1.0 - 0.8 * t_rel
        elif direction == "Presence":
            base = 0.15 + 0.1 * np.sin(t_rel * np.pi)
        else:  # Neutral
            if i == 0:
                base = 0.3
            else:
                dx = path[i][0] - path[i-1][0]
                dy = path[i][1] - path[i-1][1]
                dist = np.sqrt(dx**2 + dy**2)
                xrange = df_active["x"].max() - df_active["x"].min() + 1e-6
                base = float(np.clip(dist / (xrange * 0.3), 0.05, 1.0))
        tensions.append(round(base, 3))
    return tensions


# Manteniamo LACHENMANN_MAP e LACHENMANN_COLORS solo per la logica SC legacy
# (SuperCollider synths still use these — to be updated separately)
LACHENMANN_COLORS = {
    "Neutro":    "#888888",
    "Klang":     "#4A90D9",
    "Farbklang": "#5CB85C",
    "Geräusch":  "#E05C5C",
    "Kadenz":    "#BA7517",
    "Textur":    "#9B59B6",
    "Stille":    "#CCCCCC",
}

LACHENMANN_MAP = {
    "horn in f":"Klang","natural horn in a":"Klang","natural horn in b-basso":"Klang",
    "natural horn in bb-alto":"Klang","natural horn in c-alto":"Klang",
    "natural horn in c-basso":"Klang","natural horn in d":"Klang",
    "natural horn in e":"Klang","natural horn in eb":"Klang",
    "natural horn in g":"Klang",
    "bass trombone":"Klang","tenor trombone":"Klang","bass trumpet":"Klang",
    "piccolo trumpet":"Klang","trumpet in c":"Klang","bass tuba":"Klang",
    "piano":"Klang","balaphone":"Klang","glockenspiel":"Klang",
    "lithophone":"Klang","marimbaphone":"Klang","vibraphone":"Klang",
    "bassoon":"Klang","bb clarinet boehm system":"Klang","flute":"Klang",
    "piccolo flute":"Klang","oboe":"Klang","english horn":"Klang",
    "alto saxophone":"Klang","soprano saxophone":"Klang","tenor saxophone":"Klang",
    "baritone saxophone":"Klang","sopranino saxophone":"Klang",
    "violin":"Klang","viola":"Klang","violoncello":"Klang","double bass":"Klang",
    "guitar":"Klang","harp":"Klang","accordion":"Klang",
    "timpani in C":"Klang","timpani in G":"Klang",
    "crotales":"Klang","triangle large":"Klang","triangle medium":"Klang",
    "triangle small":"Klang","tubular bells":"Klang","cow bells":"Klang",
    "flexatone large":"Klang","flexatone small":"Klang","singing saw":"Klang",
    "rin":"Klang","church bell":"Klang","cuckoo birdcall":"Klang",
    "nightengale birdcall":"Klang","udu":"Klang","steel drum":"Klang",
    "log drum":"Klang","baya":"Klang","tabla":"Klang","cuica":"Klang","mokusho":"Klang",
    "contrabass trombone":"Farbklang","alto flute":"Farbklang",
    "baritone oboe":"Farbklang","bass clarinet boehm system":"Farbklang",
    "eb clarinet boehm system":"Farbklang",
    "tubax":"Farbklang","bass flute":"Farbklang","contrabass flute":"Farbklang",
    "contrabass clarinet":"Farbklang","tenor hackbrett":"Farbklang",
    "tamtam":"Farbklang","gong":"Farbklang","bell plates":"Farbklang",
    "marimbula":"Farbklang","ship's bell large":"Farbklang",
    "ship's bell small":"Farbklang","elephant bell":"Farbklang",
    "large kongari":"Farbklang","small kongari":"Farbklang",
    "chinese opera gong large":"Farbklang","chinese opera gong medium":"Farbklang",
    "chinese opera gong small":"Farbklang","furin":"Farbklang",
    "sawblade large":"Farbklang","sawblade small":"Farbklang",
    "water gourd":"Farbklang","car horn large":"Farbklang","car horn small":"Farbklang",
    "metal tube large":"Farbklang","metal tube small":"Farbklang",
    "crash cymbal":"Geräusch","chinese cymbal":"Geräusch","hi-hat":"Geräusch",
    "ride cymbal":"Geräusch","snare drum":"Geräusch","bass drum":"Geräusch",
    "thundersheet large":"Geräusch","thundersheet medium":"Geräusch",
    "thundersheet small":"Geräusch","brake drum":"Geräusch",
    "car spring large":"Geräusch","car spring small":"Geräusch",
    "lion's roar":"Geräusch","frame drum large":"Geräusch",
    "sandblocks coarse grain":"Geräusch","sandblocks fine grain":"Geräusch",
    "guiro bamboo":"Geräusch","wind machine":"Geräusch",
    "wooden ratchet large":"Geräusch","wooden ratchet small":"Geräusch",
    "waldteufel":"Geräusch",
    "claves":"Kadenz","hyoshigi":"Kadenz","whip":"Kadenz",
    "wood block large":"Kadenz","wood block medium":"Kadenz","wood block small":"Kadenz",
    "temple block large":"Kadenz","temple block medium":"Kadenz","temple block small":"Kadenz",
    "bongo large":"Kadenz","bongo small":"Kadenz","conga":"Kadenz",
    "quinto":"Kadenz","tumba":"Kadenz","timbales high":"Kadenz","timbales low":"Kadenz",
    "tomtom":"Kadenz","kick drum":"Kadenz","shime daiko":"Kadenz",
    "darabukka metal":"Kadenz","dombak":"Kadenz","frame drum small":"Kadenz",
    "tambourine european":"Kadenz","hand castanets":"Kadenz",
    "sheep bell":"Kadenz","caxixi large":"Kadenz","caxixi small":"Kadenz",
    "maracas wood large":"Kadenz","maracas wood small":"Kadenz",
    "maracas metal small":"Kadenz","rakatak":"Kadenz",
    "bamboo chimes":"Textur","metal chimes":"Textur","nail chimes":"Textur",
    "paper chimes":"Textur","shell chimes":"Textur",
    "bean rattle large":"Textur","bean rattle small":"Textur",
    "goat hoof rattle":"Textur","heart of palm rattle":"Textur",
    "kola nut rattle":"Textur","rainmaker":"Textur",
    "machine castanets":"Textur","stir drum":"Textur",
}

LACHENMANN_COLORS = {
    "Neutro":    "#888888",
    "Klang":     "#4A90D9",
    "Farbklang": "#5CB85C",
    "Geräusch":  "#E05C5C",
    "Kadenz":    "#BA7517",
    "Textur":    "#9B59B6",
    "Stille":    "#CCCCCC",
}

# LACHENMANN_CATEGORIES kept for SC backwards compatibility
LACHENMANN_CATEGORIES = ["Neutro", "Klang", "Farbklang", "Geräusch", "Kadenz", "Textur", "Stille"]

FAMILY_COLORS = {
    fam: color for fam, color in zip(
        ALL_FAMILIES,
        ["#4A90D9","#E05C5C","#5CB85C","#F0A500","#9B59B6",
         "#1ABC9C","#E67E22","#34495E","#E91E63","#00BCD4",
         "#8BC34A","#FF5722","#607D8B","#795548","#FFC107",
         "#3F51B5","#009688","#F44336","#673AB7","#2196F3",
         "#4CAF50","#FF9800","#9E9E9E"]
    )
}

DIR_ABBREV = {
    "Forward":  "Fwd →",
    "Backward": "Bwd ←",
    "Presence": "Pres ○",
    "Neutral":  "Neu —",
}

GESTURE_PALETTE = [
    "#E24B4A","#378ADD","#1D9E75","#BA7517","#7F77DD",
    "#D85A30","#185FA5","#0F6E56","#854F0B","#534AB7",
    "#993C1D","#0C447C","#085041","#633806","#3C3489",
]

# ─── App ────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, title="Remnant",
                suppress_callback_exceptions=True)


def _slider_block(label, sid, min_val, max_val, step, value):
    return html.Div([
        html.Div([
            html.Span(label, style={"fontFamily": "monospace", "fontSize": "11px", "color": "#555"}),
            html.Span(id=f"{sid}-display", children=str(value),
                      style={"fontFamily": "monospace", "fontSize": "11px", "color": "#111", "fontWeight": "bold"}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"}),
        dcc.Slider(id=sid, min=min_val, max=max_val, step=step, value=value,
                   marks=None, tooltip={"always_visible": False}),
    ], style={"marginBottom": "18px"})


def _label(text):
    return html.Div(text, style={
        "fontFamily": "monospace", "fontSize": "10px", "letterSpacing": "3px",
        "color": "#aaa", "textTransform": "uppercase", "marginBottom": "12px",
    })


def _btn(label, bid, outline=False, color=None):
    bg = color if color else ("#fff" if outline else "#111")
    fg = "#fff" if (color or not outline) else "#111"
    return html.Button(label, id=bid, n_clicks=0, style={
        "width": "100%", "padding": "11px",
        "background": bg, "color": fg,
        "border": f"1px solid {color or '#111'}",
        "fontFamily": "monospace", "fontSize": "10px", "letterSpacing": "2px",
        "textTransform": "uppercase", "cursor": "pointer", "marginBottom": "10px",
    })


def _hr():
    return html.Hr(style={"border": "none", "borderTop": "1px solid #e8e8e8", "margin": "18px 0"})


# Costruisci pannello filtri famiglie/strumenti
def _filter_panel():
    family_checks = []
    for fam in ALL_FAMILIES:
        instruments = sorted(df_full[df_full["family"] == fam]["instrument"].unique())
        color = FAMILY_COLORS.get(fam, "#ccc")
        family_checks.append(html.Div([
            # Checkbox famiglia
            html.Div([
                dcc.Checklist(
                    id=f"fam-{fam.replace(' ', '_')}",
                    options=[{"label": "", "value": fam}],
                    value=[fam],
                    style={"display": "inline-block", "marginRight": "6px"},
                    inputStyle={"accentColor": color},
                ),
                html.Span(fam, style={
                    "fontFamily": "monospace", "fontSize": "10px",
                    "color": color, "fontWeight": "bold", "cursor": "pointer",
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),
            # Strumenti della famiglia (collassabili)
            html.Div([
                dcc.Checklist(
                    id=f"instr-{fam.replace(' ', '_')}",
                    options=[{"label": i, "value": i} for i in instruments],
                    value=instruments,
                    labelStyle={"display": "block", "fontFamily": "monospace",
                                "fontSize": "9px", "color": "#555", "marginBottom": "2px"},
                    inputStyle={"marginRight": "5px", "accentColor": color},
                ),
            ], style={"paddingLeft": "20px", "marginBottom": "8px"}),
        ]))
    return family_checks


family_filter_ids = [f"fam-{f.replace(' ', '_')}" for f in ALL_FAMILIES]
instr_filter_ids  = [f"instr-{f.replace(' ', '_')}" for f in ALL_FAMILIES]


# app.layout is set after home_layout() and score_layout() are defined below


# Layout homepage
def home_layout():
    return html.Div([

    html.Div([
        html.Div("", style={"fontFamily": "monospace", "fontSize": "10px",
                                     "letterSpacing": "4px", "color": "#aaa", "marginBottom": "4px"}),
        html.H1("Remnant", style={"fontFamily": "Georgia, serif", "fontSize": "26px",
                                             "fontWeight": "400", "color": "#111", "margin": "0"}),
    ], style={"padding": "28px 40px 16px", "borderBottom": "1px solid #e8e8e8"}),

    html.Div([

        # ── Left panel ──
        html.Div([

            # Filtri strumenti
            _label("Instruments"),
            html.Div(_filter_panel(), style={"maxHeight": "320px", "overflowY": "auto",
                                              "marginBottom": "12px"}),
            _btn("Apply filter", "filter-btn", color="#378ADD"),
            html.Div(id="filter-status", style={
                "fontFamily": "monospace", "fontSize": "10px",
                "color": "#378ADD", "minHeight": "14px", "marginBottom": "8px",
            }),

            _hr(),

            # Parametri compositivi
            _label("Compositional form"),
            _slider_block("Duration (sec)", "duration-slider", 4, 30, 1, 10),
            _slider_block("Number of fields", "gestures-slider", 1, 15, 1, 4),

            _hr(),

            _label("Initial parameters"),
            _slider_block("Brownian steps", "steps-slider", 4, 32, 1, 12),
            _slider_block("Initial volatility", "volatility-slider", 0.5, 10.0, 0.5, 3.0),
            _slider_block("Stochastic drift", "drift-noise-slider", 0.0, 2.0, 0.1, 0.5),
            _slider_block("Distance threshold (Lerdahl)", "threshold-slider", 0.0, 5.0, 0.1, 0.0),
            _slider_block("Spectral diversity", "spectral-div-slider", 0.0, 0.5, 0.01, 0.15),

            _hr(),

            _label("Temporal direction"),
            html.Div(id="dynamic-form-dropdowns", style={"marginBottom": "12px"}),
            _slider_block("Attraction intensity", "attraction-slider", 0.0, 1.0, 0.05, 0.35),

            _hr(),

            _btn("Generate composition", "generate-btn"),
            _btn("Export for Orchestrator", "export-btn", outline=True),
            _btn("Export for ePlayer", "eplayer-btn", outline=True),
            html.Div(id="eplayer-status", style={
                "fontFamily": "monospace", "fontSize": "10px",
                "color": "#5CB85C", "minHeight": "14px", "marginBottom": "4px",
            }),
            _btn("Generate score", "score-btn", outline=True),
            html.Div(id="score-status", style={
                "fontFamily": "monospace", "fontSize": "10px",
                "color": "#378ADD", "minHeight": "14px", "marginBottom": "4px",
            }),
            html.Div(id="export-status", style={
                "fontFamily": "monospace", "fontSize": "10px",
                "color": "#5CB85C", "minHeight": "16px", "marginBottom": "16px",
            }),

            _hr(),

            _label("Saved scores"),
            dcc.Dropdown(
                id="score-dropdown",
                options=[],
                placeholder="select a score…",
                clearable=True,
                style={"fontFamily": "monospace", "fontSize": "9px", "marginBottom": "8px"},
            ),
            html.Div([
                html.Button("↓ Load", id="score-load-btn", n_clicks=0, style={
                    "width": "48%", "padding": "8px",
                    "background": "none", "color": "#111",
                    "border": "1px solid #111",
                    "fontFamily": "monospace", "fontSize": "9px",
                    "letterSpacing": "1px", "cursor": "pointer",
                }),
                html.Button("↑ Save as…", id="score-save-btn", n_clicks=0, style={
                    "width": "48%", "padding": "8px", "marginLeft": "4%",
                    "background": "none", "color": "#111",
                    "border": "1px solid #111",
                    "fontFamily": "monospace", "fontSize": "9px",
                    "letterSpacing": "1px", "cursor": "pointer",
                }),
            ], style={"display": "flex", "marginBottom": "6px"}),
            dcc.Input(
                id="score-name-input",
                type="text",
                placeholder="score name (enter to save)",
                debounce=True,
                style={
                    "width": "100%", "padding": "6px 8px",
                    "fontFamily": "monospace", "fontSize": "9px",
                    "border": "1px solid #ddd", "marginBottom": "6px",
                    "display": "none",
                },
            ),
            html.Div(id="score-store-status", style={
                "fontFamily": "monospace", "fontSize": "10px",
                "color": "#5CB85C", "minHeight": "14px", "marginBottom": "4px",
            }),

            _hr(),

            _label("Fields"),
            html.Div(id="gesture-info", style={"maxHeight": "180px", "overflowY": "auto"}),

            _hr(),

            _label("Sequence"),
            html.Div(id="sequence-list", style={"maxHeight": "180px", "overflowY": "auto"}),

        ], style={
            "width": "280px", "flexShrink": "0",
            "padding": "24px 20px 24px 40px",
            "borderRight": "1px solid #e8e8e8",
            "overflowY": "auto",
        }),

        # ── Map + timeline ──
        html.Div([
            dcc.Graph(id="umap-graph", config={"displayModeBar": False},
                      style={"height": "calc(100% - 90px)"}),
            html.Div(id="timeline", style={
                "height": "70px", "margin": "8px 16px 0",
                "borderTop": "1px solid #e8e8e8", "paddingTop": "8px",
                "position": "relative",
            }),
        ], style={"flex": "1", "padding": "16px 16px 0", "overflow": "hidden"}),

    ], style={"display": "flex", "height": "calc(100vh - 96px)"}),

    ], style={"fontFamily": "Georgia, serif", "background": "#fafafa", "minHeight": "100vh"})


# Layout pagina partitura
def score_layout(gesture_idx, fig, status):
    return html.Div([
        html.Div([
            dcc.Link("← Remnant", href="/",
                   style={"fontFamily": "monospace", "fontSize": "10px",
                          "color": "#378ADD", "textDecoration": "none",
                          "letterSpacing": "1px"}),
            html.Span("  ·  ", style={"color": "#ccc"}),
            html.Span(f"Partitura — Field {gesture_idx + 1}",
                      style={"fontFamily": "Georgia, serif", "fontSize": "18px",
                             "color": "#111", "fontWeight": "400"}),
        ], style={"padding": "20px 40px 14px", "borderBottom": "1px solid #e8e8e8",
                  "display": "flex", "alignItems": "center", "gap": "16px"}),
        html.Div(status, style={
            "fontFamily": "monospace", "fontSize": "9px",
            "color": "#aaa", "padding": "6px 40px",
        }),
        dcc.Graph(
            id="score-graph",
            figure=fig,
            config={"displayModeBar": True,
                    "toImageButtonOptions": {
                        "format": "png", "filename": f"partitura_g{gesture_idx+1}",
                        "height": 700, "width": 1600, "scale": 2,
                    }},
            style={"height": "calc(100vh - 80px)"},
        ),
    ], style={"background": "#fafafa", "minHeight": "100vh"})


# ─── Logic ──────────────────────────────────────────────────────────────────

# app.layout: tutti i componenti sono sempre nel DOM.
# Il routing mostra/nasconde home-page e score-page via CSS display.
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="path-store"),
    dcc.Store(id="df-store"),
    dcc.Store(id="gestures-store"),
    dcc.Store(id="dynamic-form-store", data={}),
    dcc.Store(id="selected-gesture", data=0),
    dcc.Store(id="score-gesture-idx", data=0),
    dcc.Store(id="score-ready", data=False),
    # Bottone trigger nel root per generate_score
    html.Button(id="score-btn-root", n_clicks=0,
                style={"display": "none"}),

    # Homepage — always in DOM, visible by default
    html.Div(id="home-page", children=home_layout().children,
             style={"fontFamily": "Georgia, serif", "background": "#fafafa",
                    "minHeight": "100vh", "display": "block"}),

    # Score page — always in DOM, hidden by default
    html.Div(id="score-page",
             children=[
                 # Header
                 html.Div([
                     dcc.Link("← Remnant", href="/",
                              style={"fontFamily": "monospace", "fontSize": "10px",
                                     "color": "#378ADD", "textDecoration": "none",
                                     "letterSpacing": "1px"}),
                     html.Span("  ·  ", style={"color": "#ccc"}),
                     html.Span(id="score-title",
                               style={"fontFamily": "Georgia, serif", "fontSize": "18px",
                                      "color": "#111", "fontWeight": "400"}),
                     html.Span("  ·  ", style={"color": "#ccc", "marginLeft": "auto"}),

                 ], style={"padding": "16px 40px 12px", "borderBottom": "1px solid #e8e8e8",
                           "display": "flex", "alignItems": "center", "gap": "12px"}),

                 html.Div(id="score-status-page", style={
                     "fontFamily": "monospace", "fontSize": "9px",
                     "color": "#aaa", "padding": "4px 40px",
                 }),

                 # Partitura a schermo intero
                 dcc.Graph(id="score-graph",
                           figure=go.Figure(layout=dict(
                               paper_bgcolor="white", plot_bgcolor="white",
                               margin=dict(l=0,r=0,t=0,b=0))),
                           config={"displayModeBar": True,
                                   "scrollZoom": True,
                                   "toImageButtonOptions": {
                                       "format": "png", "filename": "partitura",
                                       "height": 700, "width": 1600, "scale": 2}},
                           style={"height": "calc(100vh - 80px)"}),

             ],
             style={"display": "none", "background": "white", "minHeight": "100vh"}),

], style={"fontFamily": "Georgia, serif", "background": "#fafafa", "minHeight": "100vh"})

def recompute_umap(df_subset):
    """Recompute UMAP on a corpus subset."""
    dynamic_map = {"ppp":1,"pp":2,"p":3,"mp":4,"mf":5,"f":6,"ff":7,"fff":8}
    df_subset = df_subset.copy()
    df_subset["dynamic_num"] = df_subset["dynamic"].map(dynamic_map).fillna(0)

    features = ["pitch", "dynamic_num", "spectral_complexity", "spectral_center"]
    # Usa solo le colonne disponibili nel CSV UMAP
    available = [c for c in features if c in df_subset.columns]

    if len(df_subset) < 10:
        return df_subset

    X = df_subset[available].fillna(0).values
    X_std = StandardScaler().fit_transform(X)

    # Ponderazione McAdams — stessa di umap_full.py
    weight_map = {"pitch": 1.5, "dynamic_num": 1.0,
                  "spectral_complexity": 2.0, "spectral_center": 3.0}
    weights = np.array([weight_map.get(c, 1.0) for c in available])
    X_std = X_std * weights

    n_neighbors = min(8, len(df_subset) - 1)
    embedding = umap_lib.UMAP(n_components=2, n_neighbors=n_neighbors,
                               min_dist=0.1, random_state=42).fit_transform(X_std)
    df_subset["x"] = embedding[:, 0]
    df_subset["y"] = embedding[:, 1]
    return df_subset


def stochastic_params(prev_vol, prev_dx, prev_dy, drift_noise):
    new_vol = np.clip(prev_vol + drift_noise * np.random.uniform(-1, 1), 0.5, 10.0)
    new_dx  = np.clip(prev_dx  + drift_noise * np.random.uniform(-1, 1) * 0.5, -2.0, 2.0)
    new_dy  = np.clip(prev_dy  + drift_noise * np.random.uniform(-1, 1) * 0.5, -2.0, 2.0)
    return new_vol, new_dx, new_dy


def brownian_path(steps, volatility, drift_x, drift_y, xmin, xmax, ymin, ymax,
                  start=None, attractor=None, attraction=0.35):
    if start is None:
        x = np.random.uniform(xmin, xmax)
        y = np.random.uniform(ymin, ymax)
    else:
        x, y = start
    path = [(x, y)]
    for _ in range(steps - 1):
        adx, ady = 0.0, 0.0
        if attractor is not None:
            ax, ay = attractor
            adx = (ax - x) * attraction
            ady = (ay - y) * attraction
        nx = np.clip(x + drift_x + adx + volatility * np.random.uniform(-1, 1), xmin, xmax)
        ny = np.clip(y + drift_y + ady + volatility * np.random.uniform(-1, 1), ymin, ymax)
        x, y = nx, ny
        path.append((x, y))
    return path


def nearest_sound(px, py, df_active):
    dists = (df_active["x"] - px)**2 + (df_active["y"] - py)**2
    return df_active.iloc[dists.idxmin()]


def tension_level(vol, xmin, xmax, ymin, ymax):
    """Map volatility to a tension scale 0-1 (Lerdahl).
    High volatility = high timbral tension."""
    vol_range = 10.0 - 0.5
    return round((vol - 0.5) / vol_range, 2)


def path_to_sequence(path, df_active, threshold=0.0, spectral_diversity=0.15,
                     global_seen=None):
    """Convert a Brownian path to a sequence of sounds.

    If threshold > 0 (Lerdahl): select sound only if distance
    from Brownian point is below threshold, otherwise skip
    producing timbral rarefaction/pause.

    spectral_diversity: minimum fractional difference in spectral_center
    required between consecutive selected sounds, as a fraction of the
    total spectral_center range. E.g. 0.15 = next sound must differ by
    at least 15% of the range. Set to 0.0 to disable.
    """
    seen        = set()
    global_seen = global_seen or set()
    seq         = []
    last_sc     = None

    has_sc   = "spectral_center" in df_active.columns
    sc_range = float(df_active["spectral_center"].max()
                     - df_active["spectral_center"].min()) if has_sc else 1.0
    sc_range    = max(sc_range, 1.0)
    min_sc_diff = spectral_diversity * sc_range

    for px, py in path:
        dists    = (df_active["x"] - px)**2 + (df_active["y"] - py)**2
        min_dist = np.sqrt(dists.min())

        if threshold > 0 and min_dist > threshold:
            seq.append(None)
            continue

        # Ordina per distanza UMAP crescente
        df_r       = df_active.reset_index(drop=True)
        sorted_idx = dists.argsort()
        selected = None
        for idx in sorted_idx:
            candidate = df_r.iloc[idx]
            sid = candidate["id"]
            if sid in seen:
                continue
            if sid in global_seen:
                continue
            if has_sc and last_sc is not None and min_sc_diff > 0:
                sc_diff = abs(float(candidate["spectral_center"]) - last_sc)
                if sc_diff < min_sc_diff:
                    continue
            selected = candidate
            break

        if selected is not None:
            seen.add(selected["id"])
            last_sc = float(selected["spectral_center"]) if has_sc else None
            seq.append(selected)
        else:
            seq.append(None)

    # Rimuovi None finali ma mantieni quelli interni (pause timbriche)
    while seq and seq[-1] is None:
        seq.pop()
    # Aggiorna global_seen con i suoni selezionati in questo field
    for s in seq:
        if s is not None:
            global_seen.add(s["id"])
    return seq


def generate_composition(n_gestures, steps, init_vol, drift_noise, duration_sec,
                         df_active, threshold=0.0, dynamic_form_sequence=None,
                         attraction=0.35, spectral_diversity=0.15):
    """Generate composition using Dynamic Forms (Thoresen ch. 8) as directional engine.

    For each field:
    - Direction (Forward/Backward/Presence/Neutral) determines the UMAP attractor
    - Presence halves Brownian volatility
    - Tension profile is computed from direction (not just volatility)
    """
    gestures    = []
    global_seen = set()   # suoni già usati in field precedenti (diversità inter-field)
    vol, dx, dy = init_vol, 0.0, 0.0
    start = None
    xmin, xmax = df_active["x"].min(), df_active["x"].max()
    ymin, ymax = df_active["y"].min(), df_active["y"].max()
    gesture_duration = duration_sec / n_gestures

    for i in range(n_gestures):
        direction = "Neutral"
        if dynamic_form_sequence and i < len(dynamic_form_sequence):
            direction = dynamic_form_sequence[i] or "Neutral"

        # Presence → halved volatility
        eff_vol = vol * 0.5 if direction == "Presence" else vol

        # Attractor UMAP dalla direzione
        attractor = compute_dynamic_form_attractor(direction, df_active)

        path = brownian_path(steps, eff_vol, dx, dy, xmin, xmax, ymin, ymax,
                             start=start, attractor=attractor, attraction=attraction)

        # Profilo di tensione per-passo dalla direzione
        tension_profile = compute_tension_profile(path, df_active, direction)
        # Tensione globale del gesto = media del profilo
        tension = round(float(np.mean(tension_profile)), 2)

        seq       = path_to_sequence(path, df_active, threshold=threshold,
                                     spectral_diversity=spectral_diversity,
                                     global_seen=global_seen)
        real_sounds = [s for s in seq if s is not None]

        # Brownian temporal distribution — Euclidean distances between steps
        dists = [0.0]
        for k in range(1, len(path)):
            ddx = path[k][0] - path[k-1][0]
            ddy = path[k][1] - path[k-1][1]
            dists.append(np.sqrt(ddx**2 + ddy**2))
        cum = np.cumsum(dists)
        total_dist = cum[-1] if cum[-1] > 0 else 1.0

        t_start = round(i * gesture_duration, 2)
        t_end   = round(t_start + gesture_duration, 2)

        # Mappa i suoni reali ai passi del percorso browniano
        real_path_indices = [j for j, s in enumerate(seq) if s is not None]
        events_timed = []
        ev_tensions = []
        for j, (sound, path_idx) in enumerate(zip(real_sounds, real_path_indices)):
            t_frac = float(cum[path_idx] / total_dist)
            t_ev   = round(t_start + t_frac * gesture_duration, 2)
            ev_t   = tension_profile[path_idx] if path_idx < len(tension_profile) else tension
            ev_tensions.append(ev_t)
            events_timed.append({"t": t_ev, "sound": sound, "gesture_idx": i,
                                  "tension": ev_t})

        # Funzioni d'accento per ogni evento
        for j, ev in enumerate(events_timed):
            ev["accent"] = compute_accent_function(j, len(events_timed), ev_tensions, direction)

        # Inter-step Euclidean distances for the pulse grid
        # dists[0] = 0 (initial position), dists[1..n] = distances between steps
        step_dists = [float(dists[k]) for k in range(len(dists))]

        gestures.append({
            "index":          i,
            "path":           path,
            "sequence":       real_sounds,
            "vol":            round(eff_vol, 2),
            "dx":             round(dx, 2),
            "dy":             round(dy, 2),
            "tension":        tension,
            "tension_profile": tension_profile,
            "t_start":        t_start,
            "t_end":          t_end,
            "duration":       round(gesture_duration, 2),
            "density":        len(real_sounds),
            "events_timed":   events_timed,
            "dynamic_form":   direction,
            "step_dists":     step_dists,   # distanze browniane per griglia pulsazione
            # keep lachenmann key for SC legacy compatibility
            "lachenmann":     "Neutro",
        })
        start = path[-1]
        vol, dx, dy = stochastic_params(vol, dx, dy, drift_noise)
    return gestures



# ─── Score ───────────────────────────────────────────────────────────────────

def y_to_azimuth(y, y_min, y_max):
    """Map UMAP Y coordinate to azimuthal angle 0-360."""
    if y_max == y_min:
        return 180.0
    return round((y - y_min) / (y_max - y_min) * 360.0, 1)


# Standard 8-channel octophonic mapping (ITU-R BS.775)
OCTO_CHANNELS = [
    (0,   1),   # CH1 — frontale centro
    (45,  2),   # CH2 — frontale destra
    (90,  3),   # CH3 — laterale destra
    (135, 4),   # CH4 — posteriore destra
    (180, 5),   # CH5 — posteriore centro
    (225, 6),   # CH6 — posteriore sinistra
    (270, 7),   # CH7 — laterale sinistra
    (315, 8),   # CH8 — frontale sinistra
]

def azimuth_to_channel(az):
    """Return (ch_a, ch_b, alpha) for panning between two adjacent channels.
    alpha = weight on ch_b (0.0 = all ch_a, 1.0 = all ch_b).
    """
    az = az % 360
    for i in range(len(OCTO_CHANNELS)):
        a0, c0 = OCTO_CHANNELS[i]
        a1, c1 = OCTO_CHANNELS[(i+1) % len(OCTO_CHANNELS)]
        span = (a1 - a0) % 360
        diff  = (az - a0) % 360
        if diff <= span:
            alpha = round(diff / span, 3) if span > 0 else 0.0
            return c0, c1, alpha
    return 1, 1, 0.0

def channel_label(az):
    """Return a readable string e.g. 'CH4 · CH5 (50%)'."""
    c0, c1, alpha = azimuth_to_channel(az)
    if alpha == 0.0:
        return f"CH{c0}"
    elif alpha == 1.0:
        return f"CH{c1}"
    else:
        pct = int(alpha * 100)
        return f"CH{c0}›CH{c1} {pct}%"



    """Chiama SBCL per risolvere il testo del modo per ogni sound_id.
    Restituisce dict {id: mode_text}.
    """
    import subprocess, tempfile, json as _json
    if not sound_ids:
        return {}

    id_list = " ".join(f'"{sid}"' for sid in missing)
    lisp_script = f"""
(ql:quickload '(:cl-ppcre :parse-float) :silent t)
(defvar conTimbreDir "/Volumes/disk 1/conTimbre Standard V2")
(load (format nil "~A/algorithmic orchestration/contimbre_library.lisp" conTimbreDir))
(in-package :contimbre)

(defun escape-json (s)
  (with-output-to-string (out)
    (loop for c across s do
      (cond ((char= c #\\\\) (write-string "\\\\\\\\" out))
            ((char= c #\\") (write-string "\\\\\\"" out))
            (t (write-char c out))))))

(let* ((ids '({id_list}))
       (result (list)))
  (dolist (id ids)
    (let* ((sound (find id contimbre:contimbre
                        :test #'string=
                        :key  (lambda (s) (contimbre:get_value s "filename_short"))))
           (mode-text ""))
      (when sound
        (let* ((kg (contimbre:find_keygroup_of_contimbre_sound sound))
               (mi (when kg (contimbre:eplayer_key-modes_index kg)))
               (instr (when kg (contimbre:eplayer_key-model kg)))
               (modes (when (and instr mi)
                        (contimbre:eplayer_get_all_modes_of_instrument instr)))
               (mode-list (when (and modes (< mi (length modes)))
                            (nth mi modes))))
          (when mode-list
            (setf mode-text
                  (reduce (lambda (a b) (format nil "~A ~A" a b))
                          mode-list)))))
      (push (format nil "\\"~A\\": \\"~A\\"" (escape-json id) (escape-json mode-text))
            result)))
  (format t "MODES-OK {{~{{~A~^, ~}}}}~%" (nreverse result)))

(sb-ext:exit)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lisp", delete=False) as f:
        f.write(lisp_script)
        tmp = f.name

    try:
        res = subprocess.run(["sbcl", "--load", tmp],
                             capture_output=True, text=True, timeout=300)
        os.unlink(tmp)
    except Exception:
        return {}

    # Estrai il JSON dalla riga MODES-OK
    import re as _re
    m = _re.search(r'MODES-OK (\{.*\})', res.stdout, _re.DOTALL)
    if not m:
        # SBCL fallito: restituisce almeno i valori in cache
        return {sid: cache.get(sid, "") for sid in sound_ids}
    try:
        new_modes = _json.loads(m.group(1))
    except Exception:
        return {sid: cache.get(sid, "") for sid in sound_ids}

    # Aggiorna cache con i nuovi risultati e salva
    cache.update(new_modes)
    _save_modes_cache(cache)

    return {sid: cache.get(sid, "") for sid in sound_ids}


# Cache dei modi: evita chiamate SBCL ripetute.
# File: scores/modes_cache.json — chiave = sound_id, valore = mode_text.
MODES_CACHE_PATH = os.path.join(BASE_DIR, "scores", "modes_cache.json")

def _load_modes_cache():
    try:
        with open(MODES_CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_modes_cache(cache):
    os.makedirs(os.path.dirname(MODES_CACHE_PATH), exist_ok=True)
    try:
        with open(MODES_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass

def resolve_modes_via_sbcl(sound_ids):
    """Call SBCL only for ids not yet in cache.
    Return dict {id: mode_text} (cache union + new results).
    """
    import subprocess, tempfile, json as _json
    if not sound_ids:
        return {}

    cache    = _load_modes_cache()
    missing  = [sid for sid in sound_ids if sid not in cache]

    if not missing:
        return {sid: cache[sid] for sid in sound_ids}

    id_list = " ".join(f'"{sid}"' for sid in sound_ids)
    lisp_script = f"""
(ql:quickload '(:cl-ppcre :parse-float) :silent t)
(defvar conTimbreDir "/Volumes/disk 1/conTimbre Standard V2")
(load (format nil "~A/algorithmic orchestration/contimbre_library.lisp" conTimbreDir))
(in-package :contimbre)

(defun escape-json (s)
  (with-output-to-string (out)
    (loop for c across (or s "") do
      (cond ((char= c #\\\\) (write-string "\\\\\\\\" out))
            ((char= c #\\") (write-string "\\\\\\"" out))
            (t (write-char c out))))))

(let* ((ids '({id_list}))
       (pairs (list)))
  (dolist (id ids)
    (let* ((sound (find id contimbre:contimbre
                        :test #'string=
                        :key  (lambda (s) (contimbre:get_value s "filename_short"))))
           (mode-text ""))
      (when sound
        (let* ((kg    (contimbre:find_keygroup_of_contimbre_sound sound))
               (mi    (when kg (contimbre:eplayer_key-modes_index kg)))
               (instr (when kg (contimbre:eplayer_key-model kg)))
               (modes (when (and instr mi)
                        (contimbre:eplayer_get_all_modes_of_instrument instr)))
               (mlist (when (and modes (< mi (length modes)))
                        (nth mi modes))))
          (when mlist
            (setf mode-text
                  (reduce (lambda (a b) (format nil "~A ~A" a b)) mlist)))))
      (push (format nil "\\"~A\\": \\"~A\\"" (escape-json id) (escape-json mode-text))
            pairs)))
  (format t "MODES-OK {{~{{~A~^, ~}}}}~%" (nreverse pairs)))

(sb-ext:exit)
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".lisp", delete=False) as f:
        f.write(lisp_script)
        tmp = f.name

    try:
        import os as _os
        res = subprocess.run(["sbcl", "--load", tmp],
                             capture_output=True, text=True, timeout=300)
        _os.unlink(tmp)
    except Exception:
        return {}

    import re as _re
    m = _re.search(r'MODES-OK (\{.*\})', res.stdout, _re.DOTALL)
    if not m:
        return {}
    try:
        return _json.loads(m.group(1))
    except Exception:
        return {}


def build_score_json(gestures, duration, df_active, bpm=60, dur_scale=1.0):
    """Build score JSON using events_timed.
    Resolve mode text strings via SBCL using modes_index.
    """
    import re as _re
    y_min = df_active["y"].min()
    y_max = df_active["y"].max()

    # Raccoglie tutti gli id unici per una singola chiamata SBCL
    all_ids = list(dict.fromkeys(
        ev["sound"]["id"]
        for g in gestures
        for ev in g.get("events_timed", [])
    ))
    mode_map = resolve_modes_via_sbcl(all_ids)

    score_gestures = []
    for g in gestures:
        events_timed = g.get("events_timed", [])
        if not events_timed:
            continue
        events = []
        for ev in events_timed:
            sound   = ev["sound"]
            sid     = sound.get("id", "")
            azimuth = y_to_azimuth(sound["y"], y_min, y_max)
            instr   = sound.get("instrument", sid.split(".")[0])
            mode    = mode_map.get(sid, "")
            ch0, ch1, alpha = azimuth_to_channel(azimuth)
            events.append({
                "t":          ev["t"],
                "azimuth":    azimuth,
                "channel":    ch0,
                "channel_b":  ch1,
                "pan_alpha":  alpha,
                "ch_label":   channel_label(azimuth),
                "id":         sid,
                "instrument": instr,
                "mode":       mode,
                "tension":    ev.get("tension", g.get("tension", 0.5)),
                "accent":     ev.get("accent", "none"),
            })
        # Evita sovrapposizioni per stesso strumento nello stesso field.
        # Durata stimata: DUR_MIN + tension * (DUR_MAX - DUR_MIN) in secondi.
        DUR_MIN, DUR_MAX = 0.4, 7.0
        last_end_by_instr = {}
        events_sorted = sorted(events, key=lambda e: e["t"])
        for ev in events_sorted:
            instr    = ev["instrument"]
            dur_est  = DUR_MIN + float(ev.get("tension", 0.5)) * (DUR_MAX - DUR_MIN)
            last_end = last_end_by_instr.get(instr, 0.0)
            if ev["t"] < last_end:
                ev["t"] = round(last_end, 2)
            last_end_by_instr[instr] = round(ev["t"] + dur_est, 2)
        events = events_sorted

        score_gestures.append({
            "index":        g["index"],
            "t_start":      g["t_start"],
            "t_end":        g["t_end"],
            "tension":      g.get("tension", 0.5),
            "dynamic_form": g.get("dynamic_form", "Neutral"),
            "lachenmann":   g.get("lachenmann", "Neutro"),
            "step_dists":   g.get("step_dists", []),
            "events":       events,
        })
    return {"duration": duration, "bpm": bpm, "dur_scale": dur_scale, "gestures": score_gestures}


# ─── Callbacks ──────────────────────────────────────────────────────────────

# Family ↔ instrument synchronisation
for fam in ALL_FAMILIES:
    _fam_id   = f"fam-{fam.replace(' ', '_')}"
    _instr_id = f"instr-{fam.replace(' ', '_')}"
    _instruments = sorted(df_full[df_full["family"] == fam]["instrument"].unique().tolist())

    def _make_sync(instr_id, instruments):
        @app.callback(
            Output(instr_id, "value"),
            Input(instr_id.replace("instr-", "fam-"), "value"),
            prevent_initial_call=True,
        )
        def _sync(fam_val, _i=instruments):
            return _i if fam_val else []
    _make_sync(_instr_id, _instruments)


@app.callback(Output("duration-slider-display",   "children"), Input("duration-slider",   "value"))
def _upd_duration(val):   return str(val)

@app.callback(Output("gestures-slider-display",   "children"), Input("gestures-slider",   "value"))
def _upd_gestures(val):   return str(val)

@app.callback(Output("steps-slider-display",      "children"), Input("steps-slider",      "value"))
def _upd_steps(val):      return str(val)

@app.callback(Output("volatility-slider-display", "children"), Input("volatility-slider", "value"))
def _upd_volatility(val): return str(val)

@app.callback(Output("drift-noise-slider-display","children"), Input("drift-noise-slider","value"))
def _upd_drift(val):      return str(val)

@app.callback(Output("threshold-slider-display",  "children"), Input("threshold-slider",  "value"))
def _upd_threshold(val):  return str(val)

@app.callback(Output("spectral-div-slider-display", "children"), Input("spectral-div-slider", "value"))
def _upd_spectral_div(val): return str(val)

@app.callback(Output("attraction-slider-display", "children"), Input("attraction-slider", "value"))
def _upd_attraction(val): return str(val)



# Apply filter → recompute UMAP → update df-store
@app.callback(
    Output("df-store",      "data"),
    Output("filter-status", "children"),
    Output("umap-graph",    "figure", allow_duplicate=True),
    Input("filter-btn",     "n_clicks"),
    [State(iid, "value") for iid in instr_filter_ids],
    prevent_initial_call=True,
)
def apply_filter(n_clicks, *instr_values):
    # Raccogli tutti gli strumenti selezionati
    selected = []
    for vals in instr_values:
        if vals:
            selected.extend(vals)

    if not selected:
        return None, "Select at least one instrument.", go.Figure()

    # Se il TSV originale esiste, usa colonne ricche per UMAP
    if os.path.exists(UMAP_ORIG_PATH):
        df_orig = pd.read_csv(UMAP_ORIG_PATH, sep="\t")
        df_orig["pitch"] = pd.to_numeric(df_orig["pitch"], errors="coerce")
        df_orig["pitch"] = df_orig["pitch"].replace(-1000.0, np.nan).fillna(df_orig["pitch"].median())
        dynamic_map = {"ppp":1,"pp":2,"p":3,"mp":4,"mf":5,"f":6,"ff":7,"fff":8}
        df_orig["dynamic_num"] = df_orig["dynamic"].map(dynamic_map).fillna(0)
        df_sub = df_orig[df_orig["instrument"].isin(selected)].copy()
        # Campiona max 100 per strumento per velocità
        df_sub = df_sub.groupby("instrument").apply(
            lambda x: x.sample(min(len(x), 100), random_state=42)
        ).reset_index(drop=True)
        features = ["pitch", "dynamic_num", "spectral_complexity", "spectral_center",
                    "duration", "absolute_intensity"]
    else:
        # Fallback: usa coordinate già calcolate, filtra solo
        df_sub = df_full[df_full["instrument"].isin(selected)].copy()
        features = ["x", "y"]

    if len(df_sub) < 10:
        return None, f"Too few sounds ({len(df_sub)}). Select more instruments.", go.Figure()

    # Ricalcola UMAP
    X = df_sub[[c for c in features if c in df_sub.columns]].fillna(0).values
    X_std = StandardScaler().fit_transform(X)
    n_neighbors = min(8, len(df_sub) - 1)
    embedding = umap_lib.UMAP(n_components=2, n_neighbors=n_neighbors,
                               min_dist=0.1, random_state=42).fit_transform(X_std)
    df_sub["x"] = embedding[:, 0]
    df_sub["y"] = embedding[:, 1]

    n_instr = df_sub["instrument"].nunique()
    status = f"✓ {len(df_sub)} sounds · {n_instr} instruments"
    df_out = df_sub[["id", "instrument", "family", "x", "y"]]
    _fig = go.Figure()
    for _fam, _grp in df_out.groupby("family"):
        _col = FAMILY_COLORS.get(_fam, "#ccc")
        _fig.add_trace(go.Scattergl(
            x=_grp["x"], y=_grp["y"], mode="markers",
            marker=dict(size=5, color=_col, opacity=0.4),
            name=_fam, text=_grp["id"],
            hovertemplate="<b>%{text}</b><extra></extra>",
            legendgroup=_fam,
        ))
    _fig.update_layout(
        paper_bgcolor="#fafafa", plot_bgcolor="#fafafa",
        font=dict(family="Courier New", size=10, color="#555"),
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="v", x=1.01, y=1, font=dict(size=9), itemsizing="constant"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
    )
    return df_out.to_dict("records"), status, _fig



# ── Routing ─────────────────────────────────────────────────────────────────
@app.callback(
    Output("home-page",        "style"),
    Output("score-page",       "style"),
    Output("score-title",      "children"),
    Output("score-graph",      "figure"),
    Output("score-status-page","children"),
    Input("url", "pathname"),
)
def routing(pathname):
    import re as _re
    home_visible  = {"fontFamily": "Georgia, serif", "background": "#fafafa",
                     "minHeight": "100vh", "display": "block"}
    home_hidden   = {"display": "none"}
    score_visible = {"background": "#fafafa", "minHeight": "100vh", "display": "block"}
    score_hidden  = {"display": "none"}

    m = _re.match(r'^/partitura/(\d+)$', pathname or "/")
    if m:
        idx = int(m.group(1)) - 1
        fig, status = _build_score_figure(idx, None, None, None)
        return home_hidden, score_visible, f"Partitura — Field {idx + 1}", fig, status
    return home_visible, score_hidden, "", go.Figure(), ""







@app.callback(
    Output("selected-gesture", "data"),
    Input({"type": "gesture-btn", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_gesture(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return 0
    triggered_id = ctx.triggered[0]["prop_id"]
    import re as _re, json as _json
    m = _re.search(r'\{.*\}', triggered_id)
    if m:
        try:
            return _json.loads(m.group(0))["index"]
        except Exception:
            pass
    return 0



@app.callback(
    Output("dynamic-form-store", "data"),
    Input({"type": "dynform-drop", "index": dash.ALL}, "value"),
    State("gestures-slider", "value"),
    prevent_initial_call=True,
)
def save_dynamic_forms(df_values, n_gestures):
    store = {}
    for i, v in enumerate(df_values or []):
        store[str(i)] = v or "Neutral"
    return store


# Dynamic Form dropdowns
@app.callback(
    Output("dynamic-form-dropdowns", "children"),
    Input("gestures-slider", "value"),
    Input("dynamic-form-store", "data"),
)
def update_dynamic_form_dropdowns(n_gestures, df_store):
    options = [{"label": cat, "value": cat} for cat in DYNAMIC_FORM_CATEGORIES]
    items = []
    for i in range(n_gestures):
        color = GESTURE_PALETTE[i % len(GESTURE_PALETTE)]
        saved = (df_store or {}).get(str(i), "Neutral")
        dir_color = DYNAMIC_FORM_COLORS.get(saved, "#888")
        items.append(html.Div([
            html.Span(f"G{i+1}", style={
                "fontFamily": "monospace", "fontSize": "9px",
                "color": color, "marginRight": "8px", "fontWeight": "bold",
            }),
            dcc.Dropdown(
                id={"type": "dynform-drop", "index": i},
                options=options,
                value=saved,
                clearable=False,
                searchable=False,
                style={"fontFamily": "monospace", "fontSize": "9px", "flex": "1",
                       "color": dir_color},
            ),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}))
    return items


@app.callback(
    Output("umap-graph",    "figure"),
    Output("sequence-list", "children"),
    Output("gesture-info",  "children"),
    Output("timeline",      "children"),
    Output("path-store",    "data"),
    Output("gestures-store","data"),
    Input("generate-btn",   "n_clicks"),
    State("df-store",            "data"),
    State("duration-slider",     "value"),
    State("gestures-slider",     "value"),
    State("steps-slider",        "value"),
    State("volatility-slider",   "value"),
    State("drift-noise-slider",  "value"),
    State("threshold-slider",    "value"),
    State("attraction-slider",   "value"),
    State("spectral-div-slider", "value"),
    State({"type": "dynform-drop",   "index":  dash.ALL}, "value"),
    State("dynamic-form-store",  "data"),
    prevent_initial_call=True,
)
def generate(n_clicks, df_store, duration, n_gestures, steps, init_vol, drift_noise,
             threshold, attraction, spectral_div, df_values,
             dynform_store):
    if df_store:
        df_active = pd.DataFrame(df_store)
    else:
        df_active = df_full.copy()

    # Legge i valori direttamente dai dropdown
    if df_values and len(df_values) >= n_gestures:
        dynamic_form_sequence = [v or "Neutral" for v in df_values[:n_gestures]]
    elif df_values:
        dynamic_form_sequence = [v or "Neutral" for v in df_values]
        while len(dynamic_form_sequence) < n_gestures:
            dynamic_form_sequence.append("Neutral")
    else:
        dynamic_form_sequence = ["Neutral"] * n_gestures

    gestures = generate_composition(
        n_gestures, steps, init_vol, drift_noise, duration, df_active,
        threshold=threshold or 0.0,
        dynamic_form_sequence=dynamic_form_sequence,
        attraction=attraction or 0.35,
        spectral_diversity=spectral_div if spectral_div is not None else 0.15,
    )

    fig = go.Figure()

    for fam, grp in df_active.groupby("family"):
        col = FAMILY_COLORS.get(fam, "#ccc")
        fig.add_trace(go.Scattergl(
            x=grp["x"], y=grp["y"], mode="markers",
            marker=dict(size=5, color=col, opacity=0.25),
            name=fam, text=grp["id"],
            hovertemplate="<b>%{text}</b><extra></extra>",
            legendgroup=fam,
        ))

    all_ids = []
    for g in gestures:
        color = GESTURE_PALETTE[g["index"] % len(GESTURE_PALETTE)]
        px_list = [p[0] for p in g["path"]]
        py_list = [p[1] for p in g["path"]]
        fig.add_trace(go.Scatter(
            x=px_list, y=py_list, mode="lines",
            line=dict(color=color, width=1.5, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))
        for j, sound in enumerate(g["sequence"]):
            fig.add_trace(go.Scatter(
                x=[sound["x"]], y=[sound["y"]],
                mode="markers+text",
                marker=dict(size=13, color=color, line=dict(color="white", width=1.5)),
                text=[str(j + 1)],
                textposition="middle center",
                textfont=dict(size=7, color="white", family="Courier New"),
                hovertemplate=f"<b>{sound['id']}</b><br>field {g['index']+1}, suono {j+1}<extra></extra>",
                showlegend=False,
            ))
            all_ids.append({"id": sound["id"], "gesture": g["index"]})

    fig.update_layout(
        paper_bgcolor="#fafafa", plot_bgcolor="#fafafa",
        font=dict(family="Courier New", size=10, color="#555"),
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="v", x=1.01, y=1, font=dict(size=9), itemsizing="constant"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
    )

    seq_items = []
    for g in gestures:
        color = GESTURE_PALETTE[g["index"] % len(GESTURE_PALETTE)]
        seq_items.append(html.Div(f"Field {g['index']+1}", style={
            "fontFamily": "monospace", "fontSize": "9px", "color": color,
            "letterSpacing": "2px", "textTransform": "uppercase",
            "padding": "8px 0 4px", "borderTop": "1px solid #f0f0f0"
        }))
        for j, s in enumerate(g["sequence"]):
            seq_items.append(html.Div([
                html.Span(f"{j+1:02d}", style={"fontFamily": "monospace", "fontSize": "9px",
                                               "color": "#aaa", "marginRight": "8px"}),
                html.Span(s["id"], style={"fontFamily": "monospace", "fontSize": "9px", "color": "#111"}),
            ], style={"padding": "3px 0", "display": "flex"}))

    gesture_items = []
    for g in gestures:
        color     = GESTURE_PALETTE[g["index"] % len(GESTURE_PALETTE)]
        direction = g.get("dynamic_form", "Neutral")
        dir_color = DYNAMIC_FORM_COLORS.get(direction, "#888")
        gesture_items.append(html.Div([
            html.Div(f"Field {g['index']+1}  ·  {g['t_start']}″ → {g['t_end']}″",
                     style={"fontFamily": "monospace", "fontSize": "10px",
                            "color": color, "fontWeight": "bold", "marginBottom": "2px"}),
            html.Div([
                html.Span(direction, style={"color": dir_color, "fontWeight": "bold", "marginRight": "8px"}),
                html.Span(f"tensione={g.get('tension','—')}  vol={g['vol']}  suoni={g.get('density',len(g['sequence']))}"),
            ], style={"fontFamily": "monospace", "fontSize": "9px", "color": "#888"}),
        ], style={"marginBottom": "10px"}))

    timeline_items = []
    for g in gestures:
        color     = GESTURE_PALETTE[g["index"] % len(GESTURE_PALETTE)]
        direction = g.get("dynamic_form", "Neutral")
        dir_color = DYNAMIC_FORM_COLORS.get(direction, "#888")
        tension   = g.get("tension", 0.5)
        evs       = g.get("events_timed", [])
        az_vals   = []
        for ev in evs:
            s = ev.get("sound")
            if s is not None:
                try:
                    az_vals.append(float(s["y"]) if isinstance(s, dict) else float(s.get("y", 180)))
                except Exception:
                    az_vals.append(180.0)
        azimuth   = float(np.mean(az_vals)) if az_vals else 180.0
        left_pct  = g["t_start"] / duration * 100
        width_pct = (g["t_end"] - g["t_start"]) / duration * 100
        timeline_items.append(
            dcc.Link(
                [
                    html.Span(str(g["index"] + 1),
                              style={"fontSize": "10px", "fontWeight": "bold",
                                     "display": "block"}),
                    html.Span(DIR_ABBREV.get(direction, direction[:5]),
                              style={"fontSize": "7px", "opacity": "0.85",
                                     "display": "block", "letterSpacing": "0.5px"}),
                ],
                href=f"/partitura/{g['index'] + 1}",
                title=f"G{g['index']+1} · {direction} · t={tension:.2f} · az={azimuth:.0f}°",
                style={
                    "position": "absolute", "left": f"{left_pct}%",
                    "width": f"{width_pct - 0.5}%", "height": "34px",
                    "background": color,
                    "borderTop": f"3px solid {dir_color}",
                    "borderRadius": "0 0 3px 3px",
                    "cursor": "pointer", "display": "flex", "flexDirection": "column",
                    "alignItems": "center", "justifyContent": "center",
                    "fontFamily": "monospace", "color": "white",
                    "textDecoration": "none", "top": "0",
                }
            )
        )
    timeline_items.append(html.Div(
        f"{duration}″  ·  {n_gestures} fields  ·  {len(all_ids)} sounds  "
        f"·  click block → score",
        style={"fontFamily": "monospace", "fontSize": "9px", "color": "#aaa",
               "position": "absolute", "bottom": "0", "left": "0"}
    ))
    timeline = html.Div(timeline_items, style={"position": "relative", "height": "60px"})

    # Serializza gestures per lo store (rimuove oggetti pandas non serializzabili)
    gestures_serial = []
    for g in gestures:
        evs = []
        for ev in g.get("events_timed", []):
            s = ev["sound"]
            evs.append({
                "t":       ev["t"],
                "tension": ev.get("tension", g.get("tension", 0.5)),
                "accent":  ev.get("accent", "none"),
                "sound":   {k: (float(v) if hasattr(v, "item") else v)
                            for k, v in s.items() if k in ["id","instrument","family","x","y"]},
                "gesture_idx": ev["gesture_idx"],
            })
        gestures_serial.append({
            "index":        g["index"],
            "tension":      g.get("tension", 0.5),
            "t_start":      g["t_start"],
            "t_end":        g["t_end"],
            "dynamic_form": g.get("dynamic_form", "Neutral"),
            "lachenmann":   g.get("lachenmann", "Neutro"),
            "step_dists":   g.get("step_dists", []),
            "events_timed": evs,
        })
    return fig, seq_items, gesture_items, timeline, all_ids, gestures_serial






@app.callback(
    Output("export-status", "children"),
    Input("export-btn",     "n_clicks"),
    State("path-store",     "data"),
    prevent_initial_call=True,
)
def export_to_contimbre(n_clicks, store_data):
    if not store_data:
        return "No path generated."

    from collections import defaultdict
    gestures_ids = defaultdict(list)
    for d in store_data:
        gestures_ids[d["gesture"]].append(d["id"])

    n_gestures = len(gestures_ids)
    gesture_blocks = ""
    for g_idx, ids in sorted(gestures_ids.items()):
        lisp_ids = " ".join(f'"{sid}"' for sid in ids)
        out_path = os.path.join(SCORES_DIR, f"brownian_field_{g_idx + 1:02d}")
        gesture_blocks += f"""
(let* ((ids '({lisp_ids}))
       (ct-seq (remove nil
                 (mapcar (lambda (id)
                           (find id contimbre:contimbre
                                 :test #'string=
                                 :key (lambda (s) (contimbre:get_value s "filename_short"))))
                         ids))))
  (format t "Gesto {g_idx + 1}: ~A suoni~%" (length ct-seq))
  (contimbre:write_orchestrations (list ct-seq) "{out_path}"))
"""

    lisp_script = f"""
(ql:quickload '(:cl-ppcre :parse-float) :silent t)
(defvar conTimbreDir "/Volumes/disk 1/conTimbre Standard V2")
(load (format nil "~A/algorithmic orchestration/contimbre_library.lisp" conTimbreDir))
(in-package :contimbre)
{gesture_blocks}
(format t "Esportato.~%")
(sb-ext:exit)
"""
    with open(SBCL_SCRIPT, "w") as f:
        f.write(lisp_script)
    try:
        result = subprocess.run(["sbcl", "--load", SBCL_SCRIPT],
                                capture_output=True, text=True, timeout=180)
        if "Esportato." in result.stdout:
            return f"✓ {n_gestures} .cOrc files → scores/brownian_field_01..{n_gestures:02d}"
        return f"Errore: {result.stderr[:80]}"
    except subprocess.TimeoutExpired:
        return "Timeout — open SBCL manually."
    except FileNotFoundError:
        return "SBCL not found in PATH."


def _build_score_figure(sel_idx, gestures_data, df_store, duration):
    """Partitura grafica — notazione Aural Sonology (Thoresen cap. 8).

    Per ogni gesto:
    - Header: direzione temporale con simbolo (→ ← ○ —) e colore
    - Corpo: barre durata + simboli d'accento (release, goal, termination, warning)
    - Simbolo onset = forma del marker Thoresen per la direzione del gesto
    - Goal point automatico = evento di massima tensione (marker più grande)
    """
    import json as _json, os as _os, re as _re

    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                        margin=dict(l=0,r=0,t=0,b=0))
    if not gestures_data and not _os.path.exists(SCORE_PATH):
        return empty, "Generate a composition first."
    if _os.path.exists(SCORE_PATH):
        with open(SCORE_PATH) as f:
            score = _json.load(f)
    else:
        if df_store:
            df_active = pd.DataFrame(df_store)
        else:
            df_active = df_full.copy()
        score = build_score_json(gestures_data, duration or 120, df_active)
        with open(SCORE_PATH, "w") as f:
            _json.dump(score, f)

    gestures = score["gestures"]
    if not gestures:
        return empty, "No fields."

    sel_idx    = min(max(sel_idx, 0), len(gestures) - 1)
    g          = gestures[sel_idx]
    idx        = g["index"]
    direction  = g.get("dynamic_form", "Neutral")
    dir_color  = DYNAMIC_FORM_COLORS.get(direction, "#888888")
    t_start    = g["t_start"]; t_end = g["t_end"]
    events     = g["events"]; n_ev = len(events)
    g_dur      = max(t_end - t_start, 0.001)
    n_gestures = len(gestures)

    # Simbolo direzione per header testuale
    DIR_GLYPH = {
        "Forward":  "→",
        "Backward": "←",
        "Presence": "○",
        "Neutral":  "—",
    }

    INK       = "#111111"
    INK_MED   = "#222222"
    INK_LIGHT = "#444444"
    INK_FAINT = "#888888"
    PAPER     = "white"

    fig = go.Figure()

    # ── Header gesto ──────────────────────────────────────────────────────────
    fig.add_annotation(x=-g_dur*0.03, y=410,
        text=f"<b>field {idx+1}</b>",
        font=dict(size=11, color=INK, family="Georgia, serif"),
        showarrow=False, xanchor="left", yanchor="bottom")
    fig.add_annotation(x=-g_dur*0.03, y=401,
        text=f"{t_start:.0f}\u2033 \u2014 {t_end:.0f}\u2033  \u00b7  {n_ev} eventi",
        font=dict(size=8, color=INK_LIGHT, family="Georgia, serif"),
        showarrow=False, xanchor="left", yanchor="bottom")

    # Direzione temporale Thoresen — simbolo + nome
    fig.add_annotation(x=g_dur*1.08, y=412,
        text=f"<b>{DIR_GLYPH.get(direction, '—')}</b>",
        font=dict(size=18, color=dir_color, family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")
    fig.add_annotation(x=g_dur*1.08, y=401,
        text=f"<i>{direction}</i>",
        font=dict(size=10, color=dir_color, family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")

    # Navigazione gesti con colore direzione
    nav_parts = []
    for ni in range(n_gestures):
        nd = gestures[ni].get("dynamic_form", "Neutral")
        nc = DYNAMIC_FORM_COLORS.get(nd, "#888")
        glyph = DIR_GLYPH.get(nd, "—")
        if ni == idx:
            nav_parts.append(f"<b>{ni+1}</b>")
        else:
            nav_parts.append(f'<span style="color:{nc}">{ni+1}{glyph}</span>')
    fig.add_annotation(x=g_dur*1.08, y=394,
        text="  ".join(nav_parts),
        font=dict(size=8, color=INK_LIGHT, family="Georgia, serif"),
        showarrow=False, xanchor="right", yanchor="bottom")

    # ── Griglia azimutale ─────────────────────────────────────────────────────
    for deg in range(0, 361, 45):
        fig.add_shape(type="line", x0=0, x1=g_dur, y0=deg, y1=deg,
            line=dict(color=INK_FAINT, width=0.4, dash="dot"), layer="below")
        fig.add_annotation(x=-g_dur*0.02, y=deg,
            text=f"{deg}\u00b0",
            font=dict(size=7, color=INK_FAINT, family="Georgia, serif"),
            showarrow=False, xanchor="right", yanchor="middle")

    # ── Asse temporale ────────────────────────────────────────────────────────
    fig.add_shape(type="line", x0=0, x1=g_dur, y0=-5, y1=-5,
        line=dict(color=INK_FAINT, width=0.6))
    tick_step = max(1, round(g_dur / 8))
    for t_tick in range(0, int(g_dur)+1, tick_step):
        fig.add_shape(type="line", x0=t_tick, x1=t_tick, y0=-8, y1=-2,
            line=dict(color=INK_FAINT, width=0.6))
        fig.add_annotation(x=t_tick, y=-13,
            text=f"{t_tick}\u2033",
            font=dict(size=7, color=INK_FAINT, family="Georgia, serif"),
            showarrow=False, xanchor="center", yanchor="top")

    # Separatori sotto-gesto
    for s in range(1, 4):
        x_sep = g_dur * s / 4
        fig.add_shape(type="line", x0=x_sep, x1=x_sep, y0=0, y1=360,
            line=dict(color=INK_FAINT, width=0.5, dash="dash"), layer="below")



    # ── Profilo di tensione di sfondo (curva sottile) ─────────────────────────
    # Curva 1 (colore direzione): tensione compositiva per evento
    # Curva 2 (rosso tenue): inviluppo browniano — 1/durata_cella normalizzato
    if n_ev > 1:
        t_curve   = [ev["t"] - t_start for ev in events]
        ten_curve = [ev.get("tension", 0.5) for ev in events]
        ten_norm  = [(v - min(ten_curve)) / max(max(ten_curve) - min(ten_curve), 0.01)
                     for v in ten_curve]
        # Curva 1 — tensione compositiva (direzione)
        fig.add_trace(go.Scatter(
            x=t_curve,
            y=[374 + v * 14 for v in ten_norm],
            mode="lines",
            line=dict(color=dir_color, width=1.2, dash="dot"),
            opacity=0.4,
            showlegend=False, hoverinfo="skip"))

    # Curva 2 — inviluppo browniano (dalle distanze step_dists)
    step_dists_env = g.get("step_dists", [])
    if len(step_dists_env) > 1:
        raw_env    = step_dists_env[1:]  # distanze inter-passo
        total_env  = sum(raw_env) if sum(raw_env) > 0 else 1.0
        # Inverso normalizzato: passo corto = tensione alta
        inv        = [total_env / (d * len(raw_env)) if d > 0 else 1.0 for d in raw_env]
        inv_min, inv_max = min(inv), max(inv)
        inv_norm   = [(v - inv_min) / max(inv_max - inv_min, 0.01) for v in inv]
        # Posizioni temporali: centri delle celle browniane
        cell_secs_env = [d / total_env * g_dur for d in raw_env]
        t_env = [0.0]
        for s in cell_secs_env:
            t_env.append(t_env[-1] + s)
        t_centers = [(t_env[i] + t_env[i+1]) / 2 for i in range(len(cell_secs_env))]
        fig.add_trace(go.Scatter(
            x=t_centers,
            y=[374 + v * 14 for v in inv_norm],
            mode="lines+markers",
            line=dict(color="#E05C5C", width=1.0),
            marker=dict(size=3, color="#E05C5C"),
            opacity=0.35,
            showlegend=False, hoverinfo="skip"))

    # ── Banda ritmica browniana ──────────────────────────────────────────────
    # Una cella per passo browniano. Proporzioni = distanze euclidee nel piano UMAP.
    # Frazioni indipendenti per cella: num/den ottimale con den ≤ 32,
    # riferite a beat_sec (bpm del JSON score).
    # Etichette alternate sopra/sotto la linea (stile OpenMusic).
    step_dists = g.get("step_dists", [])
    if len(step_dists) > 1:
        from math import gcd as _gcd

        RH_Y     = -70
        RH_STEM  =  6

        raw_dists  = step_dists[1:]
        total_dist = sum(raw_dists) if sum(raw_dists) > 0 else 1.0

        # Durate in secondi per ogni cella (proporzionali alle distanze browniane)
        cell_secs = [d / total_dist * g_dur for d in raw_dists]

        # BPM canonico tale che g_dur * BPM / 60 sia il più vicino a un intero.
        # Garantisce che la somma delle frazioni corrisponda alla durata reale.
        n_steps = len(raw_dists)
        CANONICAL_BPM = [
            40,42,44,46,48,50,52,54,56,58,60,63,66,69,72,76,80,84,88,
            92,96,100,104,108,112,116,120,126,132,138,144,152,160,168,
            176,184,200,208
        ]
        bpm_score = min(CANONICAL_BPM,
                        key=lambda b: abs(g_dur * b / 60.0 - round(g_dur * b / 60.0)))
        beat_sec  = 60.0 / bpm_score
        NOTE_UNITS = [
            ("\u266a",  0.5),    # ♪ croma
            ("\u266a.", 0.75),   # ♪. croma puntata
            ("\u2669",  1.0),    # ♩ semiminima
            ("\u2669.", 1.5),    # ♩. semiminima puntata
            ("\U0001D157\U0001D165", 2.0),   # 𝅗𝅥 minima
            ("\U0001D157\U0001D165.", 3.0),  # 𝅗𝅥. minima puntata
        ]

        # Unità di nota globale — quella che porta al BPM canonico scelto
        # per la durata media delle celle.
        avg_cell_sec    = g_dur / n_steps if n_steps > 0 else 1.0
        best_unit_label = "♩"
        best_dist_u     = float("inf")
        for unit_label, unit_beats in NOTE_UNITS:
            bpm_loc  = unit_beats / avg_cell_sec * 60.0 if avg_cell_sec > 0 else 60.0
            dist_u   = abs(bpm_loc - bpm_score)
            if dist_u < best_dist_u:
                best_dist_u     = dist_u
                best_unit_label = unit_label

        # Per ogni cella trova num/den ottimale con denominatore binario.
        # Tutte le frazioni riferite allo stesso BPM globale del gesto.
        frac_labels   = []
        tick_times    = [0.0]
        BINARY_DENOMS = [1, 2, 4, 8, 16, 32]
        for dur_sec in cell_secs:
            dur_beats = dur_sec / beat_sec
            best_num, best_den, best_err = max(1, round(dur_beats)), 1, float("inf")
            for den in BINARY_DENOMS:
                num = max(1, round(dur_beats * den))
                err = abs(num / den - dur_beats)
                if err < best_err:
                    best_err           = err
                    best_num, best_den = num, den
            d = _gcd(best_num, best_den)
            fn, fd = best_num // d, best_den // d
            frac_labels.append(f"{fn}/{fd}" if fd > 1 else str(fn))
            tick_times.append(tick_times[-1] + dur_sec)

        # Linea base
        fig.add_shape(type="line", x0=0, x1=g_dur, y0=RH_Y, y1=RH_Y,
            line=dict(color=INK_FAINT, width=0.8))

        # Barra finale
        fig.add_shape(type="line", x0=g_dur, x1=g_dur,
            y0=RH_Y - 3, y1=RH_Y + 3,
            line=dict(color=INK_LIGHT, width=1.0))

        # Tacche agli onset di ogni cella + etichette alternate
        for i, (t_tick, label) in enumerate(zip(tick_times[:-1], frac_labels)):
            # Barra rossa verticale attraverso tutta la partitura (0°–360°)
            # La prima tacca (i=0, t=0) e l'ultima non vengono tracciate
            # perché coincidono con i bordi del gesto
            if i > 0:
                fig.add_shape(type="line",
                    x0=t_tick, x1=t_tick,
                    y0=0, y1=360,
                    line=dict(color="#E05C5C", width=1.2),
                    opacity=0.7,
                    layer="below")
            # Tacca sulla linea base
            fig.add_shape(type="line",
                x0=t_tick, x1=t_tick,
                y0=RH_Y - 3, y1=RH_Y + 3,
                line=dict(color="#E05C5C" if i > 0 else INK, width=1.2))
            # Etichetta alternata sopra/sotto: frazione + BPM locale
            above  = (i % 2 == 1)
            offset = 8 if i == 0 else 5
            y_text = RH_Y + offset if above else RH_Y - offset
            anchor = "bottom" if above else "top"
            fig.add_annotation(x=t_tick, y=y_text,
                text=f"<b>{label}</b><br><span style='font-size:9px;color:#555'>{best_unit_label}={bpm_score}</span>",
                font=dict(size=11, color=INK, family="Georgia, serif"),
                showarrow=False, xanchor="center", yanchor=anchor)

        # Etichetta e Σ a destra
        fig.add_annotation(x=g_dur * 1.01, y=RH_Y,
            text="pulse grid",
            font=dict(size=7, color=INK_FAINT, family="Georgia, serif"),
            showarrow=False, xanchor="left", yanchor="middle")
        fig.add_annotation(x=g_dur * 1.01, y=RH_Y - 6,
            text=f"Σ {round(g_dur, 2)}s",
            font=dict(size=7, color=INK_FAINT, family="Georgia, serif"),
            showarrow=False, xanchor="left", yanchor="top")

    # ── Suoni — barre + simboli ─────────────────────────────────────────────
    # Ogni evento riceve sempre una testa con il simbolo della direzione.
    # Gli accenti speciali (release/goal/termination/warning) si sovrappongono.
    dur_min, dur_max_v = 0.4, 7.0

    ev_tensions = [ev.get("tension", 0.5) for ev in events]

    DIR_DEFAULT_SYM = {
        "Forward":  "triangle-right",
        "Backward": "triangle-left",
        "Presence": "circle-open",
        "Neutral":  "line-ew",
    }
    default_sym = DIR_DEFAULT_SYM.get(direction, "circle-open")

    default_pts = {"x": [], "y": [], "sz": [], "tip": [], "op": []}
    by_accent   = {}

    for ev_idx, ev in enumerate(events):
        instr   = ev["instrument"]
        mode    = ev.get("mode", "")
        t       = ev["t"] - t_start
        azimuth = ev["azimuth"]
        tension = ev.get("tension", 0.5)
        t_rel   = t / g_dur

        accent = ev.get("accent") or compute_accent_function(
            ev_idx, n_ev, ev_tensions, direction)

        onset_offset = 0.0
        t_draw   = t + onset_offset
        dur_vis  = dur_min + tension * (dur_max_v - dur_min)
        line_w   = 0.4 + tension * 2.2
        line_op  = 0.35 + tension * 0.6

        bar_end = min(t_draw + dur_vis, g_dur)

        fig.add_shape(type="line", x0=t_draw, x1=bar_end,
            y0=azimuth, y1=azimuth,
            line=dict(color=INK, width=line_w), opacity=line_op)
        # Terminatore solo se non clippato
        if bar_end < g_dur:
            fig.add_shape(type="line",
                x0=bar_end, x1=bar_end,
                y0=azimuth-2, y1=azimuth+2,
                line=dict(color=INK_LIGHT, width=0.6), opacity=line_op)

        ch_lbl = ev.get("ch_label", channel_label(azimuth))
        # ch_lbl non viene visualizzato in partitura — è nel JSON per SuperCollider

        # Etichetta strumento — ancora a destra se vicina al bordo destro
        mid_x   = (t_draw + bar_end) / 2
        if t_draw > g_dur * 0.72:
            lx_pos  = min(t_draw - 2, g_dur * 0.97)
            xanchor = "right"
        else:
            lx_pos  = mid_x
            xanchor = "center"
        fig.add_annotation(x=lx_pos, y=azimuth,
            text=instr,
            font=dict(size=10, color=INK_MED, family="Georgia, serif"),
            showarrow=False, xanchor=xanchor, yanchor="bottom",
            yshift=5, bgcolor="rgba(255,255,255,0.92)", borderpad=2)

        tip = f"<b>{instr}</b>"
        if mode: tip += f"<br><i>{mode}</i>"
        tip += (f"<br>t = {ev['t']:.1f}s  ·  {azimuth}°  ·  {ch_lbl}"
                f"<br>{direction}  ·  tensione = {tension:.2f}"
                f"<br><i>{accent}</i>")

        base_sz = 6 + tension * 5
        op      = min(line_op + 0.15, 1.0)

        # Strato base: simbolo direzione su ogni evento
        default_pts["x"].append(t_draw)
        default_pts["y"].append(azimuth)
        default_pts["sz"].append(base_sz)
        default_pts["tip"].append(tip)
        default_pts["op"].append(op)

        # Strato superiore: accento speciale sovrapposto
        if accent not in ("none", None):
            sz = base_sz * 1.7 if accent == "goal" else base_sz * 1.3
            by_accent.setdefault(accent, {"x":[],"y":[],"sz":[],"tip":[],"op":[]})
            by_accent[accent]["x"].append(t_draw)
            by_accent[accent]["y"].append(azimuth)
            by_accent[accent]["sz"].append(sz)
            by_accent[accent]["tip"].append(tip)
            by_accent[accent]["op"].append(min(op + 0.1, 1.0))

    # Trace simboli default (uno per tutti gli eventi)
    if default_pts["x"]:
        fig.add_trace(go.Scatter(
            x=default_pts["x"], y=default_pts["y"], mode="markers",
            marker=dict(symbol=default_sym, size=default_pts["sz"],
                        color=INK, line=dict(color=INK, width=1.0),
                        opacity=default_pts["op"]),
            customdata=default_pts["tip"],
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=True,
            name=f"{DIR_GLYPH.get(direction,'—')} {direction}",
            legendgroup="default"))

    # Trace accenti speciali sovrapposti
    ACCENT_LABEL = {
        "release":     "release point ▲",
        "goal":        "goal point ●",
        "termination": "termination ▼",
        "warning":     "warning point ◇",
    }
    for acc_name, data in by_accent.items():
        sym, _, _ = ACCENT_SYMBOL.get(acc_name, ("circle", 7, INK))
        fig.add_trace(go.Scatter(
            x=data["x"], y=data["y"], mode="markers",
            marker=dict(symbol=sym, size=data["sz"], color=INK,
                        line=dict(color=INK, width=1.6),
                        opacity=data["op"]),
            customdata=data["tip"],
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=True,
            name=ACCENT_LABEL.get(acc_name, acc_name),
            legendgroup=acc_name))

    # ── Legenda canali 8ch ────────────────────────────────────────────────────
    ch_labels = [
        ("0°","CH1","frontale centro"), ("45°","CH2","frontale destra"),
        ("90°","CH3","lat. destra"),    ("135°","CH4","post. destra"),
        ("180°","CH5","post. centro"),  ("225°","CH6","post. sinistra"),
        ("270°","CH7","lat. sinistra"), ("315°","CH8","front. sinistra"),
    ]
    step = g_dur / max(len(ch_labels), 1)
    for li, (az_l, ch_l, _) in enumerate(ch_labels):
        lx = li * step
        fig.add_trace(go.Scatter(x=[lx], y=[-28], mode="markers",
            marker=dict(symbol="circle-open" if li%2==0 else "circle",
                        size=6, color=INK, line=dict(color=INK, width=1)),
            showlegend=False, hoverinfo="skip"))
        fig.add_annotation(x=lx+step*0.12, y=-28,
            text=f"{ch_l} {az_l}",
            font=dict(size=7, color=INK_LIGHT, family="Georgia, serif"),
            showarrow=False, xanchor="left", yanchor="middle")

    fig.update_layout(
        paper_bgcolor=PAPER, plot_bgcolor=PAPER,
        margin=dict(l=60, r=40, t=60, b=80),
        font=dict(family="Georgia, serif", size=8, color=INK_LIGHT),
        xaxis=dict(range=[-g_dur*0.04, g_dur*1.12],
            showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[-95, 420], showgrid=False, zeroline=False,
            showticklabels=False, side="right"),
        hovermode="closest",
        dragmode="pan",
        hoverlabel=dict(bgcolor="white", bordercolor=INK_FAINT,
            font_size=10, font_family="Georgia, serif"),
        legend=dict(orientation="h", x=0, y=-0.1,
            font=dict(size=8, color=INK_LIGHT, family="Georgia, serif"),
            bgcolor="rgba(0,0,0,0)", borderwidth=0),
        showlegend=True)

    status = (f"field {idx+1} / {n_gestures}  ·  {n_ev} events  ·  "
              f"{t_start:.0f}\u2033 \u2014 {t_end:.0f}\u2033  ·  "
              f"{DIR_GLYPH.get(direction,'—')} {direction}")
    
    return fig, status


@app.callback(
    Output("score-ready",  "data"),
    Output("score-status", "children"),
    Input("score-btn-root",      "n_clicks"),
    State("gestures-store",      "data"),
    State("df-store",            "data"),
    State("duration-slider",     "value"),
    State("dynamic-form-store",  "data"),
    prevent_initial_call=True,
)
def generate_score(n_clicks, gestures_data, df_store, duration, dynform_store):
    if not gestures_data:
        return False, "Generate a composition first."
    dynform_store = dynform_store or {}
    for g in gestures_data:
        idx = g.get("index", 0)
        g["dynamic_form"] = dynform_store.get(str(idx), "Neutral")
        g["lachenmann"]   = "Neutro"  # compatibilita SC
    if df_store:
        df_active = pd.DataFrame(df_store)
    else:
        df_active = df_full.copy()
    import json as _json
    score = build_score_json(gestures_data, duration, df_active, bpm=60, dur_scale=1.0)
    with open(SCORE_PATH, "w") as f:
        _json.dump(score, f)
    n_fields = len(score["gestures"])
    total    = sum(len(g["events"]) for g in score["gestures"])
    return True, f"✓ Score saved — {n_fields} fields · {total} events"


@app.callback(
    Output("eplayer-status", "children"),
    Input("eplayer-btn",     "n_clicks"),
    State("path-store",      "data"),
    prevent_initial_call=True,
)
def export_eplayer(n_clicks, store_data):
    """
    Genera un unico contimbre_remnant.cePlayerOrc con una voice e N programmi
    (uno per field). MIDI Program Change 0..N-1 seleziona il field attivo.
    Mantiene anche i file per-field (contimbre_brownian_field_XX.cePlayerOrc)
    per compatibilità con il workflow precedente.
    """
    import subprocess, os, tempfile

    if not store_data:
        return "Generate a composition first."

    from collections import defaultdict
    gestures_ids     = defaultdict(list)
    seen_per_gesture = defaultdict(set)
    for d in store_data:
        g   = d["gesture"]
        sid = d["id"]
        if sid not in seen_per_gesture[g] and len(gestures_ids[g]) < 128:
            seen_per_gesture[g].add(sid)
            gestures_ids[g].append(sid)

    n_gestures = len(gestures_ids)
    out_path   = os.path.join(SCORES_DIR, "contimbre_remnant.cePlayerOrc")

    # Un blocco Lisp per ogni field → accumula programmi in all-programs
    program_blocks = ""
    for g_idx, ids in sorted(gestures_ids.items()):
        id_list   = " ".join(f'"{sid}"' for sid in ids)
        prog_name = f"field_{g_idx + 1:02d}"
        program_blocks += f"""
  ;; ── Field {g_idx + 1} ──────────────────────────────────────────
  (let* ((ids  '({id_list}))
         (prog (contimbre:make-eplayer_program))
         (keys nil)
         (found 0))

    (mapc (lambda (id)
            (let* ((sound (find id contimbre:contimbre
                                :test #'string=
                                :key  (lambda (s)
                                        (contimbre:get_value s "filename_short"))))
                   (kg    (when sound
                            (contimbre:find_keygroup_of_contimbre_sound sound))))
              (when kg
                (setf (contimbre:eplayer_key-playing_mode kg) 1)
                (push kg keys)
                (incf found))))
          ids)

    (setf keys (reverse keys))

    (when keys
      (let ((last-kg (car (last keys))))
        (loop while (< (length keys) 128)
              do (push (contimbre::copy-eplayer_key last-kg) keys))
        (setf keys (reverse (nthcdr (- (length keys) 128) (reverse keys))))))

    (if (null keys)
      (format t "SKIP field {g_idx + 1}: nessun suono~%")
      (progn
        (setf (contimbre:eplayer_program-name prog) "{prog_name}")
        (setf (contimbre:eplayer_program-keys prog) keys)
        (push prog all-programs)
        (format t "PROG-OK field={g_idx + 1} suoni=~A~%" found))))
"""

    lisp_script = f"""
(ql:quickload '(:cl-ppcre :parse-float) :silent t)
(defvar conTimbreDir "/Volumes/disk 1/conTimbre Standard V2")
(load (format nil "~A/algorithmic orchestration/contimbre_library.lisp" conTimbreDir))
(in-package :contimbre)

(let* ((orchestra   (contimbre:make-eplayer_orchestra))
       (voice       (contimbre:make-eplayer_voice))
       (all-programs nil))

{program_blocks}

  (setf all-programs (reverse all-programs))
  (setf (contimbre:eplayer_voice-programs voice) all-programs)
  (setf (contimbre:eplayer_orchestra-voices orchestra) (list voice))
  (contimbre:write_eplayer_orchestra orchestra "{out_path}")
  (format t "EPLAYER-MULTI-OK programs=~A~%" (length all-programs)))

(sb-ext:exit)
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lisp", delete=False) as f:
        f.write(lisp_script)
        tmp_lisp = f.name

    try:
        result = subprocess.run(["sbcl", "--load", tmp_lisp],
                                capture_output=True, text=True, timeout=300)
        os.unlink(tmp_lisp)
    except subprocess.TimeoutExpired:
        return "SBCL timeout — too many fields/sounds?"
    except FileNotFoundError:
        return "SBCL not found in PATH."

    if "EPLAYER-MULTI-OK" in result.stdout:
        import re as _re
        m = _re.search(r"EPLAYER-MULTI-OK programs=(\d+)", result.stdout)
        n = m.group(1) if m else str(n_gestures)
        return f"✓ {n} programs → contimbre_remnant.cePlayerOrc"
    return f"Errore: {result.stderr[:120] or result.stdout[:120]}"


from flask import request, jsonify

# ── Saved scores ────────────────────────────────────────────────────────────

def _list_scores():
    try:
        files = sorted(
            [f for f in os.listdir(SCORES_DIR) if f.endswith(".json")
             and f != "modes_cache.json"],
            key=lambda f: os.path.getmtime(os.path.join(SCORES_DIR, f)),
            reverse=True,
        )
        return [{"label": f[:-5], "value": f} for f in files]
    except Exception:
        return []


@app.callback(
    Output("score-dropdown", "options"),
    Input("score-store-status", "children"),
    Input("url", "pathname"),
)
def refresh_score_list(_, __):
    return _list_scores()


@app.callback(
    Output("score-name-input", "style"),
    Input("score-save-btn", "n_clicks"),
    State("score-name-input", "style"),
    prevent_initial_call=True,
)
def toggle_name_input(n, current_style):
    if current_style and current_style.get("display") == "none":
        return {**current_style, "display": "block"}
    return {**current_style, "display": "none"}


@app.callback(
    Output("score-store-status", "children"),
    Output("score-name-input", "value"),
    Input("score-name-input", "value"),
    Input("score-load-btn",   "n_clicks"),
    State("score-dropdown",   "value"),
    prevent_initial_call=True,
)
def score_save_load(name, load_clicks, selected_file):
    import json as _json, shutil as _shutil
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    triggered = ctx.triggered[0]["prop_id"]

    if "score-name-input" in triggered and name:
        name = name.strip().replace("/", "-").replace(" ", "_")
        if not name:
            return "Invalid name.", ""
        if not os.path.exists(SCORE_PATH):
            return "Generate a score first.", ""
        dst = os.path.join(SCORES_DIR, f"{name}.json")
        _shutil.copy2(SCORE_PATH, dst)
        return f"✓ Salvata: {name}.json", ""

    if "score-load-btn" in triggered:
        if not selected_file:
            return "Select a score from the dropdown.", dash.no_update
        src_path = os.path.join(SCORES_DIR, selected_file)
        if not os.path.exists(src_path):
            return f"File non trovato: {selected_file}", dash.no_update
        _shutil.copy2(src_path, SCORE_PATH)
        with open(SCORE_PATH) as f:
            score = _json.load(f)
        n_g = len(score.get("gestures", []))
        n_e = sum(len(g.get("events", [])) for g in score.get("gestures", []))
        return f"✓ Loaded: {selected_file[:-5]}  ·  {n_g} fields  ·  {n_e} events", dash.no_update

    raise dash.exceptions.PreventUpdate


# Propagate click from score-btn (home-page) to score-btn-root (root DOM)
app.clientside_callback(
    "function(n) { return n || 0; }",
    Output("score-btn-root", "n_clicks"),
    Input("score-btn", "n_clicks"),
    prevent_initial_call=True,
)

if __name__ == "__main__":
    print("Avvio ConTimbre Explorer su http://127.0.0.1:8050")
    app.run(debug=False)
