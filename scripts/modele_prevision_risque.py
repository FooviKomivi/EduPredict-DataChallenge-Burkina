
import argparse
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss, mean_absolute_error,
                             precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore")
SEUIL = 50.0
F1 = ["ach_t", "d1_ach"]
F2 = ["ach_t", "d1_ach", "d1_eff_pct", "d1_cp1_pct", "ecart_ach_g_f", "eleves_par_ecole"]
SEED = 42


def preparer(p):
    p = p.sort_values(["region", "annee_debut"]).copy()
    g = p.groupby("region")
    p["d1_ach"] = p["ach_t"] - g["ach_t"].shift(1)
    p["d1_eff_pct"] = (p["eff_t"] / g["eff_t"].shift(1) - 1) * 100
    p["d1_cp1_pct"] = (p["cp1_t"] / g["cp1_t"].shift(1) - 1) * 100
    p["ecart_ach_g_f"] = p["ach_g"] - p["ach_f"]
    p["ach_suiv"] = g["ach_t"].shift(-1)
    p["y"] = (p["ach_suiv"] < SEUIL).astype(float).where(p["ach_suiv"].notna())
    return p


def modeles():
    return {
        "Logistique": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
        "Arbre (profondeur 2)": lambda: DecisionTreeClassifier(max_depth=2, min_samples_leaf=4, class_weight="balanced", random_state=SEED),
        "Random Forest": lambda: RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=3, class_weight="balanced", random_state=SEED),
        "Gradient Boosting": lambda: GradientBoostingClassifier(n_estimators=100, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=SEED),
    }


def valider(p, feats, origines=range(2019, 2024)):
    lignes = []
    for t in origines:
        tr = p[(p["annee_debut"] <= t - 1)].dropna(subset=feats + ["y"])      # cibles connues en t
        te = p[p["annee_debut"] == t].dropna(subset=feats + ["y"])
        base_pers = (te["ach_t"] < SEUIL).astype(float)
        base_tend = ((te["ach_t"] + te["d1_ach"]) < SEUIL).astype(float)
        out = te[["region", "annee_debut", "ach_t", "ach_suiv", "y"]].copy()
        out["origine"] = t
        out["Persistance"] = base_pers.values
        out["Tendance lineaire"] = base_tend.values
        for nom, mk in modeles().items():
            m = mk().fit(tr[feats], tr["y"])
            out[nom] = m.predict_proba(te[feats])[:, 1] if tr["y"].nunique() > 1 else 0.0
        lignes.append(out)
    return pd.concat(lignes, ignore_index=True)


def metriques(v, jeu):
    res = []
    y = v["y"].values
    entree = (v["ach_t"] >= SEUIL) & (v["y"] == 1)
    for nom in ["Persistance", "Tendance lineaire"] + list(modeles()):
        s = v[nom].values
        pred = (s >= 0.5).astype(int)
        r = {"jeu_variables": jeu, "modele": nom, "n": len(v),
             "exactitude": accuracy_score(y, pred), "exactitude_equilibree": balanced_accuracy_score(y, pred),
             "precision_risque": precision_score(y, pred, zero_division=0), "rappel_risque": recall_score(y, pred, zero_division=0),
             "entrees_en_zone_detectees": int(((pred == 1) & entree.values).sum()), "entrees_en_zone_total": int(entree.sum()),
             "fausses_alertes": int(((pred == 1) & (y == 0)).sum())}
        if nom in modeles():
            r["brier"] = brier_score_loss(y, s)
            r["auc"] = roc_auc_score(y, s)
        res.append(r)
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--sortie", default=".")
    a = ap.parse_args()
    from pathlib import Path
    out = Path(a.sortie); out.mkdir(parents=True, exist_ok=True)
    p = preparer(pd.read_csv(a.panel))

    allm, allv = [], []
    for jeu, feats in (("F1 (2 variables)", F1), ("F2 (6 variables)", F2)):
        v = valider(p, feats)
        v["jeu_variables"] = jeu
        allv.append(v)
        allm.append(metriques(v, jeu))
    M = pd.concat(allm, ignore_index=True)
    M.round(3).to_csv(out / "metriques_modeles.csv", index=False, encoding="utf-8-sig")
    pd.concat(allv, ignore_index=True).round(3).to_csv(out / "predictions_validation_chronologique.csv", index=False, encoding="utf-8-sig")
    print(M[["jeu_variables", "modele", "n", "exactitude", "exactitude_equilibree", "rappel_risque", "precision_risque",
             "entrees_en_zone_detectees", "entrees_en_zone_total", "fausses_alertes", "brier", "auc"]].round(2).to_string(index=False))

    # ---- regression : taux d'achevement de l'annee suivante ----
    reg = []
    for t in range(2019, 2024):
        tr = p[p["annee_debut"] <= t - 1].dropna(subset=F1 + ["ach_suiv"])
        te = p[p["annee_debut"] == t].dropna(subset=F1 + ["ach_suiv"])
        r = te[["region", "annee_debut", "ach_t", "ach_suiv"]].copy()
        r["Persistance"] = te["ach_t"].values
        r["Tendance lineaire"] = (te["ach_t"] + te["d1_ach"]).values
        r["Ridge"] = Ridge(alpha=10.0).fit(tr[F1], tr["ach_suiv"]).predict(te[F1])
        reg.append(r)
    R = pd.concat(reg, ignore_index=True)
    cmp_ = pd.DataFrame({m: [mean_absolute_error(R["ach_suiv"], R[m])] for m in ["Persistance", "Tendance lineaire", "Ridge"]},
                        index=["erreur_absolue_moyenne_points"]).T
    cmp_["n"] = len(R)
    cmp_.round(2).to_csv(out / "comparaison_regression_achevement.csv", encoding="utf-8-sig")
    print(cmp_.round(2))
    res_pers = (R["ach_suiv"] - R["Persistance"])
    print("Quantiles de l'erreur de persistance (points) 5/25/50/75/95 :", np.round(np.quantile(res_pers, [.05, .25, .5, .75, .95]), 1))

    # ---- prevision 2025-2026 : modeles entraines sur tout le passe connu ----
    tr = p.dropna(subset=F1 + ["y"])
    dern = p[p["annee_debut"] == p["annee_debut"].max()].dropna(subset=F1).copy()
    prev = dern[["region", "ach_t", "d1_ach"]].copy()
    prev["persistance"] = (dern["ach_t"] < SEUIL).astype(int)
    for nom, mk in modeles().items():
        prev["p_" + nom] = mk().fit(tr[F1], tr["y"]).predict_proba(dern[F1])[:, 1]
    prev["p_moyenne_modeles"] = prev[[c for c in prev.columns if c.startswith("p_")]].mean(axis=1)
    # probabilite empirique d'etre sous 50 % : ach_t + erreur de persistance historique
    err = res_pers.values
    prev["p_empirique_persistance"] = [(np.mean((a_ + err) < SEUIL)) for a_ in dern["ach_t"]]
    prev["ach_prevu_ridge"] = Ridge(alpha=10.0).fit(p.dropna(subset=F1 + ["ach_suiv"])[F1], p.dropna(subset=F1 + ["ach_suiv"])["ach_suiv"]).predict(dern[F1])
    prev = prev.sort_values("p_moyenne_modeles", ascending=False)
    prev.round(3).to_csv(out / "prevision_2025_2026.csv", index=False, encoding="utf-8-sig")
    print(prev.round(2).to_string(index=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = prev.sort_values("p_moyenne_modeles")
    fig, ax = plt.subplots(figsize=(9, 5.8))
    ax.barh(d["region"].str.title().str.replace(" Du ", " du "), d["p_moyenne_modeles"] * 100, color="#0B4DBB", label="Moyenne des 4 modèles")
    ax.plot(d["p_empirique_persistance"] * 100, range(len(d)), "o", color="#F39200", label="Approche empirique (erreurs passées)")
    ax.axvline(50, color="#999999", ls="--", lw=0.8)
    ax.set_xlim(0, 100); ax.set_xlabel("Probabilité d'avoir un taux d'achèvement < 50 % en 2025-2026 (%)")
    ax.set_title("Prévision 2025-2026 : probabilité d'être « à risque »", fontsize=12, loc="left")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, "Estimation avec peu de données (13 régions, 2015-2024) : voir la fiabilité dans la documentation. Source : DGESS.", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "graphique_prevision_2025_2026.png", dpi=160)


if __name__ == "__main__":
    main()
