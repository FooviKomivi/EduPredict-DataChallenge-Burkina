
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from nettoyage_education_burkina import REGIONS, cle, std_region, to_num

NIVEAUX = ["CP1", "CP2", "CE1", "CE2", "CM1", "CM2"]
SEXES = ["G", "F", "T"]
LIBELLES = {"TXPROM": "promotion", "TXRED": "redoublement", "TXABAN": "abandon"}


def lire_annuaire(chemin):
    d = pd.read_csv(chemin, sep=";", encoding="utf-8-sig", dtype=str)
    cells = [c for c in d.columns if re.fullmatch(r"c\d+", c)]
    d["page"] = d["page"].astype(int)
    d["ligne"] = d["ligne"].astype(int)
    d["cells"] = d[cells].apply(lambda r: [("" if pd.isna(x) else str(x).strip()) for x in r], axis=1)
    return d


def pages_tableau(d):
    """Pages du tableau : celles qui contiennent des lignes 'TX Aban' (titre parfois tronque selon l'annee)."""
    t = d["cells"].map(lambda c: any(cle(x) == "TXABAN" for x in c))
    return sorted(set(d.loc[t, "page"]))


def valeurs_apres(cells, j):
    v = [to_num(x) for x in cells[j + 1:]]
    while v and np.isnan(v[-1]):
        v.pop()
    return v


def extraire(chemin, annee_debut):
    d = lire_annuaire(chemin)
    pages = pages_tableau(d)
    lignes = d[d["page"].isin(pages)].sort_values(["page", "ligne"])
    region_courante, prec_seul = None, ""
    recents = {}      # derniers 'TX Prom', 'TX Aban' vus (les trois lignes d'une zone se suivent)
    out = []
    for _, r in lignes.iterrows():
        cells = []
        for c in r["cells"]:
            m = re.match(r"^(.+?)\s+(TX\s*(?:Prom|Red|Aban))$", c, flags=re.I)     # 'PLATEAU CENTRAL TX Red' fusionne
            cells += [m.group(1), m.group(2)] if m else [c]
        non_vides = [c for c in cells if c]
        if not non_vides:
            continue
        cles_cells = [cle(c) for c in cells]
        # ligne qui ne contient qu'un nom de region : debut de region
        if len(non_vides) == 1:
            reg = std_region(non_vides[0])
            if reg in REGIONS:
                region_courante = reg
            else:
                prec_seul = non_vides[0]          # debut d'un nom de region coupe sur deux lignes
            continue
        jt = next((j for j, k in enumerate(cles_cells) if k in LIBELLES), None)
        if jt is None and cles_cells[0] == "TOTALNATIONAL":      # ligne nationale : l'etiquette 'TX Red' est absente
            ind, vals, nom = "redoublement", valeurs_apres(cells, 0), cells[0]
        elif jt is None:
            continue
        else:
            ind = LIBELLES[cles_cells[jt]]
            vals = valeurs_apres(cells, jt)
            nom = cells[jt - 1] if jt > 0 else ""
        if ind == "promotion":
            recents = {"promotion": vals, "nom_prom": nom}
            continue
        if ind == "redoublement":
            nom_zone = nom
            recents["redoublement"] = vals
            recents["nom_zone"] = nom_zone
            recents["nom_complet"] = (prec_seul + " " + nom).strip() if prec_seul else nom
            prec_seul = ""
            continue
        if ind == "abandon":
            recents["abandon"] = vals
            nz = recents.get("nom_zone", "")
            complet = recents.get("nom_complet", nz)
            reg_nom = complet if std_region(complet) == region_courante else nz
            est_region = (std_region(reg_nom) in REGIONS) and (std_region(reg_nom) == region_courante)
            est_national = cle(nz) in ("BURKINAFASO", "NATIONAL", "TOTAL", "TOTALNATIONAL")
            if est_region or est_national:
                zone = region_courante if est_region else "NATIONAL"
                for indic in ("promotion", "redoublement", "abandon"):
                    v = recents.get(indic, [])
                    n_niv = len(v) // 3
                    for kk, val in enumerate(v):
                        if kk // 3 >= len(NIVEAUX):
                            break
                        out.append({"region": zone, "annee_debut": annee_debut, "indicateur": indic,
                                    "niveau": NIVEAUX[kk // 3], "sexe": SEXES[kk % 3], "valeur": val})
            recents = {}
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entree", required=True)
    ap.add_argument("--sortie", default="sortie_abandons")
    a = ap.parse_args()
    ent, sortie = Path(a.entree), Path(a.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    frames, ctl = [], []
    for f in sorted(ent.glob("CNS5*Annuaire*rimaire*.csv")):
        m = re.search(r"(\d{4})_(\d{4})", f.name)
        ad = int(m.group(1))
        df = extraire(f, ad)
        frames.append(df)
        nb = df[df.region != "NATIONAL"].region.nunique() if len(df) else 0
        ctl.append({"annee_scolaire": f"{ad}-{ad + 1}", "regions_trouvees": nb,
                    "national_trouve": int((df.region == "NATIONAL").any()) if len(df) else 0, "fichier": f.name})
    long = pd.concat(frames, ignore_index=True)
    long["annee_scolaire"] = long["annee_debut"].astype(str) + "-" + (long["annee_debut"] + 1).astype(str)
    long.to_csv(sortie / "taux_promotion_redoublement_abandon_region.csv", index=False, encoding="utf-8-sig")

    ab = long[long.indicateur == "abandon"].pivot_table(index=["region", "annee_debut"], columns=["niveau", "sexe"], values="valeur")
    res = pd.DataFrame(index=ab.index)
    for s in SEXES:
        surv = pd.Series(1.0, index=ab.index)
        for niv in ["CP1", "CP2", "CE1", "CE2", "CM1"]:
            if (niv, s) in ab.columns:
                surv = surv * (1 - ab[(niv, s)].fillna(0) / 100)
        res[f"abandon_cumule_{s.lower()}_pct"] = (1 - surv) * 100
    for niv in ["CP1", "CE1", "CM1"]:
        if (niv, "T") in ab.columns:
            res[f"abandon_{niv.lower()}_t"] = ab[(niv, "T")]
    red = long[(long.indicateur == "redoublement") & (long.sexe == "T")].groupby(["region", "annee_debut"])["valeur"].mean()
    res["redoublement_moyen_t"] = red
    res = res.reset_index()
    res["annee_scolaire"] = res["annee_debut"].astype(str) + "-" + (res["annee_debut"] + 1).astype(str)
    res.to_csv(sortie / "abandons_region_annee.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ctl).to_csv(sortie / "controle_abandons.csv", index=False, encoding="utf-8-sig")
    print(pd.DataFrame(ctl).to_string(index=False))


if __name__ == "__main__":
    main()
