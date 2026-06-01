# Remnant

**Sonic traces of a non-human world**

A multichannel acousmatic composition and live electronics system for orchestra and 8-channel diffusion. The project navigates orchestral timbral space through Brownian motion. In concert, the electronics listen to the orchestra in real time, transforming its signal according to temporal directions that shape tension and release as narrative forces within sound.

Through electroacoustic processing, sounds are detached from their recognisable source and relocated within an artificial sonic environment: a space that does not document but hypothesises.

The project emerges from a biocentric perspective on the Anthropocene: instrumental sounds as traces of a world that continues to exist independently of human presence.

---

## Presentation video

[![Remnant — Sound Traces from a Non-Human World](https://img.youtube.com/vi/VLJJNfbaflw/maxresdefault.jpg)](https://youtu.be/VLJJNfbaflw)

---

## System overview

```
ConTimbre TSV corpus
    ↓  export_tsv.lisp  (SBCL)
contimbre_full.tsv
    ↓  umap_full.py  (McAdams perceptual weights)
umap_full_coords.csv
    ↓  contimbre_explorer.py  (Dash)
        ├─ Instrument family filter + local UMAP recomputation
        ├─ Multi-field Brownian motion with spectral diversity constraint
        ├─ Inter-field sound exclusion (no repeated sounds across fields)
        ├─ Interactive graphic score with proportional pulse grid
        ├─ Export .cOrc / .cePlayerOrc  (SBCL)
        └─ brownian_score.json  →  SuperCollider
                ├─ remnant_sc.scd      (boot, buses, groups, synths)
                ├─ remnant_conv.scd    (convolution engine, IR generation)
                ├─ remnant_flucos.scd  (FluCoMa real-time analysis)
                └─ remnant_hud.scd     (performance HUD)
```

---

## Dependencies

### Python
```bash
pip install -r requirements.txt
```

### SuperCollider
Requires SuperCollider ≥ 3.12 with FluCoMa Quark:
```supercollider
Quarks.install("FluCoMa");
// Restart SC after installation
```

### Audio routing
Requires [BlackHole](https://existential.audio/blackhole/) (16ch) configured as aggregate device with the audio interface. ePlayer sends field tracks to BlackHole; SuperCollider reads them as `SoundIn.ar([0,1,2,3])`.

### ConTimbre + SBCL
[ConTimbre Standard V2](https://www.contimbre.com) and [SBCL](http://www.sbcl.org) with Quicklisp must be installed and available in PATH.

---

## Setup

### 1. Extract the corpus
```bash
sbcl --load export_tsv.lisp
```
Writes `/tmp/contimbre_full.tsv`.

### 2. Compute UMAP coordinates
```bash
python3 umap_full.py
```
Generates `umap_full_coords.csv` in the project folder.

### 3. Launch Remnant Explorer
```bash
python3 contimbre_explorer.py
# → http://127.0.0.1:8050
```

### 4. Launch SuperCollider — launch order is mandatory
```
remnant_sc.scd      Block 1 (boot + buses + groups)
remnant_conv.scd    Block 1, 2, 3
remnant_flucos.scd
remnant_hud.scd     Block 1 (performance functions), Block 2 (HUD window)
```

---

## Workflow

### Composition (contimbre_explorer.py)
1. Select instrument families in the left panel
2. Click **Apply filter** — recomputes UMAP on the subset with McAdams perceptual weights
3. Set compositional parameters (duration per field, number of fields, Brownian steps)
4. Set **Spectral diversity** — minimum spectral centroid difference between consecutive events
5. Assign a **Temporal direction** to each field (Forward / Backward / Presence / Neutral)
6. Click **Generate composition**
7. Click **Generate score** — writes `brownian_score.json` and opens the graphic score
8. Click **Export for ePlayer** — generates `contimbre_remnant.cePlayerOrc`
9. Click **Export HTML score** — generates `~/Desktop/partitura_remnant.html` (navigable in browser, ← → or keys 1–9)

### Live performance (remnant_hud.scd)
All fields play simultaneously as a single body. The HUD is the only live interface.

**Category buttons** — seven buttons (Klang, Farbklang, Geräusch, Kadenz, Textur, Stille, Neutro) trigger the convolution engine manually. The performer decides when to switch category based on what they hear from the orchestra.

- **tension** slider — controls masking intensity in real time (0 = dry source, 1 = fully unrecognizable)
- **FluCoMa t** — live bar showing real-time spectral tension from FluCoMa analysis (max contribution: 0.4)
- **final t** — composite tension actually sent to the SynthDef (score tension + FluCoMa × 0.4)
- **gate thr / gate rel** — input gate threshold and release
- **xfade** — crossfade time between category changes
- **master vol** — global output level
- **◎ HEADPHONES** — toggle stereo fold-down for monitoring (8ch → stereo, weighted by azimuth)
- **● REC / ■ STOP** — record output to `~/Desktop/remnant_YYYYMMDD_HHMMSS.aiff`
- **PANIC** — stops all synths and resets state

The active category label updates in real time on both the HUD and the CONV · LERDAHL panel.

---

## Architecture

### Signal chain
```
Orchestra → BlackHole ch 1–4
    → SoundIn.ar([0,1,2,3])  per field
    → \r_input  (gain stage)
    → \r_gate   (amplitude gate, control bus)
    → \r_conv   (masking pipeline — per field)
         ├─ PitchShift    (melodic/timbral scrambling)
         ├─ Convolution2  (categorical IR coloring)
         ├─ FreqShift     (spectral rotation)
         └─ BPF           (alien spectral window)
    → 8-channel octophonic output
```

### Convolution engine (Lerdahl masking)
The convolution engine implements progressive source masking following Lerdahl's timbral tension hierarchy. At tension 0.0 the source is fully recognizable; at tension 1.0 it is completely unrecognizable.

The pipeline runs in series on each field:

1. **PitchShift** — scrambles melodic/timbral identity; `pitchRatio`, `pitchDispersion` and `timeDispersion` scale with tension and vary by Lachenmann category
2. **Convolution2** — applies a category-specific procedural IR to the already-scrambled signal
3. **FreqShift** — rotates the spectrum by up to several hundred Hz, breaking residual harmonic relationships
4. **BPF** — a moving spectral window that shifts toward inharmonic frequencies as tension rises

The dry signal is multiplied by `(1 − tension)^1.5` — not mixed with the wet. At tension 1.0 the dry is zero.

IRs are generated procedurally in SC, one per Lachenmann category:

| Category  | IR character | Max freq shift | BPF Q |
|-----------|-------------|---------------|-------|
| Klang     | Pure harmonic partials, long decay | 15 Hz | 0.3 |
| Farbklang | Inharmonic ratios (φ, √2, √3…) | 60 Hz | 0.5 |
| Geräusch  | Broadband noise + band-filtered noise | 180 Hz | 1.2 |
| Kadenz    | Periodic impulse train | 8 Hz | 2.0 |
| Textur    | Slow FM modulation | 25 Hz | 0.2 |
| Stille    | Near-impulse, maximum transparency | 0 Hz | 0.1 |
| Neutro    | Neutral resonance + slight noise | 5 Hz | 0.3 |

All fields share the same IR and tension value (orchestra as a single body). Azimuth is per-field from the score.

IR parameters are adjustable live from the **CONV · LERDAHL** panel: IR length, pitch max, pitch dispersion, time dispersion, freq shift, BPF Q, pre-delay.

### Sound diversity
Two mechanisms prevent timbral homogeneity across the composition:

- **Spectral diversity** — within each field, consecutive events must differ by a minimum fraction of the total spectral centroid range (slider 0.0–0.50).
- **Inter-field exclusion** — each sound can only appear in one field. A shared `global_seen` set across all fields guarantees no repetitions.

### Pulse grid
The pulse grid encodes the Brownian inter-step distances as binary rational fractions. All fractions within a gesture share a single BPM — chosen as the canonical metronome value for which `gesture_duration × BPM / 60` is closest to an integer, so that the sum of all fractions corresponds exactly to the gesture duration.

### Dynamic Form → Lachenmann mapping

| Direction | Low tension (< 0.7) | High tension (≥ 0.7) |
|-----------|--------------------|-----------------------|
| Forward   | Textur             | Kadenz                |
| Backward  | Farbklang          | Geräusch              |
| Presence  | Klang              | Stille                |
| Neutral   | Neutro             | Textur                |

---

## Compositional parameters

| Parameter | Range | Description |
|-----------|-------|-------------|
| Duration | 30–180 s | Total duration per gesture (default: 60 s) |
| Number of fields | 1–15 | Simultaneous Brownian streams |
| Brownian steps | 4–32 | Path length per field |
| Initial volatility | 0.5–10.0 | Brownian step size |
| Stochastic drift | 0.0–2.0 | Parameter evolution rate |
| Distance threshold | 0.0–5.0 | Lerdahl timbral tension gate |
| Spectral diversity | 0.0–0.50 | Min centroid difference between events |
| Attraction intensity | 0.0–1.0 | Pull toward Dynamic Form attractor |

---

## Theoretical framework

| Layer | Reference | Implementation |
|-------|-----------|----------------|
| Timbral space | McAdams perceptual weights | UMAP with weighted features |
| Temporal directions | Thoresen Dynamic Forms (Aural Sonology ch. 8) | Brownian attractor per direction |
| Timbral tension | Lerdahl timbral hierarchy | Tension profile + distance threshold |
| Timbral prolongation | McAdams prolongational hierarchy | IR categories + gesture sequencing |
| Pulse grid | Proportional notation | Brownian inter-step distances → binary rational fractions, single canonical BPM per gesture |

Full theoretical notes: `remnant_note_teoriche.docx`

---

## Graphic score

Each field is visualised on an azimuthal axis (0–360°, mapped to 8-channel octophonic panning). The score displays:

- **Sound bars** — duration and onset of each event, clipped to field boundaries
- **Accent symbols** — release point ▲, goal point ●, termination ▼, warning point ◇ (Aural Sonology notation)
- **Pulse grid** — Brownian inter-step distances as binary rational fractions, single BPM per gesture; sum of fractions = gesture duration
- **Red vertical lines** — pulse grid divisions crossing the full azimuthal range
- **Two tension curves** — compositional profile (from Dynamic Form) and Brownian envelope (inverse of step duration)
- **Articulation slurs** — curved lines connecting consecutive events of the same instrument within a gesture. Each succession of timbres forms a phrase that the performer reads as a single gestural arc. Line weight indicates the degree of timbral contrast between events: thin (gradual transition), medium (soft contrast), thick with ◇ (sharp contrast). Slur colour matches the Dynamic Form of the gesture (Forward → blue, Backward → red, Presence → green, Neutral → grey).

---

## File structure

```
remnant/
├── contimbre_explorer.py      # Dash application — composition and score
├── umap_full.py               # UMAP pipeline (McAdams weights)
├── generate_reaper.py         # Reaper project generator
├── generate_midi.py           # MIDI file generator
├── plot_brownian.py           # Matplotlib Brownian path plot
├── partitura_html.py          # HTML score generator (navigable, one gesture per page)
├── export_tsv.lisp            # ConTimbre corpus extraction via SBCL
├── remnant_sc.scd             # SC — boot, buses, groups, SynthDefs
├── remnant_conv.scd           # SC — convolution engine, IR generation
├── remnant_flucos.scd         # SC — FluCoMa real-time analysis
├── remnant_hud.scd            # SC — performance HUD (timer + controls)
├── requirements.txt
├── README.md
├── .gitignore
├── remnant_guida.docx         # Technical guide (IT)
├── remnant_note_teoriche.docx # Theoretical notes (IT/EN)
└── scores/
    ├── brownian_score.json    # (generated — not versioned)
    ├── umap_full_coords.csv   # (generated — not versioned)
    └── modes_cache.json       # (generated — not versioned)
```

---

## Using a custom corpus

Remnant is not tied to ConTimbre. Any sound corpus can be used as long as the acoustic descriptors are available in the expected TSV format.

### TSV format

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Unique sound identifier (e.g. `violin.arco.ff.A4`) |
| `instrument` | string | Instrument name |
| `family` | string | Instrument family |
| `pitch` | float | MIDI pitch (or -1000 if unpitched) |
| `dynamic` | string | `ppp` `pp` `p` `mp` `mf` `f` `ff` `fff` |
| `spectral_complexity` | float | Spectral complexity / flux |
| `spectral_center` | float | Spectral centroid (Hz) |
| `duration` | float | Duration in seconds |
| `absolute_intensity` | float | RMS or loudness value |

After creating the TSV, run `umap_full.py` to recompute the timbral space. The rest of the system works identically.

---

## License

MIT License — see LICENSE file.

Research project. In development for international residencies.  
Open to collaborations with ensembles and music research centres.
