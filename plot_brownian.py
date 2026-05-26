import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np

umap = pd.read_csv(os.path.expanduser("~/Desktop/remnant/umap_full_coords.csv"))
path = pd.read_csv(os.path.expanduser("~/Desktop/remnant/brownian_path.csv"))

fig, ax = plt.subplots(figsize=(14, 10))

families = umap["family"].unique()
colors = cm.tab20(np.linspace(0, 1, len(families)))
for fam, col in zip(families, colors):
    grp = umap[umap["family"]==fam]
    ax.scatter(grp["x"], grp["y"], c=[col], s=8, alpha=0.3, label=fam)

colors_path = cm.plasma(np.linspace(0, 1, len(path)))
ax.plot(path["x"], path["y"], color="black", linewidth=1.5, zorder=4, alpha=0.7)
ax.scatter(path["x"], path["y"], c=colors_path, s=100, zorder=5, edgecolors="black", linewidth=0.5)

for i, row in path.iterrows():
    label = row["id"].split(".")
    short = label[0]
    ax.annotate(short, (row["x"], row["y"]), fontsize=6, ha="left", va="bottom",
                xytext=(4, 4), textcoords="offset points")

ax.legend(markerscale=2, fontsize=7, bbox_to_anchor=(1.01, 1), loc="upper left")
ax.set_title("Percorso browniano — orchestra completa")
plt.tight_layout()
plt.savefig(os.path.expanduser("~/Desktop/remnant/brownian_full.png"), dpi=150, bbox_inches="tight")
print("Salvato in ~/Desktop/remnant/brownian_full.png")
