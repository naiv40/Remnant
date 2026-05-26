# Remnant

**Sonic traces of a non-human world**

A multichannel acousmatic compositional and performance system that navigates timbral space through Brownian motion. In concert, the electronics listen to the orchestra in real time, transforming its signal according to temporal directions that shape tension and release as narrative forces within sound.

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
        ├─ Instrument filter + local UMAP recomputation
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
| Pulse grid | Proportional notation | Brownian inter-step distances → binary fractions |

Full theoretical notes: `remnant_note_teoriche.docx`

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
├── contimbre_explorer.py     # Main Dash application
├── umap_full.py              # UMAP pipeline (McAdams weights)
├── plot_brownian.py          # Matplotlib Brownian path plot
├── export_tsv.lisp           # ConTimbre corpus extraction via SBCL
├── remnant_sc.scd            # SuperCollider — synths + OSC + spatialiser
├── remnant_flucos.scd        # SuperCollider — FluCoMa real-time analysis
├── requirements.txt
├── README.md
├── .gitignore
├── remnant_guida.docx        # Technical guide (IT)
├── remnant_note_teoriche.docx # Theoretical notes (IT/EN)
└── scores/
    ├── umap_full_coords.csv  # (generated — not versioned)
    └── modes_cache.json      # (generated — not versioned)
```

---

## License

MIT License — see LICENSE file.

Research project. In development for international residencies.  
Open to collaborations with ensembles and music research centres.
