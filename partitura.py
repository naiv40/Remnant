"""
ConTimbre — Partitura Grafica
Legge /tmp/brownian_score.json e genera una partitura grafica:
  asse X = tempo (secondi)
  asse Y = angolo azimutale (0-360 gradi)
  colore = gesto
  dimensione punto = tensione timbrica
  larghezza barra = durata (modulata da inviluppo SVG)
  opacità = dinamica (modulata da inviluppo SVG)
  etichetta = nome strumento

Inviluppi SVG OpenMusic (opzionali):
  ~/Desktop/remnant/envelopes/gesto_01.svg, gesto_02.svg, ...
  La curva modula onset, durata e dinamica per ogni gesto.
"""

import json
import re
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import sys
import os

SCORE_PATH     = os.path.expanduser("~/Desktop/remnant/brownian_score.json")
ENVELOPE_DIR   = os.path.expanduser("~/Desktop/remnant/envelopes")
os.makedirs(ENVELOPE_DIR, exist_ok=True)

if not os.path.exists(SCORE_PATH):
    print(f"File non trovato: {SCORE_PATH}")
    sys.exit(1)

with open(SCORE_PATH) as f:
    score = json.load(f)

gestures   = score["gestures"]
duration   = score["duration"]
bpm        = score.get("bpm", 60)
n_gestures = len(gestures)

beat_sec  = 60.0 / bpm
dur_scale = score.get("dur_scale", 1.0)
dur_min   = 0.5 * dur_scale
dur_max   = 8.0 * dur_scale

GESTURE_PALETTE = [
    "#E24B4A","#378ADD","#1D9E75","#BA7517","#7F77DD",
    "#D85A30","#185FA5","#0F6E56","#854F0B","#534AB7",
    "#993C1D","#0C447C","#085041","#633806","#3C3489",
]

LACHENMANN_COLORS = {
    "Neutro":    "#888888",
    "Klang":     "#4A90D9",
    "Farbklang": "#5CB85C",
    "Geräusch":  "#E05C5C",
    "Kadenz":    "#BA7517",
    "Textur":    "#9B59B6",
    "Stille":    "#CCCCCC",
}

# ─── Inviluppi SVG ────────────────────────────────────────────────────────────

def parse_om_svg(path):
    """Estrae punti normalizzati [(t, v)] da un SVG OpenMusic.
    x → t (0→1), y → v (0→1, invertito perché SVG y↓).
    """
    try:
        with open(path) as f:
            svg = f.read()
    except FileNotFoundError:
        return None
    matches = re.findall(r'[ML]\s*([\d.]+)\s+([\d.]+)', svg)
    if not matches:
        return None
    pts = [(float(x), float(y)) for x, y in matches]
    xs  = [p[0] for p in pts]
    ys  = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0 or y1 == y0:
        return None
    normalized = [((x - x0) / (x1 - x0), 1.0 - (y - y0) / (y1 - y0)) for x, y in pts]
    return sorted(normalized, key=lambda p: p[0])


def envelope_value(t, envelope):
    """Interpolazione lineare dell'inviluppo al tempo t (0→1)."""
    if not envelope:
        return 1.0
    if t <= envelope[0][0]:
        return envelope[0][1]
    if t >= envelope[-1][0]:
        return envelope[-1][1]
    for i in range(len(envelope) - 1):
        t0, v0 = envelope[i]
        t1, v1 = envelope[i + 1]
        if t0 <= t <= t1:
            alpha = (t - t0) / (t1 - t0)
            return v0 + alpha * (v1 - v0)
    return 1.0


# Carica inviluppi per ogni gesto
envelopes = {}
for g in gestures:
    idx  = g["index"]
    path = os.path.join(ENVELOPE_DIR, f"gesto_{idx+1:02d}.svg")
    env  = parse_om_svg(path)
    if env:
        envelopes[idx] = env
        print(f"Inviluppo G{idx+1}: {len(env)} punti")
    else:
        print(f"Inviluppo G{idx+1}: non trovato, curva piatta")

# ─── Disegno ──────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(1, 1, figsize=(20, 10))
fig.patch.set_facecolor("#FAFAFA")
ax.set_facecolor("#FAFAFA")

# Griglia azimutale
for deg in [0, 45, 90, 135, 180, 225, 270, 315, 360]:
    ax.axhline(deg, color="#EEEEEE", linewidth=0.5, zorder=0)
    ax.text(-duration * 0.012, deg, f"{deg}°",
            fontsize=7, color="#BBBBBB", va="center", ha="right",
            fontfamily="monospace")

legend_handles = []
seen = set()

for g in gestures:
    idx     = g["index"]
    color   = GESTURE_PALETTE[idx % len(GESTURE_PALETTE)]
    t_start = g.get("t_start", 0)
    t_end   = g.get("t_end", duration)
    env     = envelopes.get(idx)
    cat     = g.get("lachenmann", "Neutro")
    lach_color = LACHENMANN_COLORS.get(cat, "#888")

    # Sfondo gesto
    ax.axvspan(t_start, t_end, alpha=0.04, color=color, zorder=0)

    # Etichetta gesto + categoria Lachenmann
    ax.text((t_start + t_end) / 2, 378,
            f"G{idx+1}", fontsize=8, color=color,
            ha="center", va="bottom", fontfamily="monospace", fontweight="bold")
    ax.text((t_start + t_end) / 2, 370,
            cat, fontsize=6, color=lach_color,
            ha="center", va="bottom", fontfamily="monospace")

    events = g["events"]
    n_ev   = len(events)

    # Disegna inviluppo SVG come curva sottile sopra la banda del gesto
    if env:
        env_y_base = 365
        env_y_range = 8
        t_env = [t_start + (t_end - t_start) * pt[0] for pt in env]
        v_env = [env_y_base + pt[1] * env_y_range for pt in env]
        ax.plot(t_env, v_env, color=color, linewidth=0.8, alpha=0.5, zorder=1)

    for i, ev in enumerate(events):
        t       = ev["t"]
        azimuth = ev["azimuth"]
        label   = ev["instrument"]
        mode    = ev.get("mode", "")
        label_full = f"{label}" + (f"\n{mode}" if mode else "")
        tension = ev.get("tension", 0.5)

        # Posizione relativa nell'inviluppo (0→1 dentro il gesto)
        t_rel = (t - t_start) / max(t_end - t_start, 0.001)
        env_v = envelope_value(t_rel, env)  # 0→1

        # Onset: offset temporale aggiuntivo proporzionale all'inviluppo
        # (env_v alto = attacco più netto, env_v basso = attacco più ritardato)
        onset_offset = (1.0 - env_v) * (t_end - t_start) / max(n_ev * 2, 1)
        t_draw = t + onset_offset

        # Durata visiva: barra orizzontale
        dur_visual = dur_min + env_v * (dur_max - dur_min)

        # Dinamica: opacità e dimensione
        alpha_ev = 0.3 + env_v * 0.65   # 0.3 (pp) → 0.95 (ff)
        size     = (40 + tension * 80) * (0.4 + env_v * 0.6)

        # Barra durata
        ax.plot([t_draw, t_draw + dur_visual], [azimuth, azimuth],
                color=color, linewidth=1.5 + env_v * 2.5,
                alpha=alpha_ev * 0.6, zorder=3, solid_capstyle="round")

        # Punto onset
        ax.scatter(t_draw, azimuth, s=size, color=color, zorder=4,
                   alpha=alpha_ev, edgecolors="white", linewidths=0.6)

        # Etichetta
        offset_y = 8 if i % 2 == 0 else -14
        ax.annotate(label_full, xy=(t_draw, azimuth),
                    xytext=(4, offset_y), textcoords="offset points",
                    fontsize=6, color=color, fontfamily="monospace",
                    alpha=alpha_ev * 0.9, zorder=5)

    if idx not in seen:
        seen.add(idx)
        env_marker = " ∿" if env else ""
        legend_handles.append(
            mpatches.Patch(color=color,
                           label=f"G{idx+1}{env_marker}  {t_start:.1f}s–{t_end:.1f}s  "
                                 f"{cat}  tensione={g.get('tension',0.5)}"))

ax.set_xlim(-duration * 0.02, duration * 1.05)
ax.set_ylim(-20, 395)
ax.set_xlabel("Tempo (secondi)", fontsize=10, fontfamily="monospace", color="#555555")
ax.set_ylabel("Posizione azimutale (gradi)", fontsize=10, fontfamily="monospace", color="#555555")
ax.set_title("Partitura Grafica — Spazio Timbrico e Collocazione Spaziale",
             fontsize=13, fontfamily="Georgia", color="#111111", pad=14)
ax.tick_params(colors="#AAAAAA", labelsize=8)
for spine in ax.spines.values():
    spine.set_edgecolor("#DDDDDD")

ax.legend(handles=legend_handles, loc="lower right", fontsize=7,
          framealpha=0.9, edgecolor="#DDDDDD",
          prop={"family": "monospace", "size": 7})

# Legenda parametri inviluppo
ax.text(duration * 1.01, 200,
        "∿ inviluppo SVG\n→ onset · durata · dinamica",
        fontsize=7, color="#AAAAAA", fontfamily="monospace", va="center")

plt.tight_layout()
out = "/Users/ivan/Desktop/remnant/partitura.png"
plt.savefig(out, dpi=180, bbox_inches="tight", facecolor="#FAFAFA")
print(f"Partitura salvata in {out}")
plt.show()

