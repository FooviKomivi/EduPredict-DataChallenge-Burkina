
import argparse
import numpy as np
import pandas as pd

SEUIL_ACH = 50.0      # % d'achevement
SEUIL_TEND = -10.0    # points sur 3 ans
SEUIL_PDI = 30.0      # deplaces pour 100 eleves
SEUIL_CHUTE_EFF = -15.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--sortie", default="panel_region_annee_primaire_risque.csv")
    a = ap.parse_args()
    p = pd.read_csv(a.panel).sort_values(["region", "annee_debut"]).reset_index(drop=True)
    g = p.groupby("region")

    p["delta3_ach_points"] = p["ach_t"] - g["ach_t"].shift(3)
    p["delta3_eff_pct"] = (p["eff_t"] / g["eff_t"].shift(3) - 1) * 100
    p["ecart_ach_g_moins_f"] = p["ach_g"] - p["ach_f"]

    # exposition : derniere situation connue des deplaces (2022 reportee sur 2023-2024)
    p["pdi_retenu"] = g["pdi_total"].ffill()
    p["pdi_pour_100_eleves_retenu"] = p["pdi_retenu"] / p["eff_t"] * 100
    p["exposition_evaluee"] = (p["annee_debut"] >= 2019).astype(int)

    p["etat_critique"] = (p["ach_t"] < SEUIL_ACH).astype(int)
    p["tendance_forte_baisse"] = (p["delta3_ach_points"] <= SEUIL_TEND).astype(int)
    p["exposition_forte"] = ((p["pdi_pour_100_eleves_retenu"] >= SEUIL_PDI) & (p["exposition_evaluee"] == 1)).astype(int)
    p["chute_effectifs_1an"] = (p["variation_eff_t_pct"] <= SEUIL_CHUTE_EFF).astype(int)

    surv = (p["tendance_forte_baisse"] == 1) | (p["exposition_forte"] == 1)
    p["niveau_risque"] = np.where(p["etat_critique"] == 1, "ELEVE", np.where(surv, "A SURVEILLER", "FAIBLE"))
    p.to_csv(a.sortie, index=False, encoding="utf-8-sig")

    d = p[p["annee_debut"] == p["annee_debut"].max()].sort_values("ach_t")
    print(d[["region", "annee_scolaire", "ach_t", "delta3_ach_points", "pdi_pour_100_eleves_retenu", "niveau_risque"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
