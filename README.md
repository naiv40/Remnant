# Remnant

**Sonic traces of a non-human world**

A multichannel acousmatic compositional and performance system that navigates orchestral timbral space through Brownian motion. In concert, the electronics listen to the orchestra in real time, transforming its signal according to temporal directions that shape tension and release as narrative forces within sound.

Through electroacoustic processing, sounds are detached from their recognisable source and relocated within an artificial sonic environment: a space that does not document but hypothesises.

The project emerges from a biocentric perspective on the Anthropocene: instrumental sounds as traces of a world that continues to exist independently of human presence.

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
        └─ OSC → SuperCollider
                ├─ remnant_sc.scd   (16 permanent synths)
                └─ remnant_flucos.scd  (FluCoMa real-time analysis)
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

### ConTimbre + SBCL
[ConTimbre Standard V2](https://www.contimbre.com) and [SBCL](http://www.sbcl.org) with Quicklisp must be installed and available in PATH.

---

## Setup

### 1. Extract the corpus
```bash
sbcl --load export_tsv.lisp
```
This writes `/tmp/contimbre_full.tsv`.

### 2. Compute UMAP coordinates
```bash
cd ~/Desktop/remnant
python3 umap_full.py
```
This generates `umap_full_coords.csv` in the project folder.

### 3. Launch Remnant Explorer
```bash
python3 contimbre_explorer.py
# → http://127.0.0.1:8050
```

### 4. Launch SuperCollider
Open and evaluate in SC IDE:
```supercollider
Document.open("remnant_sc.scd");     // Cmd+Return
Document.open("remnant_flucos.scd"); // after boot
```

---

## Workflow

### Composition
1. Select instrument families in the left panel
2. Click **Apply filter** — recomputes UMAP on the subset
3. Set compositional parameters (duration, number of fields, Brownian steps)
4. Assign a **Temporal direction** to each field (Forward / Backward / Presence / Neutral)
5. Click **Generate composition**
6. Click **Generate score** — opens the graphic score at `/score/N`

### Live performance
- The timeline at the bottom of the UMAP map is the direction panel
- Click a field block → sends OSC `/remnant/gesture` to SuperCollider
- SuperCollider transforms the orchestra signal according to the Dynamic Form
- FluCoMa analysis adds automatic tension modulation (max contribution: 0.4)
- `/remnant/panic` — resets all synths to Neutral

---

## Theoretical framework

The system integrates four analytical layers:

| Layer | Reference | Implementation |
|-------|-----------|----------------|
| Timbral space | McAdams perceptual weights | UMAP with weighted features |
| Temporal directions | Thoresen Dynamic Forms (Aural Sonology ch. 8) | Brownian attractor per direction |
| Timbral tension | Lerdahl timbral hierarchy | Tension profile + distance threshold |
| Pulse grid | Proportional notation | Brownian inter-step distances → binary rational fractions, serving as compositional reference for symbolic notation development. Each cell carries a local BPM derived from the nearest canonical metronome value — a tempo-map where every section has its own implicit speed, directly traceable to the geometry of the Brownian path |

Full theoretical notes: `remnant_note_teoriche.docx`

---

## Graphic score

Each field is visualised on an azimuthal axis (0–360°, mapped to 8-channel panning). The score displays:

- **Sound bars** — duration and onset of each event, clipped to field boundaries
- **Accent symbols** — release point ▲, goal point ●, termination ▼, warning point ◇ (Aural Sonology notation)
- **Pulse grid** — Brownian inter-step distances expressed as binary rational fractions, with local BPM per cell. The grid serves as a compositional reference for developing the musical gesture in symbolic notation
- **Red vertical lines** — pulse grid divisions crossing the full azimuthal range
- **Two tension curves** — compositional profile (from Dynamic Form) and Brownian envelope (inverse of step duration). Where they converge the field is coherent; where they diverge, intention and stochastic geometry pull in opposite directions

---

## OSC protocol

All messages sent to `127.0.0.1:57121`.

| Message | Arguments | Description |
|---------|-----------|-------------|
| `/remnant/gesture` | `[idx, category, tension, azimuth]` | Activate field |
| `/remnant/tension` | `[value]` | Override global tension (0.0–1.0) |
| `/remnant/mute` | `[channel]` | Mute channel 0–15 |
| `/remnant/panic` | — | Reset all synths to Neutral |
| `/remnant/volume` | `[value]` | Master volume (default 1.6) |

### Dynamic Form → Lachenmann mapping

| Direction | Low tension (< 0.7) | High tension (≥ 0.7) |
|-----------|--------------------|-----------------------|
| Forward   | Textur             | Kadenz                |
| Backward  | Farbklang          | Geräusch              |
| Presence  | Klang              | Stille                |
| Neutral   | Neutro             | Textur                |

---

## File structure

```
remnant/
├── contimbre_explorer.py      # Main Dash application
├── umap_full.py               # UMAP pipeline (McAdams weights)
├── plot_brownian.py           # Matplotlib Brownian path plot
├── export_tsv.lisp            # ConTimbre corpus extraction via SBCL
├── remnant_sc.scd             # SuperCollider — synths + OSC + spatialiser
├── remnant_flucos.scd         # SuperCollider — FluCoMa real-time analysis
├── requirements.txt
├── README.md
├── .gitignore
├── remnant_guida.docx         # Technical guide (IT)
├── remnant_note_teoriche.docx # Theoretical notes (IT/EN)
└── scores/
    ├── umap_full_coords.csv   # (generated — not versioned)
    └── modes_cache.json       # (generated — not versioned)
```

---

## License

MIT License — see LICENSE file.

Research project. In development for international residencies.  
Open to collaborations with ensembles and music research centres.

---

## Using a custom corpus

Remnant is not tied to ConTimbre. Any sound corpus can be used as long as the acoustic descriptors are available in the expected TSV format.

### TSV format

The file `contimbre_full.tsv` must be a tab-separated file with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Unique sound identifier (e.g. `violin.arco.ff.A4`) |
| `instrument` | string | Instrument name |
| `family` | string | Instrument family (e.g. `strings`, `woodwinds`) |
| `pitch` | float | MIDI pitch (or -1000 if unpitched) |
| `dynamic` | string | Dynamic marking (`ppp`, `pp`, `p`, `mp`, `mf`, `f`, `ff`, `fff`) |
| `spectral_complexity` | float | Spectral complexity / flux |
| `spectral_center` | float | Spectral centroid (Hz) |
| `duration` | float | Duration in seconds |
| `absolute_intensity` | float | RMS or loudness value |

### Extracting descriptors with FluCoMa (SuperCollider)

```supercollider
// Example: extract descriptors from a folder of audio files
~files = PathName("/path/to/samples/").files;
~buf  = Buffer.read(s, ~files[0].fullPath);

FluidBufSpectralShape.process(s, ~buf, features: ~shape);
FluidBufPitch.process(s, ~buf, features: ~pitch);
FluidBufLoudness.process(s, ~buf, features: ~loud);
```

Then export to TSV with the column names above. The `id` field is used as the sound reference throughout the system — it should match the filename or a unique key in your sample player.

### Minimal example

```
id	instrument	family	pitch	dynamic	spectral_complexity	spectral_center	duration	absolute_intensity
rain.light	rain	field	-1000	pp	0.82	1200.4	3.2	0.12
rain.heavy	rain	field	-1000	ff	0.95	2400.1	4.1	0.71
wind.low	wind	field	-1000	p	0.61	800.2	5.0	0.08
```

After creating the TSV, run `umap_full.py` to recompute the timbral space. The rest of the system works identically.
