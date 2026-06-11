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
ConTimbre TSV corpus  /  SOL HQ corpus
    ↓  export_tsv.lisp  (SBCL)  /  sol_to_tsv_2.py
contimbre_full.tsv  /  sol_coords_input.tsv
    ↓  umap_full.py  (McAdams perceptual weights)
umap_contimbre_coords.csv  /  umap_sol_coords.csv
    ↓  contimbre_explorer.py  (Dash)
        ├─ Corpus selector (ConTimbre / SOL HQ)
        ├─ Sound image selector (centroid, texture, pitch, dynamics + Breadth)
        ├─ Instrument family filter + local UMAP recomputation
        ├─ Multi-field Brownian motion with spectral diversity constraint
        ├─ Inter-field sound exclusion (no repeated sounds across fields)
        ├─ Interactive graphic score with proportional pulse grid
        ├─ Export .cOrc / .cePlayerOrc  (SBCL)
        ├─ Export PS notation  (ConTimbre graphic notation via SBCL)
        ├─ Click-to-open ConTimbre HTML (instrument notation via browser)
        ├─ Target audio attractor (Orchidea-style: audio → UMAP coord → Brownian attractor)
        └─ brownian_score.json  →  SuperCollider
                ├─ remnant_sc.scd      (boot, buses, groups, synths)
                ├─ remnant_conv.scd    (convolution engine, IR generation)
                ├─ remnant_flucos.scd  (FluCoMa real-time analysis)
                └─ remnant_hud.scd     (performance HUD)

Demo / development playback (no orchestra):
        contimbre_test.scd     (FOA playback from score, with recording)
        contimbre_resolve_paths.lisp  (ConTimbre id → MP3 path resolver)
```

---

## Dependencies

### Python
```bash
pip install -r requirements.txt  # includes librosa for target audio projection
```

### SuperCollider
Requires SuperCollider ≥ 3.12 with FluCoMa and ATK quarks:
```supercollider
Quarks.install("FluCoMa");
Quarks.install("atk-sc3");
// Restart SC after installation
```

### Audio routing
Requires [BlackHole](https://existential.audio/blackhole/) (16ch) configured as aggregate device with the audio interface. ePlayer sends field tracks to BlackHole; SuperCollider reads them as `SoundIn.ar([0,1,2,3])`.

### ConTimbre + SBCL
[ConTimbre Standard V2](https://www.contimbre.com) and [SBCL](http://www.sbcl.org) with Quicklisp must be installed and available in PATH.

### SOL HQ (optional)
[Studio On Line HQ](https://forum.ircam.fr/projects/detail/sol/) from IRCAM. Required only when using the SOL corpus. The `sol_to_tsv_2.py` script reads `SOL_0.9_HQ_2.spectrum.db` and exports the TSV.

---

## Setup

### 1. Extract the corpus

**ConTimbre:**
```bash
sbcl --load export_tsv.lisp
```
Writes `/tmp/contimbre_full.tsv`.

**SOL HQ:**
```bash
python3 sol_to_tsv_2.py
```
Writes `sol_coords_input.tsv` in the project folder.

### 2. Compute UMAP coordinates
```bash
python3 umap_full.py  # also saves umap_model.pkl + umap_scaler.pkl for target audio projection
```
Generates `umap_contimbre_coords.csv` and/or `umap_sol_coords.csv`.

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

### 5. Demo playback (no orchestra)
```
1. sbcl --load contimbre_resolve_paths.lisp   # resolves score IDs → MP3 paths
2. contimbre_test.scd  Block 0, 1, 2, 3, 4
3. ~playScore.()   # plays entire score with automatic recording
```

---

## Workflow

### Composition (contimbre_explorer.py)

**Corpus selection** — switch between ConTimbre and SOL HQ from the sidebar. Each corpus has its own pre-computed UMAP space.

**Sound image** — describe the target timbre using four perceptual sliders (centroid, texture, pitch, dynamics) and set **Breadth** to control how much of the corpus is selected. Click **Select from sound image** — the system selects the closest sounds using a McAdams-weighted Euclidean distance and updates the timbral map.

Alternatively, select instrument families manually and click **Apply filter** — recomputes UMAP on the subset.

1. Set compositional parameters (duration, number of fields, Brownian steps)
2. Set **Spectral diversity** — minimum spectral centroid difference between consecutive events
3. Assign a **Temporal direction** to each field (Forward / Backward / Presence / Neutral)
4. Click **Generate composition**
5. Click **Generate score** — writes `brownian_score.json` and opens the graphic score
6. Click **Export for ePlayer** — generates `contimbre_remnant.cePlayerOrc`
7. (Optional) Click **Export RTM for OpenMusic** — generates `scores/rtm_ferneyhough.lisp` with 3-level hierarchical rhythm trees (exact time signatures + per-measure BPM + tension-driven sub-subdivision); load in OM 8 Listener and connect to `voice` boxes
8. (Optional) Load a **target audio file** — the Brownian path is attracted toward its UMAP coordinates instead of the Dynamic Form centroid
9. Click **Export PS notation** — generates `brownian_notation.ps` with ConTimbre graphic notation via SBCL

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

The active category label updates in real time on both the HUD and the CONV · LERDAHL panel. The timer advances through the score gestures automatically; category and tension are read from the score but can be overridden manually at any time.

### Demo playback (contimbre_test.scd)
Standalone playback of the brownian score using ConTimbre MP3 samples, without a live orchestra. Uses ATK FOA for 8-channel diffusion.

```supercollider
~playScore.()      // plays entire score in sequence, records automatically
~stopScore.()      // stop
~playGesture.(0)   // play single gesture (0-indexed)
~recStart.()       // manual record start
~recStop.()        // manual record stop
```

Recording closes automatically after all reverb tails have decayed (monitored via `s.numSynths`). Output: `~/Desktop/remnant_YYYYMMDD_HHMMSS.aiff`, 8 channels.

---

## Architecture

### Signal chain (live)
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
    → 8-channel octophonic output (VBAP)
```

### Signal chain (demo — contimbre_test.scd)
```
brownian_score.json
    → contimbre_resolve_paths.lisp  (id → MP3 path)
    → Buffer.read  (per event, cached)
    → PlayBuf  →  FreeVerb  →  FOA encode  →  FoaDecode (panto 8)
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
The pulse grid encodes the Brownian inter-step distances as binary rational fractions. Each cell carries its own local BPM, derived from the per-step tension value: `BPM = 40 + tension × 80`, snapped to `[40, 48, 60, 72, 80, 96, 120]`. High tension produces a faster local pulse; low tension a slower one. The absolute durations in seconds remain invariant — the BPM is a gestural and interpretive indication, not a temporal constraint.

### RTM export for OpenMusic

**Export RTM for OpenMusic** generates `scores/rtm_ferneyhough.lisp` — a three-level hierarchical rhythm tree for each field in Ferneyhough's proportional notation system.

**Level 1 — Time signature:** each Brownian cell becomes a measure `(n d)` with `d ∈ {2, 4, 8, 16}`, `n ∈ [1, 16]`. Signature is chosen so the local BPM is in [40, 240] and closest to the gesture's global BPM, keeping absolute durations invariant:

```
bpm_local = 240 × n / (cell_dur_sec × d)
cell_dur  = (cell_dist / total_dist) × gesture_dur_sec
```

Cells are partitioned by cumulative Euclidean distance threshold (midpoint rule). Empty cells → rest `(-1)`.

**Level 2 — Measure subdivision:** steps within a cell weighted by Euclidean distance, quantised with denominator ≤ 8.

**Level 3 — Sub-subdivision** from `tension_profile`:
- tension ≤ 0.25 → whole note
- tension 0.25–0.50 → 2–5 near-uniform subdivisions
- tension > 0.50 → 3–8 subdivisions, exponential distribution, odd denominators preferred (3, 5, 7)

Output: native OpenMusic 8 `voice` objects with per-measure tempo in `format-omtempo` format. Load in OM 8 Listener: `(load "…/scores/rtm_ferneyhough.lisp")`, then use `(lambda () *rtm-gesto1*)` in a Lisp Function box connected to a `voice` box.

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
| Centroid | 0.0–1.0 | Dark ↔ Bright — target spectral centroid for sound image selection |
| Texture | 0.0–1.0 | Smooth ↔ Rough — target spectral complexity |
| Pitch | 0.0–1.0 | Low ↔ High — target pitch register |
| Dynamics | 0.0–1.0 | Soft ↔ Loud — target dynamic level |
| Breadth | 0.05–0.50 | Percentage of corpus selected (top-N closest sounds by weighted distance) |
| Duration | 30–180 s | Total duration per gesture (default: 60 s) |
| Number of fields | 1–15 | Simultaneous Brownian streams |
| Brownian steps | 4–32 | Path length per field |
| Initial volatility | 0.5–10.0 | Brownian step size |
| Stochastic drift | 0.0–2.0 | Parameter evolution rate |
| Distance threshold | 0.0–5.0 | Lerdahl timbral tension gate |
| Spectral diversity | 0.0–0.50 | Min centroid difference between events |
| Attraction intensity | 0.0–1.0 | Pull toward Dynamic Form centroid or target audio coord |
| Target audio | .wav / .aiff | Replaces Dynamic Form centroid as attractor; upload or paste path |

---

## Theoretical framework

| Layer | Reference | Implementation |
|-------|-----------|----------------|
| Timbral space | McAdams perceptual weights | UMAP with weighted features |
| Temporal directions | Thoresen Dynamic Forms (Aural Sonology ch. 8) | Brownian attractor per direction |
| Timbral tension | Lerdahl timbral hierarchy | Tension profile + distance threshold |
| Timbral prolongation | McAdams prolongational hierarchy | IR categories + gesture sequencing |
| Pulse grid | Proportional notation | Brownian inter-step distances → binary rational fractions, local BPM per cell from per-step tension |
| RTM export | Ferneyhough proportional notation | 3-level hierarchical rhythm tree: exact time signatures (n/d, d∈{2,4,8,16}) from Euclidean distances, per-measure BPM for absolute duration invariance, Level 3 sub-subdivision from tension_profile |
| Temporal consciousness | Husserl, *lebendige Gegenwart* | Living present composite in SC tension bus |
| Target orchestration | Cella, Orchidea / MaxOrch | Audio target → UMAP projection → Brownian attractor |

### Living present (Husserl)

The tension architecture in SuperCollider implements Husserl's *lebendige Gegenwart* — the structure of temporal consciousness as a unified flow of three moments:

- **Retention** (*Retention*) — the immediate past that still resonates in the present. Implemented as an exponentially-weighted moving average of the last 8 tension values (`~r_retentionValue`). High-weight recent history, low-weight distant past.
- **Primal impression** (*Urimpression*) — the instantaneous present tension value, composite of score tension and FluCoMa analysis.
- **Protention** (*Protention*) — the imminent future anticipated before it arrives. A background routine reads `brownian_score.json` and pre-loads the tension of the next event 2 seconds in advance (`~r_protenzioneRoutine`).

The final tension sent to all SynthDefs is the weighted composite:

```
living_present = impression × 0.60 + retention × 0.25 + protention × 0.15
```

The three moments are not separate — they form a single temporal thickness around the present. Timbral category transitions are never abrupt: the system carries memory of what has just sounded and anticipates what is about to arrive, producing a perceptible temporal depth at every moment of the performance.

Full theoretical notes: `remnant_note_teoriche.docx`

---

## Graphic score

Each field is visualised on an azimuthal axis (0–360°, mapped to 8-channel octophonic panning). The score displays:

- **Sound bars** — duration and onset of each event, clipped to field boundaries
- **Pitch notation** — 5-line mini staff above/below each event bar; filled notehead (●) positioned by relative pitch within the gesture; alternates above/below to avoid overlap
- **Dynamic markings** — italic dynamic (p, mf, f, fff…) at the start of each bar, below the line
- **Pulse grid** — Brownian inter-step distances as binary rational fractions (denominator ≤ 8, Ferneyhough system); each cell is independent with its own local BPM
- **Red vertical lines** — pulse grid divisions crossing the full azimuthal range
- **Two tension curves** — compositional profile (from Dynamic Form) and Brownian envelope (inverse of step duration)
- **Watermark** — field index (F.1, F.2 …) as a large semi-transparent background element
- **ConTimbre links** — click any event marker to open the instrument's ConTimbre HTML page in the browser (playing technique, notation, audio examples)
- **SVG export** — camera button in the Plotly toolbar saves a fully vectorial SVG (all elements are paths, editable in Illustrator or Inkscape)

The PS score (`brownian_notation.ps`) contains ConTimbre's own graphic notation for each sound (staff, noteheads, playing techniques), generated via `orchestrations_to_postscript` in the ConTimbre library.

---

## File structure

```
remnant/
├── contimbre_explorer.py          # Dash — composition, score, export
├── umap_full.py                   # UMAP pipeline (McAdams weights) — saves umap_model.pkl
├── umap_model.pkl                # Serialised UMAP reducer for target audio projection
├── umap_scaler.pkl               # Serialised scaler for target audio projection
├── sol_to_tsv_2.py                # SOL HQ → TSV pipeline
├── generate_reaper.py             # Reaper project generator
├── generate_midi.py               # MIDI file generator
├── plot_brownian.py               # Matplotlib Brownian path plot
├── export_tsv.lisp                # ConTimbre corpus extraction (SBCL)
├── contimbre_resolve_paths.lisp   # ConTimbre id → MP3 path resolver
├── remnant_sc.scd                 # SC — boot, buses, groups, SynthDefs
├── remnant_conv.scd               # SC — convolution engine, IR generation
├── remnant_flucos.scd             # SC — FluCoMa real-time analysis
├── remnant_hud.scd                # SC — performance HUD
├── contimbre_test.scd             # SC — demo playback + recording (no orchestra)
├── requirements.txt
├── README.md
├── .gitignore
├── remnant_guida.docx             # System guide v4 (IT)
├── remnant_note_teoriche.docx     # Theoretical notes (IT/EN)
└── scores/
    ├── brownian_score.json        # (generated — not versioned)
    ├── umap_contimbre_coords.csv  # (generated — not versioned)
    ├── umap_sol_coords.csv        # (generated — not versioned)
    ├── modes_cache.json           # (generated — not versioned)
    └── rtm_ferneyhough.lisp       # (generated — not versioned)
```

---

## Target audio (Orchidea-style)

Any `.wav` or `.aiff` file can be loaded as a Brownian attractor. The system extracts spectral features with librosa, applies McAdams weighting, and projects into the existing ConTimbre UMAP space:

```
audio file → librosa features → umap_scaler → umap_model.transform() → (x, y) → Brownian attractor
```

- **Load:** click `↑ carica file audio` or paste a path in the text field
- **Remove:** click `✕ rimuovi target` — reverts to Dynamic Form centroid
- **Requirement:** run `umap_full.py` once to generate `umap_model.pkl` and `umap_scaler.pkl`

---

## Using a custom corpus

Remnant is not tied to ConTimbre or SOL. Any sound corpus can be used as long as the acoustic descriptors are available in the expected TSV format.

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

Research project. Submitted to Score Follower (autumn 2026 round).  
Open to collaborations with ensembles, music research centres, and international residencies.
