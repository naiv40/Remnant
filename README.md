# Remnant

**Sonic traces of a non-human world**

A multichannel acousmatic composition and live electronics system for orchestra and 8-channel diffusion. The project navigates orchestral timbral space through Brownian motion. In concert, the electronics listen to the orchestra in real time, transforming its signal according to temporal directions that shape tension and release as narrative forces within sound.

Through electroacoustic processing, sounds are detached from their recognisable source and relocated within an artificial sonic environment: a space that does not document but hypothesises.

The project emerges from a biocentric perspective on the Anthropocene: instrumental sounds as traces of a world that continues to exist independently of human presence.

---

## Presentation video

[![Remnant — Sound Traces from a Non-Human World](https://img.youtube.com/vi/3dbyVULZbTE/maxresdefault.jpg)](https://www.youtube.com/watch?v=3dbyVULZbTE)

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
        ├─ Multi-field Brownian motion
        ├─ Interactive graphic score
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
Requires [BlackHole](https://existential.audio/blackhole/) (16ch) configured as aggregate device with the audio interface. ePlayer sends 4 field tracks to BlackHole channels 1–4; SuperCollider reads them as `SoundIn.ar([0,1,2,3])`.

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
remnant_hud.scd     Block 1, Block 2
```

---

## Workflow

### Composition (contimbre_explorer.py)
1. Select instrument families in the left panel
2. Click **Apply filter** — recomputes UMAP on the subset
3. Set compositional parameters (duration, number of fields, Brownian steps)
4. Assign a **Temporal direction** to each field (Forward / Backward / Presence / Neutral)
5. Click **Generate composition**
6. Click **Generate score** — writes `brownian_score.json` and opens the graphic score
7. Click **Export for ePlayer** — generates `contimbre_remnant.cePlayerOrc`

### Live performance (remnant_hud.scd)
All fields play simultaneously as a single body. The HUD is the only live interface.

- **START** — launches the automatic gesture timer; fields advance according to `brownian_score.json` durations
- **STOP** — interrupts and resets to gesture 1
- **tension** slider — overrides score tension in real time; alt+click returns to score value
- **gate thr / gate rel** — input gate threshold and release
- **xfade** — crossfade time between gestures
- **master vol** — global output level
- **PANIC** — stops timer and resets all synths

The HUD display shows: current gesture / total, Lachenmann category, progress bar, elapsed time / total duration.

FluCoMa analysis runs continuously, adding automatic tension modulation (max contribution: 0.4).

---

## Architecture

### Signal chain
```
Orchestra → BlackHole ch 1–4
    → SoundIn.ar([0,1,2,3])  per field
    → \r_input  (gain stage)
    → \r_gate   (amplitude gate, control bus)
    → \r_conv   (Convolution2 — one processor per field, shared IR)
    → 8-channel octophonic output
```

### Convolution engine
IRs are generated procedurally in SC, one per Lachenmann category:

| Category  | IR character |
|-----------|-------------|
| Farbklang | FM, 3 inharmonic operators (ratios 1.41, 2.73, 0.618), decreasing index |
| Geräusch  | White noise |
| Klang     | 6 harmonic partials, long decay |
| Kadenz    | Sinusoidal impulse train |
| Textur    | Noise with slow attack |

All fields share the same IR and tension value (orchestra as a single body). Azimuth is per-field from the score.

### Dynamic Form → Lachenmann mapping

| Direction | Low tension (< 0.7) | High tension (≥ 0.7) |
|-----------|--------------------|-----------------------|
| Forward   | Textur             | Kadenz                |
| Backward  | Farbklang          | Geräusch              |
| Presence  | Klang              | Stille                |
| Neutral   | Neutro             | Textur                |

---

## Theoretical framework

| Layer | Reference | Implementation |
|-------|-----------|----------------|
| Timbral space | McAdams perceptual weights | UMAP with weighted features |
| Temporal directions | Thoresen Dynamic Forms (Aural Sonology ch. 8) | Brownian attractor per direction |
| Timbral tension | Lerdahl timbral hierarchy | Tension profile + distance threshold |
| Timbral prolongation | McAdams prolongational hierarchy | IR categories + gesture sequencing |
| Pulse grid | Proportional notation | Brownian inter-step distances → binary rational fractions with local BPM per cell |

Full theoretical notes: `remnant_note_teoriche.docx`

---

## Graphic score

Each field is visualised on an azimuthal axis (0–360°, mapped to 8-channel octophonic panning). The score displays:

- **Sound bars** — duration and onset of each event, clipped to field boundaries
- **Accent symbols** — release point ▲, goal point ●, termination ▼, warning point ◇ (Aural Sonology notation)
- **Pulse grid** — Brownian inter-step distances as binary rational fractions, with local BPM per cell
- **Red vertical lines** — pulse grid divisions crossing the full azimuthal range
- **Two tension curves** — compositional profile (from Dynamic Form) and Brownian envelope (inverse of step duration)

---

## File structure

```
remnant/
├── contimbre_explorer.py      # Dash application — composition and score
├── umap_full.py               # UMAP pipeline (McAdams weights)
├── plot_brownian.py           # Matplotlib Brownian path plot
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
