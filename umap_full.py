import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import umap
import matplotlib.pyplot as plt
import matplotlib.cm as cm

# Path relativo alla cartella dello script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV    = os.path.join(SCRIPT_DIR, "umap_full_coords.csv")
OUT_PNG    = os.path.join(SCRIPT_DIR, "umap_full.png")

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

df_sample = df.groupby("family").apply(
    lambda x: x.sample(min(len(x), 300), random_state=42)
).reset_index(drop=True)
print(f"Campione: {len(df_sample)} suoni da {df_sample['family'].nunique()} famiglie")

features = ["pitch", "dynamic_num", "spectral_complexity", "spectral_center", "duration", "absolute_intensity"]
X = df_sample[features].fillna(0).values

X_std = StandardScaler().fit_transform(X)

# Ponderazione percettiva McAdams
MCADAMS_WEIGHTS = np.array([1.5, 1.0, 2.0, 3.0, 1.0, 1.0])
X_std = X_std * MCADAMS_WEIGHTS
print(f"Ponderazione McAdams: {dict(zip(features, MCADAMS_WEIGHTS))}")

print("UMAP in corso...")
embedding = umap.UMAP(n_components=2, n_neighbors=8, min_dist=0.1, random_state=42).fit_transform(X_std)

df_sample["x"] = embedding[:, 0]
df_sample["y"] = embedding[:, 1]

df_sample[["id", "instrument", "family", "x", "y", "pitch", "dynamic",
           "spectral_complexity", "spectral_center"]].to_csv(OUT_CSV, index=False)

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
