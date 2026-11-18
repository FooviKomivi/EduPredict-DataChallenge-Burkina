
import argparse, glob, re
from pathlib import Path
import numpy as np
import pandas as pd
from nettoyage_education_burkina import REGIONS, std_region, to_num


def causes(tdb):
    rows = []
    for motif, ad in (("CNS574*", 2021), ("CNS565*", 2022)):
        f = glob.glob(str(Path(tdb) / motif))[0]
        d = pd.read_csv(f, sep=";", encoding="utf-8-sig", dtype=str)
        cells = [c for c in d.columns if re.fullmatch(r"c\d+", c)]
        d["page"] = d["page"].astype(int); d["ligne"] = d["ligne"].astype(int)
        for _, r in d[d.page == 44].sort_values("ligne").iterrows():
            c = [("" if pd.isna(v) else str(v).strip()) for v in r[cells]]
            reg = std_region(c[0]) if c[0] else None
            if reg in REGIONS:
                v = [to_num(t) for t in c[1:4]]
                if not any(np.isnan(v)):
                    rows.append({"region": reg, "annee_debut": ad, "orpaillage": v[0], "mariage": v[1], "grossesse": v[2]})
    z = pd.DataFrame(rows)
    z["cas_total"] = z[["orpaillage", "mariage", "grossesse"]].sum(axis=1)
    return z


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tdb", required=True); ap.add_argument("--panel", required=True)
    ap.add_argument("--classement"); ap.add_argument("--abandons"); ap.add_argument("--sortie", default="sortie_abandons")
    a = ap.parse_args()
    out = Path(a.sortie); out.mkdir(parents=True, exist_ok=True)
    z = causes(a.tdb)
    eff = pd.read_csv(a.panel)[["region", "annee_debut", "eff_t"]]
    z = z.merge(eff, on=["region", "annee_debut"])
    z["cas_pour_1000_eleves"] = z["cas_total"] / z["eff_t"] * 1000
    z["part_orpaillage_pct"] = z["orpaillage"] / z["cas_total"] * 100
    z["annee_scolaire"] = z["annee_debut"].astype(str) + "-" + (z["annee_debut"] + 1).astype(str)
    z.round(2).to_csv(out / "abandons_causes_region.csv", index=False, encoding="utf-8-sig")
    if a.classement and a.abandons:
        c = pd.read_csv(a.classement)
        ab = pd.read_csv(a.abandons); ab = ab[(ab.region != "NATIONAL") & (ab.annee_debut == 2024)]
        ab = ab[["region", "abandon_cp1_t", "abandon_ce1_t", "abandon_cm1_t", "abandon_cumule_t_pct"]].add_suffix("_2024_2025").rename(columns={"region_2024_2025": "region"})
        cz = z[z.annee_debut == 2022][["region", "cas_total", "cas_pour_1000_eleves", "part_orpaillage_pct"]].add_suffix("_2022_2023").rename(columns={"region_2022_2023": "region"})
        m = c.merge(ab, on="region", how="left").merge(cz, on="region", how="left")
        m["vigilance_orpaillage"] = (m["cas_pour_1000_eleves_2022_2023"] >= 9).astype(int)
        m.round(2).to_csv(out / "classement_2024_2025_avec_abandons.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
