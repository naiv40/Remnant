import os
import pickle
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import umap
import matplotlib.pyplot as plt
import matplotlib.cm as cm

# Path relativo alla cartella dello script
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUT_CSV     = os.path.join(SCRIPT_DIR, "umap_contimbre_coords.csv")
OUT_PNG     = os.path.join(SCRIPT_DIR, "umap_full.png")
OUT_MODEL   = os.path.join(SCRIPT_DIR, "umap_model.pkl")   # modello UMAP serializzato
OUT_SCALER  = os.path.join(SCRIPT_DIR, "umap_scaler.pkl")  # scaler serializzato

df = pd.read_csv("/tmp/contimbre_full.tsv", sep="\t")

df["pitch"] = pd.to_numeric(df["pitch"], errors="coerce")
df["pitch"] = df["pitch"].replace(-1000.0, np.nan)
df["pitch"] = df["pitch"].fillna(df["pitch"].median())

# Rinomina colonne per compatibilità con contimbre_explorer
if "instrument_english" in df.columns:
    df = df.rename(columns={"instrument_english": "instrument"})
if "family_english" in df.columns:
    df = df.rename(columns={"family_english": "family"})

dynamic_map = {"ppp": 1, "pp": 2, "p": 3, "mp": 4, "mf": 5, "f": 6, "ff": 7, "fff": 8}
df["dynamic_num"] = df["dynamic"].map(dynamic_map).fillna(0)

df_sample = df.copy()
print(f"Corpus completo: {len(df_sample)} suoni da {df_sample['family'].nunique()} famiglie")

features = ["pitch", "dynamic_num", "spectral_complexity", "spectral_center", "duration", "absolute_intensity"]
features = [f for f in features if f in df_sample.columns]
X = df_sample[features].fillna(0).values

X_std = StandardScaler().fit_transform(X)

# Ponderazione percettiva McAdams (adattata alle colonne disponibili)
WEIGHTS_MAP = {"pitch": 1.5, "dynamic_num": 1.0, "spectral_complexity": 2.0, "spectral_center": 3.0}
MCADAMS_WEIGHTS = np.array([WEIGHTS_MAP.get(f, 1.0) for f in features])

# Salva scaler per proiezione futura di target audio
scaler = StandardScaler()
X_std  = scaler.fit_transform(X) * MCADAMS_WEIGHTS
with open(OUT_SCALER, "wb") as f:
    pickle.dump((scaler, MCADAMS_WEIGHTS, features), f)
print(f"Scaler salvato: {OUT_SCALER}")
print(f"Ponderazione McAdams: {dict(zip(features, MCADAMS_WEIGHTS))}")

print("UMAP in corso (corpus completo — può richiedere 20–30 min)...")
reducer = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, random_state=42)
embedding = reducer.fit_transform(X_std)

# Salva modello UMAP per proiezione target audio
with open(OUT_MODEL, "wb") as f:
    pickle.dump(reducer, f)
print(f"Modello UMAP salvato: {OUT_MODEL}")

df_sample["x"] = embedding[:, 0]
df_sample["y"] = embedding[:, 1]

df_sample[[c for c in ["id","instrument","family","x","y","pitch","dynamic","spectral_complexity","spectral_center","technique","duration_frames","start_frame"] if c in df_sample.columns]].to_csv(OUT_CSV, index=False)

families = df_sample["family"].unique()
colors = cm.tab20(np.linspace(0, 1, len(families)))
family_color = dict(zip(families, colors))

plt.figure(figsize=(14, 10))
for fam, grp in df_sample.groupby("family"):
    plt.scatter(grp["x"], grp["y"], c=[family_color[fam]], s=8, alpha=0.5, label=fam)
plt.legend(markerscale=2, fontsize=7, bbox_to_anchor=(1.01, 1), loc="upper left")
plt.title("ConTimbre — UMAP orchestra (ponderazione McAdams)")
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
print(f"Salvato in {OUT_PNG}")
print(f"Esportati {len(df_sample)} suoni in {OUT_CSV}")
