
import argparse
import numpy as np
import pandas as pd

W = (0.6, 0.2, 0.2)
SCENARIOS = {"A_60_20_20 (retenu)": (0.6, 0.2, 0.2), "B_egal": (1 / 3, 1 / 3, 1 / 3), "C_50_25_25": (0.5, 0.25, 0.25),
             "D_70_15_15": (0.7, 0.15, 0.15), "E_etat_seul": (1.0, 0.0, 0.0)}
BORNES = [(70, "Tres eleve"), (55, "Eleve"), (40, "Modere eleve"), (20, "Modere"), (-1, "Faible")]


def palier(x):
    return next(lbl for b, lbl in BORNES if x >= b)


def composantes(p):
    p = p.copy()
    p["score_etat"] = 100 - p["ach_t"]
    p["score_tendance"] = (-p["delta3_ach_points"]).clip(0, 20) / 20 * 100
    p["score_exposition"] = p["pdi_pour_100_eleves_retenu"].clip(0, 100)
    return p


def indice(df, w=W):
    return w[0] * df["score_etat"] + w[1] * df["score_tendance"] + w[2] * df["score_exposition"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--sortie", default=".")
    a = ap.parse_args()
    from pathlib import Path
    out = Path(a.sortie); out.mkdir(parents=True, exist_ok=True)

    p = composantes(pd.read_csv(a.panel))
    p = p[p["annee_debut"] >= 2019].dropna(subset=["score_etat", "score_tendance", "score_exposition"]).copy()
    p["indice_risque"] = indice(p)
    p["rang"] = p.groupby("annee_debut")["indice_risque"].rank(ascending=False, method="min").astype(int)
    p["palier"] = p["indice_risque"].map(palier)
    cols = ["region", "annee_scolaire", "annee_debut", "ach_t", "delta3_ach_points", "pdi_pour_100_eleves_retenu",
            "score_etat", "score_tendance", "score_exposition", "indice_risque", "rang", "palier", "niveau_risque"]
    p[cols].round(2).to_csv(out / "indice_risque_region_annee.csv", index=False, encoding="utf-8-sig")

    d = p[p["annee_debut"] == p["annee_debut"].max()].set_index("region").copy()
    for k, w in SCENARIOS.items():
        d["rang_" + k] = indice(d, w).rank(ascending=False, method="min").astype(int)
    rcols = [c for c in d.columns if c.startswith("rang_")]
    d["rang_min"] = d[rcols].min(axis=1)
    d["rang_max"] = d[rcols].max(axis=1)
    d["contrib_etat"] = W[0] * d["score_etat"]
    d["contrib_tendance"] = W[1] * d["score_tendance"]
    d["contrib_exposition"] = W[2] * d["score_exposition"]
    d = d.sort_values("indice_risque", ascending=False)
    res = d[["annee_scolaire", "indice_risque", "rang", "rang_min", "rang_max", "palier", "niveau_risque", "ach_t",
             "delta3_ach_points", "pdi_pour_100_eleves_retenu", "contrib_etat", "contrib_tendance", "contrib_exposition"] + rcols]
    res.round(2).to_csv(out / "classement_2024_2025.csv", encoding="utf-8-sig")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 6))
    dd = d.iloc[::-1]
    y = np.arange(len(dd))
    ax.barh(y, dd["contrib_etat"], color="#0B4DBB", label="État (non-achèvement)")
    ax.barh(y, dd["contrib_tendance"], left=dd["contrib_etat"], color="#F39200", label="Tendance (baisse sur 3 ans)")
    ax.barh(y, dd["contrib_exposition"], left=dd["contrib_etat"] + dd["contrib_tendance"], color="#8E8E8E", label="Exposition (déplacés)")
    for i, (idx, v) in enumerate(zip(dd.index, dd["indice_risque"])):
        ax.text(v + 1, i, f"{v:.0f}", va="center", fontsize=9)
    ax.set_yticks(y); ax.set_yticklabels([r.title().replace(" Du ", " du ") for r in dd.index], fontsize=9)
    ax.set_xlim(0, 100); ax.set_xlabel("Indice de risque de décrochage (0 à 100)")
    for b in (20, 40, 55, 70):
        ax.axvline(b, color="#BBBBBB", lw=0.7, ls="--")
    ax.set_title("Indice de risque par région, 2024-2025", fontsize=12, loc="left")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, "Sources : DGESS (primaire 2016-2025) ; CONASUR via Data Pack DCB 2026. Calculs de l'équipe.", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "graphique_indice_2024_2025.png", dpi=160)
    print(res[["indice_risque", "rang", "rang_min", "rang_max", "palier"]].round(1).to_string())


if __name__ == "__main__":
    main()
