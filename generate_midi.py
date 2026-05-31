"""
Remnant — MIDI Generator  v2
=============================
Reads brownian_score.json and the .cePlayerOrc files in scores/
and generates ONE .mid file with one track per field.

Track N  →  MIDI channel N  (Field 1 = CH1, Field 2 = CH2, … max 16)

In Reaper:
  • Load remnant.mid
  • Each track → MIDI send to ePlayer on the corresponding channel
  • ePlayer set to receive on "All channels" (Omni) or per-channel
  • SC listens on the same MIDI port and uses channel number to know
    which field is currently active (for gate / processing activation)

MIDI layout per event:
  Note      = sound key from .cePlayerOrc
  Velocity  = tension → 40-110
  Duration  = DUR_MIN + tension * DUR_MAX (beats)
  CC10 pan  = azimuth → 0 (left) … 127 (right)   [stereo reference only]
  CC11 expr = tension → 0-127                      [available for ePlayer gain]

Usage:
    python3 generate_midi.py

Output:
    scores/remnant.mid

Dependencies:
    pip install midiutil
"""

import os
import re
import json
from midiutil import MIDIFile

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR = os.path.join(BASE_DIR, "scores")
SCORE_PATH = os.path.join(BASE_DIR, "brownian_score.json")
OUT_PATH   = os.path.join(SCORES_DIR, "remnant.mid")

MAX_MIDI_CHANNELS = 16

# ─── Parse .cePlayerOrc ───────────────────────────────────────────────────────

def parse_eplayer_orc(path):
    """Return dict: sound_filename → MIDI key number.
    Padding entries (key 0 filename repeated throughout) are excluded.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  WARNING: not found: {path}")
        return {}

    blocks = re.findall(
        r'number:\s*(\d+).*?filename:\s*"([^"]+)"',
        content, re.DOTALL
    )
    keys = [(int(n), fname.strip()) for n, fname in blocks]
    if not keys:
        return {}

    padding_fname = keys[0][1]
    seen    = set()
    mapping = {}
    for num, fname in keys:
        if fname != padding_fname and fname not in seen:
            seen.add(fname)
            mapping[fname] = num
    return mapping


def find_eplayer_file(field_idx):
    candidates = [
        os.path.join(SCORES_DIR, f"contimbre_brownian_field_{field_idx+1:02d}.cePlayerOrc"),
        os.path.join(SCORES_DIR, f"contimbre_brownian_gesto_{field_idx+1:02d}.cePlayerOrc"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# ─── Sound → MIDI key lookup ──────────────────────────────────────────────────

def find_midi_note(sound_id, sound_to_midi):
    note = sound_to_midi.get(sound_id)
    if note is not None:
        return note
    parts   = sound_id.split(".")
    prefix2 = ".".join(parts[:2]) if len(parts) >= 2 else sound_id
    prefix1 = parts[0] if parts else sound_id
    for key, val in sound_to_midi.items():
        if key.startswith(prefix2):
            return val
    for key, val in sound_to_midi.items():
        if key.startswith(prefix1 + "."):
            return val
    return None


# ─── Build one track ──────────────────────────────────────────────────────────

def write_field_track(midi, field, sound_to_midi, bpm, field_idx, track_idx=None):
    """Write events for one field into the MIDIFile object.

    track   = field_idx          (0-based)
    channel = field_idx % 16     (0-based, so Field 1 = CH1 in DAW = index 0 here)
    """
    events  = field.get("events", [])
    if not events:
        print(f"  Field {field_idx+1}: no events, skipping.")
        return 0

    track    = track_idx if track_idx is not None else field_idx
    channel  = field_idx % MAX_MIDI_CHANNELS   # 0-based for midiutil
    beat_sec = 60.0 / bpm
    t_start  = field.get("t_start", 0)

    DUR_MIN = 0.4
    DUR_MAX = 7.0

    midi.addTrackName(track, 0, f"Field {field_idx+1}")
    midi.addTempo(track, 0, bpm)

    n_mapped   = 0
    n_unmapped = 0

    for ev in events:
        sound_id = ev.get("id", "")
        t_abs    = ev.get("t", t_start)
        tension  = float(ev.get("tension", 0.5))
        azimuth  = float(ev.get("azimuth", 180.0))

        t_beat   = (t_abs - t_start) / beat_sec
        dur_sec  = DUR_MIN + tension * (DUR_MAX - DUR_MIN)
        dur_beat = max(dur_sec / beat_sec, 0.125)
        velocity = max(1, min(127, int(40 + tension * 70)))

        # CC10 pan: azimuth → stereo reference
        # 0° = L (0), 180° = C (63), 360° = R (127)
        pan_cc  = max(0, min(127, int((azimuth / 360.0) * 127)))

        # CC11 expression: tension → ePlayer gain/dynamic
        expr_cc = max(0, min(127, int(tension * 127)))

        midi_note = find_midi_note(sound_id, sound_to_midi)
        if midi_note is None:
            print(f"  WARNING field {field_idx+1}: no key for '{sound_id}'")
            n_unmapped += 1
            continue

        midi.addControllerEvent(track, channel, max(t_beat - 0.001, 0), 10, pan_cc)
        midi.addControllerEvent(track, channel, max(t_beat - 0.001, 0), 11, expr_cc)
        midi.addNote(track, channel, midi_note, t_beat, dur_beat, velocity)
        n_mapped += 1

    print(f"  Field {field_idx+1} → MIDI CH{channel+1}: "
          f"{n_mapped} notes, {n_unmapped} unmapped")
    return n_mapped


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Remnant MIDI Generator  v2")
    print("=" * 44)

    if not os.path.exists(SCORE_PATH):
        print(f"ERROR: score not found at {SCORE_PATH}")
        print("Generate a composition and click 'Generate score' first.")
        return

    with open(SCORE_PATH) as f:
        score = json.load(f)

    fields  = score.get("gestures", [])
    bpm     = score.get("bpm", 60)
    dur_tot = score.get("duration", 120)

    print(f"Score: {len(fields)} fields  ·  {dur_tot}s  ·  BPM {bpm}")
    print()

    if len(fields) > MAX_MIDI_CHANNELS:
        print(f"WARNING: {len(fields)} fields > 16 MIDI channels. "
              f"Fields 17+ will share channels (wrap around).")

    os.makedirs(SCORES_DIR, exist_ok=True)

    # One MIDIFile with N tracks (one per field)
    n_fields = len(fields)
    midi     = MIDIFile(n_fields)

    n_total = 0
    field_map = []   # for summary

    for track_idx, field in enumerate(fields):
        idx      = field.get("index", 0)
        # track_idx = contiguous 0-based track number in the MIDIFile
        # channel   = original field index (so Reaper CH matches field)
        orc_path = find_eplayer_file(idx)

        if orc_path is None:
            print(f"Field {idx+1}: no .cePlayerOrc — export for ePlayer first.")
            field_map.append((idx+1, idx % MAX_MIDI_CHANNELS + 1, 0))
            continue

        print(f"Field {idx+1}: {os.path.basename(orc_path)}")
        sound_to_midi = parse_eplayer_orc(orc_path)

        if not sound_to_midi:
            print(f"  WARNING: no sounds parsed.")
            field_map.append((idx+1, idx % MAX_MIDI_CHANNELS + 1, 0))
            continue

        print(f"  {len(sound_to_midi)} sounds mapped")
        n = write_field_track(midi, field, sound_to_midi, bpm, idx, track_idx)
        n_total += n
        field_map.append((idx+1, idx % MAX_MIDI_CHANNELS + 1, n))

    with open(OUT_PATH, "wb") as f:
        midi.writeFile(f)

    print()
    print("=" * 44)
    print(f"→ {OUT_PATH}")
    print(f"  {n_total} total notes  ·  {len(field_map)} tracks")
    print()
    print("  Field  MIDI CH  Notes")
    print("  ─────  ───────  ─────")
    for fld, ch, n in field_map:
        print(f"    {fld:2d}     CH{ch:2d}    {n:4d}")
    print()
    print("Reaper setup:")
    print("  1. Import remnant.mid")
    print("  2. Each track → MIDI output → ePlayer, channel as above")
    print("  3. SC receives same MIDI port → channel = active field")


if __name__ == "__main__":
    main()
