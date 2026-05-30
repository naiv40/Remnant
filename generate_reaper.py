"""
Remnant — Reaper Project Generator  v3
========================================
Reads brownian_score.json + scores/contimbre_remnant.cePlayerOrc
and generates:

  scores/remnant.rpp   — one MIDI track per field, Program Change before
                         each field's events to select the right program
  scores/setup.txt     — ePlayer setup guide

ePlayer setup (one-time):
  1. Add ePlayer on a new "ePlayer" track in Reaper
  2. Load scores/contimbre_remnant.cePlayerOrc
  3. Route all MIDI tracks → ePlayer track via MIDI send
  4. Save project

MIDI Program Change mapping:
  Field 1 → Program Change 0
  Field 2 → Program Change 1
  ...

Usage:
    python3 generate_reaper.py

Dependencies: none (stdlib only)
"""

import os
import re
import json
import uuid
import base64

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SCORES_DIR  = os.path.join(BASE_DIR, "scores")
SCORE_PATH  = os.path.join(BASE_DIR, "brownian_score.json")
ORC_PATH    = os.path.join(SCORES_DIR, "contimbre_remnant.cePlayerOrc")
RPP_PATH    = os.path.join(SCORES_DIR, "remnant.rpp")
SETUP_PATH  = os.path.join(SCORES_DIR, "setup.txt")

# ─── Parse .cePlayerOrc ───────────────────────────────────────────────────────

def parse_programs(orc_path):
    """Return list of program names in order from a .cePlayerOrc file."""
    if not os.path.exists(orc_path):
        return []
    with open(orc_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return re.findall(r'name:\s*"([^"]+)"', content)


def parse_sound_to_midi(orc_path):
    """Return dict: filename → MIDI key.

    The .cePlayerOrc format repeats a padding filename for the first N voices,
    then lists the real sounds (also starting from key 0).
    We skip the leading run of identical filenames to find where real sounds begin,
    then map each unique filename to its MIDI key number.
    """
    if not os.path.exists(orc_path):
        return {}
    with open(orc_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    blocks = re.findall(
        r'number:\s*(\d+).*?filename:\s*"([^"]+)"',
        content, re.DOTALL
    )
    keys = [(int(n), fname.strip()) for n, fname in blocks]
    if not keys:
        return {}

    # Deduplicazione per filename — tiene la prima occorrenza di ogni suono.
    # Non esclude padding: ogni filename unico e' un suono valido.
    seen, mapping = set(), {}
    for num, fname in keys:
        if fname not in seen:
            seen.add(fname)
            mapping[fname] = num
    return mapping


# ─── MIDI note lookup ─────────────────────────────────────────────────────────

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


# ─── MIDI events for one field ────────────────────────────────────────────────

def field_to_midi_events(field, sound_to_midi, bpm, program_number):
    """
    Returns (length_seconds, list_of_reaper_event_strings).
    Prepends a MIDI Program Change to select the field's program.
    All events on channel 0 (MIDI CH1).
    TPQ = 960.
    """
    events   = field.get("events", [])
    TPQ      = 960
    beat_sec = 60.0 / max(bpm, 1)
    t_start  = field.get("t_start", 0)
    DUR_MIN, DUR_MAX = 0.4, 7.0
    ch = 0  # single channel, program change selects the field

    raw = []  # (abs_tick, bytes)

    # Program Change at tick 0
    raw.append((0, bytes([0xC0 | ch, program_number & 0x7F, 0x00])))

    for ev in events:
        sound_id = ev.get("id", "")
        t_abs    = ev.get("t", t_start)
        tension  = float(ev.get("tension", 0.5))
        azimuth  = float(ev.get("azimuth", 180.0))

        tick     = int(round(((t_abs - t_start) / beat_sec) * TPQ))
        dur_tick = max(int(round(
            ((DUR_MIN + tension * (DUR_MAX - DUR_MIN)) / beat_sec) * TPQ)), 120)
        vel      = max(1, min(127, int(40 + tension * 70)))
        pan      = max(0, min(127, int((azimuth / 360.0) * 127)))
        expr     = max(0, min(127, int(tension * 127)))

        midi_note = find_midi_note(sound_id, sound_to_midi)
        if midi_note is None:
            continue

        raw.append((tick,            bytes([0xB0 | ch, 0x0A, pan])))
        raw.append((tick,            bytes([0xB0 | ch, 0x0B, expr])))
        raw.append((tick,            bytes([0x90 | ch, midi_note, vel])))
        raw.append((tick + dur_tick, bytes([0x80 | ch, midi_note, vel])))

    if len(raw) <= 1:  # only program change, no notes
        return 1.0, []

    raw.sort(key=lambda x: x[0])

    lines = []
    prev  = 0
    for abs_tick, b in raw:
        delta = abs_tick - prev
        prev  = abs_tick
        # Program change is 2 bytes of data in MIDI but Reaper uses 3 fields
        if b[0] & 0xF0 == 0xC0:
            lines.append(f"        E {delta} {b[0]:02x} {b[1]:02x} 00")
        else:
            lines.append(f"        E {delta} {b[0]:02x} {b[1]:02x} {b[2]:02x}")

    last_tick = raw[-1][0]
    lines.append(f"        E {last_tick - prev + 480} {0xB0|ch:02x} 7b 00")

    length_sec = ((last_tick + 480) / TPQ) * beat_sec
    return length_sec, lines


# ─── GUID + colors ────────────────────────────────────────────────────────────

def guid():
    return str(uuid.uuid4()).upper()

COLORS = [5963007, 2263842, 5592405, 10066329, 8388608,
          32768, 255, 8388736, 8421376, 8421504,
          16711935, 65535, 16776960, 16744448, 13421772, 6710886]


# ─── ePlayer master track (track index 0, no plugin yet) ─────────────────────

def make_eplayer_track(field_guids):
    """
    Creates the ePlayer master track (first in the project).
    Receives MIDI from all field tracks via AUXRECV blocks.
    field_guids: list of (track_guid, color_idx) for each field track.
    Number of AUXRECV blocks = number of fields in the score.
    """
    t_guid = guid()
    auxrecv_lines = "\n".join(
        f"    AUXRECV {i + 1} 0 1 0 0 0 0 0 {i} {i}"
        for i, _ in enumerate(field_guids)
    )

    return t_guid, f"""  <TRACK {{{t_guid}}}
    NAME "ePlayer"
    PEAKCOL 16711422
    BEAT -1
    AUTOMODE 0
    PANLAWFLAGS 3
    VOLPAN 1 0 -1 -1 1
    MUTESOLO 0 0 0
    IPHASE 0
    PLAYOFFS 0 1
    ISBUS 0 0
    BUSCOMP 0 0 0 0 0
    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0
    SEL 0
    REC 0 0 1 0 0 0 0 0
    VU 2
    TRACKHEIGHT 80 0 0 0 0 0 0
    NCHAN 2
    FX 1
    TRACKID {{{t_guid}}}
    PERF 0
    MIDIOUT -1
    MAINSEND 1 0
{auxrecv_lines}
  >"""


# ─── Build one MIDI field track ───────────────────────────────────────────────

def make_track(field, sound_to_midi, bpm, program_number, color_idx):
    idx      = field.get("index", 0)
    name     = f"Field {idx + 1}"
    t_guid   = guid()
    i_guid   = guid()
    s_guid   = guid()
    p_guid   = guid()
    color    = COLORS[color_idx % len(COLORS)]

    length_sec, event_lines = field_to_midi_events(
        field, sound_to_midi, bpm, program_number)
    length_sec = max(length_sec, 1.0)
    events_str = "\n".join(event_lines)

    name_b64 = base64.b64encode(
        bytes([0xFF, 0x03]) + name.encode()).decode()

    return t_guid, f"""  <TRACK {{{t_guid}}}
    NAME "{name}"
    PEAKCOL {color}
    BEAT -1
    AUTOMODE 0
    PANLAWFLAGS 3
    VOLPAN 1 0 -1 -1 1
    MUTESOLO 0 0 0
    IPHASE 0
    PLAYOFFS 0 1
    ISBUS 0 0
    BUSCOMP 0 0 0 0 0
    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0
    SEL 0
    REC 0 0 1 0 0 0 0 0
    VU 2
    TRACKHEIGHT 80 0 0 0 0 0 0
    NCHAN 2
    FX 0
    TRACKID {{{t_guid}}}
    PERF 0
    MIDIOUT -1
    MAINSEND 0 0
    <ITEM
      POSITION 0
      SNAPOFFS 0
      LENGTH {length_sec:.6f}
      LOOP 0
      ALLTAKES 0
      FADEIN 1 0 0 1 0 0 0
      FADEOUT 1 0 0 1 0 0 0
      MUTE 0 0
      SEL 1
      IGUID {{{i_guid}}}
      IID {idx + 1}
      NAME "{name}"
      VOLPAN 1 0 1 -1
      SOFFS 0 0
      PLAYRATE 1 1 0 -1 0 0.0025
      CHANMODE 0
      GUID {{{s_guid}}}
      <SOURCE MIDI
        HASDATA 1 960 QN
        CCINTERP 32
        POOLEDEVTS {{{p_guid}}}
        <X 0 0 0 0 3 "{name}"
          {name_b64}
        >
{events_str}
        CCINTERP 32
        CHASE_CC_TAKEOFFS 1
        GUID {{{s_guid}}}
        IGNTEMPO 0 {bpm} 4 4
        SRCCOLOR {color_idx + 20}
        EVTFILTER 0 -1 -1 -1 -1 0 0 0 0 -1 -1 -1 -1 0 -1 0 -1 -1
      >
    >
  >"""


# ─── RPP wrapper ──────────────────────────────────────────────────────────────

def make_rpp(tracks_str, bpm):
    return f"""<REAPER_PROJECT 0.1 "7.69/OSX64-clang" 0 0
  <NOTES 0 2
  >
  RIPPLE 0 0
  AUTOXFADE 4488
  ENVATTACH 1
  PANLAW 0.59566214
  PROJOFFS 0 0 0
  GRID 3455 8 1 8 1 0 0 0
  TIMEMODE 1 5 -1 30 0 0 -1 0
  PANMODE 5
  CURSOR 0
  ZOOM 100 0 0
  SAMPLERATE 48000 0 0
  TEMPO {bpm} 4 4 0
  PLAYRATE 1 0 0.25 4
  SELECTION 0 0
  MASTERAUTOMODE 0
  MASTERTRACKHEIGHT 0 0
  MASTERPEAKCOL 16576
  MASTER_NCH 2 2
  MASTER_VOLUME 1 0 -1 -1 1
  MASTER_PANMODE 3
  MASTER_FX 1
  MASTER_SEL 0
  <PROJBAY
  >
{tracks_str}
  <EXTENSIONS
  >
>
"""


# ─── Setup guide ──────────────────────────────────────────────────────────────

def make_setup(fields_info, orc_name, bpm):
    lines = [
        "REMNANT — ePlayer Setup Guide",
        "=" * 48,
        "",
        "One ePlayer instance, one voice, N programs.",
        f"Orchestra file: {orc_name}",
        f"BPM: {bpm}",
        "",
        "In Reaper:",
        "  1. Create a new track named 'ePlayer'",
        "  2. Add ePlayer as VSTi on that track",
        f"  3. Load {orc_name}",
        "  4. For each MIDI track: right-click → MIDI send → ePlayer track",
        "  5. Save the project",
        "",
        "MIDI Program Change mapping:",
        "",
        f"  {'Field':<8} {'Program':<10} {'ePlayer program name'}",
        f"  {'─────':<8} {'───────':<10} {'────────────────────'}",
    ]
    for idx, prog_num, prog_name in fields_info:
        lines.append(f"  Field {idx:<3}  PC {prog_num:<7}  {prog_name}")
    lines += [
        "",
        "Each MIDI track already contains a Program Change at beat 0.",
        "ePlayer will switch program automatically when Reaper plays",
        "each track.",
        "",
        "Note: ePlayer must have 'Chase CC/PC' enabled to switch",
        "programs correctly during playback.",
    ]
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Remnant Reaper Project Generator  v3")
    print("=" * 48)

    if not os.path.exists(SCORE_PATH):
        print(f"ERROR: score not found at {SCORE_PATH}")
        return

    with open(SCORE_PATH) as f:
        score = json.load(f)

    fields  = score.get("gestures", [])
    bpm     = score.get("bpm", 60)
    dur_tot = score.get("duration", 120)

    print(f"Score: {len(fields)} fields  ·  {dur_tot}s  ·  BPM {bpm}")

    # Load orchestra
    orc_name     = os.path.basename(ORC_PATH)
    sound_to_midi = parse_sound_to_midi(ORC_PATH)
    programs      = parse_programs(ORC_PATH)

    if not sound_to_midi:
        print(f"WARNING: {orc_name} not found or empty.")
        print("Run 'Export for ePlayer' in Remnant first, then re-run this script.")
    else:
        print(f"Orchestra: {len(sound_to_midi)} sounds, {len(programs)} programs")

    print()
    os.makedirs(SCORES_DIR, exist_ok=True)

    track_blocks = []
    fields_info  = []
    field_guids  = []

    # Build field tracks first to collect GUIDs for routing
    for prog_num, field in enumerate(fields):
        display_num = prog_num + 1
        prog_name   = programs[prog_num] if prog_num < len(programs) else f"field_{display_num:02d}"
        n_sounds    = len([e for e in field.get("events", [])
                           if find_midi_note(e.get("id",""), sound_to_midi) is not None])

        print(f"Field {display_num}  PC{prog_num}  {prog_name}  ({n_sounds} notes mapped)")

        # Sovrascrive index con prog_num così make_track usa sempre 0-based
        field["index"] = prog_num
        t_guid, block = make_track(field, sound_to_midi, bpm, prog_num, prog_num)
        track_blocks.append(block)
        field_guids.append((t_guid, prog_num))
        fields_info.append((display_num, prog_num, prog_name))

    # Build ePlayer master track (first) with AUXRECV from all field tracks
    _, eplayer_block = make_eplayer_track(field_guids)

    # ePlayer first, then field tracks
    all_tracks = "\n".join([eplayer_block] + track_blocks)
    rpp = make_rpp(all_tracks, bpm)
    with open(RPP_PATH, "w", encoding="utf-8") as f:
        f.write(rpp)

    setup = make_setup(fields_info, orc_name, bpm)
    with open(SETUP_PATH, "w", encoding="utf-8") as f:
        f.write(setup)

    print()
    print("=" * 48)
    print(f"→ {RPP_PATH}")
    print(f"→ {SETUP_PATH}")
    print()
    print("Open remnant.rpp in Reaper, follow setup.txt for ePlayer.")


if __name__ == "__main__":
    main()
