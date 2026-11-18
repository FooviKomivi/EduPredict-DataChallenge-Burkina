
import argparse, tempfile, zipfile
from pathlib import Path
import geopandas as gpd
import pandas as pd

NOMS = {"BF13": "CENTRE", "BF46": "BOUCLE DU MOUHOUN", "BF47": "CASCADES", "BF48": "CENTRE-EST", "BF49": "CENTRE-NORD",
        "BF50": "CENTRE-OUEST", "BF51": "CENTRE-SUD", "BF52": "EST", "BF53": "HAUTS-BASSINS", "BF54": "NORD",
        "BF55": "PLATEAU CENTRAL", "BF56": "SAHEL", "BF57": "SUD-OUEST"}   # 4 premiers caracteres de adm3_pcode_old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cod", required=True); ap.add_argument("--sortie", default="regions_13_simplifie.geojson")
    a = ap.parse_args()
    cod = Path(a.cod)
    corr = pd.read_excel(cod / "bfa_admin_boundaries.xlsx", sheet_name="bfa_admin3")[["adm3_pcode", "adm3_pcode_old"]]
    with tempfile.TemporaryDirectory() as tmp:
        zipfile.ZipFile(cod / "bfa_admin_boundaries.geojson.zip").extractall(tmp)
        g = gpd.read_file(Path(tmp) / "bfa_admin3.geojson")
    g = g.merge(corr, on="adm3_pcode", how="left", suffixes=("", "_x"))
    col = "adm3_pcode_old" if "adm3_pcode_old" in g.columns else "adm3_pcode_old_x"
    g["region"] = g[col].astype(str).str[:4].map(NOMS)
    assert g["region"].notna().all(), "commune sans region"
    r = g[["region", "geometry"]].dissolve(by="region").reset_index().to_crs(4326)
    r["geometry"] = r.geometry.simplify(0.012, preserve_topology=True).buffer(0)
    r.to_file(a.sortie, driver="GeoJSON")
    print(len(r), "regions ecrites dans", a.sortie)


if __name__ == "__main__":
    main()
