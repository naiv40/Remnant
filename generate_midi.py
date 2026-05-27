"""
Remnant — MIDI Generator
========================
Reads brownian_score.json and the .cePlayerOrc files in scores/
and generates one .mid file per field.

Each event in the score is mapped to the MIDI key number of the
corresponding sound in the .cePlayerOrc file.

Usage:
    python3 generate_midi.py

Output:
    scores/remnant_field_01.mid, remnant_field_02.mid, ...

Dependencies:
    pip install midiutil
"""

import os
import re
import json
from midiutil import MIDIFile

# ─── Paths ───────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR = os.path.join(BASE_DIR, "scores")
SCORE_PATH = os.path.join(BASE_DIR, "brownian_score.json")

# ePlayer orchestra files: contimbre_brownian_gesto_NN.cePlayerOrc
# or contimbre_brownian_field_NN.cePlayerOrc
EPLAYER_DIR = os.path.join(
    "/Volumes/disk 1/conTimbre Standard V2",
    "algorithmic orchestration",
    "ePlayer orchestras"
)

# ─── Parse cePlayerOrc ────────────────────────────────────────────────────────

def parse_eplayer_orc(path):
    """Parse a .cePlayerOrc file and return a dict mapping
    sound filename (without extension) → MIDI key number.

    Real sounds are identified as keys whose filename differs
    from the most common filename (the padding sound).
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  WARNING: file not found: {path}")
        return {}

    # Extract all (number, filename) pairs
    keys = []
    blocks = re.findall(
        r'number:\s*(\d+).*?filename:\s*"([^"]+)"',
        content, re.DOTALL
    )
    for num_str, filename in blocks:
        keys.append((int(num_str), filename.strip()))

    if not keys:
        return {}

    # Find padding filename (most common)
    from collections import Counter
    filenames = [f for _, f in keys]
    padding_fname = Counter(filenames).most_common(1)[0][0]

    # Real sounds = keys with a different filename
    real_keys = [(num, fname) for num, fname in keys if fname != padding_fname]

    # Build mapping: sound_id (filename without path) → midi_note
    mapping = {}
    for num, fname in real_keys:
        # Normalise: strip path separators, use as-is
        sound_id = fname.strip()
        mapping[sound_id] = num

    return mapping


def find_eplayer_file(field_idx):
    """Find the .cePlayerOrc file for a given field index (0-based).
    Tries both 'gesto' and 'field' naming conventions.
    """
    candidates = [
        os.path.join(EPLAYER_DIR,
            f"contimbre_brownian_gesto_{field_idx+1:02d}.cePlayerOrc"),
        os.path.join(EPLAYER_DIR,
            f"contimbre_brownian_field_{field_idx+1:02d}.cePlayerOrc"),
        os.path.join(SCORES_DIR,
            f"contimbre_brownian_gesto_{field_idx+1:02d}.cePlayerOrc"),
        os.path.join(SCORES_DIR,
            f"contimbre_brownian_field_{field_idx+1:02d}.cePlayerOrc"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# ─── MIDI generation ─────────────────────────────────────────────────────────

def generate_midi_for_field(field, sound_to_midi, bpm, field_idx):
    """Generate a MIDIFile for one field.

    Each event becomes a note_on at its exact time (in beats),
    with duration proportional to dur_vis (min 0.25 beats).
    """
    events = field.get("events", [])
    if not events:
        print(f"  Field {field_idx+1}: no events, skipping.")
        return None

    beat_sec    = 60.0 / bpm
    t_start     = field.get("t_start", 0)
    dur_min_sec = 0.3   # minimum note duration in seconds

    midi = MIDIFile(1)
    midi.addTempo(0, 0, bpm)
    midi.addTrackName(0, 0, f"Remnant field {field_idx+1}")

    n_mapped   = 0
    n_unmapped = 0

    for ev in events:
        sound_id = ev.get("id", "")
        t_sec    = ev.get("t", t_start) - t_start  # relative to field start
        tension  = ev.get("tension", 0.5)

        # Duration: from tension (0.3s → 2.0s)
        dur_sec  = dur_min_sec + tension * 1.7
        t_beat   = t_sec / beat_sec
        dur_beat = max(dur_sec / beat_sec, 0.25)

        # Velocity from tension (40–110)
        velocity = int(40 + tension * 70)

        # Find MIDI note
        midi_note = sound_to_midi.get(sound_id)

        if midi_note is None:
            # Try partial match on sound_id
            for key, val in sound_to_midi.items():
                if sound_id in key or key in sound_id:
                    midi_note = val
                    break

        if midi_note is None:
            print(f"  WARNING: no MIDI key for sound '{sound_id}'")
            n_unmapped += 1
            continue

        midi.addNote(0, 0, midi_note, t_beat, dur_beat, velocity)
        n_mapped += 1

    print(f"  Field {field_idx+1}: {n_mapped} notes mapped, {n_unmapped} unmapped")
    return midi


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Remnant MIDI Generator")
    print("=" * 40)

    if not os.path.exists(SCORE_PATH):
        print(f"ERROR: score not found at {SCORE_PATH}")
        print("Generate a composition and click 'Generate score' first.")
        return

    with open(SCORE_PATH) as f:
        score = json.load(f)

    fields  = score.get("gestures", [])
    bpm     = score.get("bpm", 60)
    dur_tot = score.get("duration", 120)

    print(f"Score: {len(fields)} fields, {dur_tot}s, BPM {bpm}")
    print()

    os.makedirs(SCORES_DIR, exist_ok=True)
    n_generated = 0

    for field in fields:
        idx      = field.get("index", 0)
        orc_path = find_eplayer_file(idx)

        if orc_path is None:
            print(f"Field {idx+1}: no .cePlayerOrc found — export for ePlayer first.")
            continue

        print(f"Field {idx+1}: reading {os.path.basename(orc_path)}")
        sound_to_midi = parse_eplayer_orc(orc_path)

        if not sound_to_midi:
            print(f"  WARNING: no sounds parsed from {orc_path}")
            continue

        print(f"  {len(sound_to_midi)} unique sounds mapped")

        midi = generate_midi_for_field(field, sound_to_midi, bpm, idx)
        if midi is None:
            continue

        out_path = os.path.join(SCORES_DIR, f"remnant_field_{idx+1:02d}.mid")
        with open(out_path, "wb") as f:
            midi.writeFile(f)

        print(f"  → {out_path}")
        n_generated += 1

    print()
    print("=" * 40)
    if n_generated > 0:
        print(f"Generated {n_generated} MIDI file(s) in {SCORES_DIR}/")
    else:
        print("No MIDI files generated.")
        print("Make sure you have:")
        print("  1. Generated a composition and clicked 'Generate score'")
        print("  2. Exported for ePlayer (the .cePlayerOrc files)")


if __name__ == "__main__":
    main()
