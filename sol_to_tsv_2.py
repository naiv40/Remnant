"""
Remnant — SOL 0.9 HQ DB → TSV
Legge il file .spectrum.db di SOL, calcola descrittori spettrali
(centroide, complessità, spread) e li esporta come TSV per umap_full.py.

Uso: python3 sol_to_tsv.py
Output: ~/Desktop/remnant/sol_coords_input.tsv
"""

import os
import re
import numpy as np
import pandas as pd

DB_PATH  = "/Volumes/disk 1/SOL_0.9_HQ 2.spectrum.db"
SOL_BASE = "/Volumes/disk 1/SOL_0.9_HQ 2"
OUT_TSV  = os.path.expanduser("~/Desktop/remnant/sol_coords_input.tsv")

# Cache cartelle strumento: "Violoncello" -> "07_Violoncello"
import glob as _glob
_instr_map = {}
for _fam_dir in _glob.glob(SOL_BASE + "/*/"):
    for _instr_dir in _glob.glob(_fam_dir + "*/"):
        _folder = os.path.basename(_instr_dir.rstrip("/"))
        _clean  = re.sub(r"^\d+_", "", _folder)
        _instr_map[_clean] = _folder
print(f"Instrument folder map: {len(_instr_map)} entries")

# ── Parsing pitch ─────────────────────────────────────────────────────────────
NOTE_RE = re.compile(r'([A-Ga-g][#b]?)(\d+)')
NOTE_MAP = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}

def pitch_to_midi(pitch_str):
    """Converte 'A#4' in MIDI note number."""
    m = NOTE_RE.match(pitch_str)
    if not m:
        return -1000
    note, octave = m.group(1), int(m.group(2))
    n = NOTE_MAP.get(note[0].upper(), 0)
    if len(note) > 1:
        n += 1 if note[1] == '#' else -1
    return (octave + 1) * 12 + n

DYNAMIC_MAP = {"ppp":1,"pp":2,"p":3,"mp":4,"mf":5,"f":6,"ff":7,"fff":8}

# ── Leggi header per ottenere parametri FFT ───────────────────────────────────
with open(DB_PATH, 'r', errors='replace') as f:
    header = f.readline().strip()

# header: "spectrum 4096 2048 1024"
parts  = header.split()
N_FFT  = int(parts[1]) if len(parts) > 1 else 4096
SR     = 44100
freqs  = np.fft.rfftfreq(N_FFT, 1.0/SR)[:1024]

print(f"DB: {DB_PATH}")
print(f"FFT size: {N_FFT}, freq bins: {len(freqs)}")

# ── Processa righe ────────────────────────────────────────────────────────────
rows = []
skipped = 0

with open(DB_PATH, 'r', errors='replace') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('spectrum'):
            continue

        parts = line.split(';')
        if len(parts) < 10:
            skipped += 1
            continue

        path   = parts[0]          # /Brass/01_Horn/brassy/Hn-brassy-A#2-ff.wav
        spec   = np.array([float(v) for v in parts[1:] if v], dtype=np.float32)

        # ── Estrai metadati dal path ──────────────────────────────────────────
        path_parts = path.strip('/').split('/')
        # path_parts: [Family, Instrument, Technique, filename]
        family     = path_parts[0] if len(path_parts) > 0 else "Unknown"
        instrument = path_parts[1] if len(path_parts) > 1 else "Unknown"
        technique  = path_parts[2] if len(path_parts) > 2 else "Unknown"
        filename   = path_parts[-1].replace('.wav', '')

        # Parsea filename: Vn-ord-A#4-ff-2c → strumento, tecnica, pitch, dyn
        fname_parts = filename.split('-')
        pitch_str   = ""
        dynamic_str = ""
        for p in fname_parts:
            if NOTE_RE.match(p):
                pitch_str = p
            elif p.lower() in DYNAMIC_MAP:
                dynamic_str = p.lower()

        midi_pitch = pitch_to_midi(pitch_str) if pitch_str else -1000
        dyn_num    = DYNAMIC_MAP.get(dynamic_str, 0)

        # ── Descrittori spettrali dal vettore FFT ────────────────────────────
        f_bins = freqs[:len(spec)]
        power  = spec ** 2 + 1e-10
        total  = power.sum()

        centroid   = float(np.sum(f_bins * power) / total)
        spread     = float(np.sqrt(np.sum(((f_bins - centroid)**2) * power) / total))
        # Flatness = media geometrica / media aritmetica (complessità spettrale)
        log_mean   = float(np.exp(np.mean(np.log(power + 1e-10))))
        arith_mean = float(np.mean(power))
        flatness   = log_mean / (arith_mean + 1e-10)

        # Verifica esistenza file audio su disco
        _instr_folder = _instr_map.get(instrument, instrument)
        _wav = os.path.join(SOL_BASE, family, _instr_folder, technique, filename + ".wav")
        if not os.path.exists(_wav):
            skipped += 1
            continue

        rows.append({
            "id":                  filename,
            "instrument":          instrument,
            "family":              family,
            "technique":           technique,
            "pitch":               midi_pitch,
            "dynamic":             dynamic_str or "mf",
            "dynamic_num":         dyn_num,
            "spectral_center":     round(centroid, 2),
            "spectral_complexity": round(float(flatness), 5),
            "spectral_spread":     round(spread, 2),
            "duration":            0.0,   # non disponibile nel DB
            "absolute_intensity":  round(float(spec.mean()), 4),
        })

        if len(rows) % 2000 == 0:
            print(f"  {len(rows)} / ~24900")

df = pd.DataFrame(rows)
df.to_csv(OUT_TSV, sep="\t", index=False)
print(f"\nSaved: {OUT_TSV}  ({len(df)} suoni, {skipped} saltati)")
print("Next: python3 umap_full.py  (con TSV_PATH = OUT_TSV)")
print("  oppure modifica UMAP_ORIG_PATH in contimbre_explorer.py")
