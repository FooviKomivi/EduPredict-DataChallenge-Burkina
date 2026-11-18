
import argparse
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from nettoyage_education_burkina import cle, std_region, to_num

# situations au format CONASUR "commune" : fichier -> date de la situation
FICHIERS = {
    "situation-pdis-27012020__Situation_par_communes.csv": date(2020, 1, 27),
    "situation_pdi_09072020__Feuil1.csv": date(2020, 7, 9),
    "situation_pdi_08082020__080820.csv": date(2020, 8, 8),
    "situation_pdi_31122020__31122020.csv": date(2020, 12, 31),
    "situation_pdi_31032021__31032021.csv": date(2021, 3, 31),
    "situation_pdi_31052021__310521.csv": date(2021, 5, 31),
    "situation_pdi_30062021__30_06_2021.csv": date(2021, 6, 30),
    "situation_pdi_31072021__31_07_2021.csv": date(2021, 7, 31),
    "situation_pdi_30112021__30_11_2021.csv": date(2021, 11, 30),
    "situation-des-pdi-par-communes-30-novembre-2022-1__30_11_2022.csv": date(2022, 11, 30),
    "situation-des-pdi-par-communes-accueil-du-31-decembre-2022-1__31122022.csv": date(2022, 12, 31),
}
COLS_REGION = {"REGIONS", "REGION", "REGIONDESTINATION"}
COLS_TOTAL = {"NOMBRETOTALDEPDI", "TOTALPDIS", "TOTALINDIVIDUS", "TOTALPDI"}
NAT_PUBLIE = {date(2022, 11, 30): 1810105}   # ligne 'Ensemble' du fichier du 30/11/2022


def lire(chemin):
    return pd.read_csv(chemin, sep=";", encoding="utf-8-sig", dtype=str, header=None)


def snapshot_commune(chemin, d):
    df = lire(chemin)
    h = next(i for i in range(min(25, len(df)))
             if any(cle(x) in COLS_REGION for x in df.iloc[i].dropna()))
    ent = [cle(x) if pd.notna(x) else "" for x in df.iloc[h]]
    jr = next(j for j, c in enumerate(ent) if c in COLS_REGION)
    jt = next(j for j, c in enumerate(ent) if c in COLS_TOTAL)
    sub = df.iloc[h + 1:, [jr, jt]].copy()
    sub.columns = ["region_brut", "pdi"]
    sub["region"] = sub["region_brut"].map(lambda v: std_region(v) if pd.notna(v) else None)
    sub = sub[sub["region"].isin(__import__("nettoyage_education_burkina").REGIONS)]
    sub["pdi"] = sub["pdi"].map(to_num)
    out = sub.groupby("region", as_index=False)["pdi"].sum()
    out["date_situation"] = d
    out["source"] = Path(chemin).name
    return out


def snapshot_dgess_2019(chemin):
    """situation_pdis_14022020xlsx__PDI.csv : colonne 'date donnee' (plusieurs dates)."""
    df = lire(chemin)
    h = next(i for i in range(10) if any(cle(x) == "DATEDONNEE" for x in df.iloc[i].dropna()))
    ent = [cle(x) if pd.notna(x) else "" for x in df.iloc[h]]
    jr = ent.index("REGIONDESTINATION"); jt = ent.index("TOTALINDIVIDUS"); jd = ent.index("DATEDONNEE")
    sub = df.iloc[h + 2:, [jr, jt, jd]].copy()
    sub.columns = ["region_brut", "pdi", "d"]
    sub["region"] = sub["region_brut"].map(lambda v: std_region(v) if pd.notna(v) else None)
    sub = sub[sub["region"].isin(__import__("nettoyage_education_burkina").REGIONS)]
    sub["pdi"] = sub["pdi"].map(to_num)
    sub["date_situation"] = pd.to_datetime(sub["d"], errors="coerce").dt.date
    out = sub.dropna(subset=["date_situation"]).groupby(["region", "date_situation"], as_index=False)["pdi"].sum()
    out["source"] = Path(chemin).name
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entree", required=True)
    ap.add_argument("--sortie", default="sortie_pdi")
    ap.add_argument("--panel", default=None)
    a = ap.parse_args()
    ent, out = Path(a.entree), Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)

    morceaux, controles = [], []
    for f, d in FICHIERS.items():
        s = snapshot_commune(ent / f, d)
        morceaux.append(s)
        controles.append({"date_situation": d, "nb_regions": s["region"].nunique(), "total_pdi": s["pdi"].sum(),
                          "total_publie": NAT_PUBLIE.get(d, np.nan), "source": f})
    try:
        s19 = snapshot_dgess_2019(ent / "situation_pdis_14022020xlsx__PDI.csv")
        morceaux.append(s19)
        for d, g in s19.groupby("date_situation"):
            controles.append({"date_situation": d, "nb_regions": g["region"].nunique(), "total_pdi": g["pdi"].sum(),
                              "total_publie": np.nan, "source": g["source"].iloc[0]})
    except Exception as e:
        print("Fichier 2019 ignore :", e)

    dates = pd.concat(morceaux, ignore_index=True)
    dates["date_situation"] = pd.to_datetime(dates["date_situation"])
    # deux fichiers donnent la meme situation du 27/01/2020 (valeurs identiques) : on garde une seule ligne
    dates = dates.sort_values(["date_situation", "region"]).drop_duplicates(["region", "date_situation"])
    dates.to_csv(out / "pdi_region_dates.csv", index=False, encoding="utf-8-sig")
    ctl = pd.DataFrame(controles)
    ctl["ecart_pct"] = (ctl["total_pdi"] - ctl["total_publie"]) / ctl["total_publie"] * 100
    ctl.to_csv(out / "controles_pdi.csv", index=False, encoding="utf-8-sig")

    # une valeur par annee scolaire : situation la plus proche du 31 decembre de annee_debut
    lignes = []
    for ad in range(2018, 2023):
        cible = pd.Timestamp(ad, 12, 31)
        dispo = dates.groupby("date_situation").region.nunique()
        dispo = dispo[dispo >= 12].index      # situations couvrant (presque) toutes les regions
        if not len(dispo):
            continue
        proche = min(dispo, key=lambda x: abs((x - cible).days))
        if abs((proche - cible).days) > 60:      # pas de situation assez proche du 31 decembre : annee non renseignee
            continue
        sel = dates[dates["date_situation"] == proche].copy()
        sel["annee_debut"] = ad
        sel["annee_scolaire"] = f"{ad}-{ad + 1}"
        sel["ecart_jours_au_31_dec"] = (proche - cible).days
        lignes.append(sel)
    ann = pd.concat(lignes, ignore_index=True)
    ann = ann.rename(columns={"pdi": "pdi_total", "date_situation": "date_situation_retenue"})
    ann = ann[["region", "annee_scolaire", "annee_debut", "pdi_total", "date_situation_retenue", "ecart_jours_au_31_dec", "source"]]
    ann.to_csv(out / "pdi_region_annee.csv", index=False, encoding="utf-8-sig")

    if a.panel:
        p = pd.read_csv(a.panel)
        m = p.merge(ann[["region", "annee_debut", "pdi_total"]], on=["region", "annee_debut"], how="left")
        m["pdi_pour_100_eleves"] = m["pdi_total"] / m["eff_t"] * 100
        m.to_csv(out / "panel_region_annee_primaire_pdi.csv", index=False, encoding="utf-8-sig")
    print(ctl.to_string(index=False))


if __name__ == "__main__":
    main()
