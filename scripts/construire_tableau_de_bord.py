
import argparse, json, math
import geopandas as gpd
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    for k in ("geo", "donnees", "classement", "panel", "indice", "modele"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--sortie", default="tableau_de_bord_risque_decrochage.html")
    a = ap.parse_args()
    g = gpd.read_file(a.geo)
    g["geometry"] = g.geometry.simplify(0.025, preserve_topology=True)
    minx, miny, maxx, maxy = g.total_bounds
    k = 100; cx = math.cos(math.radians((miny + maxy) / 2))
    P = lambda x, y: ((x - minx) * cx * k, (maxy - y) * k)

    def path(geom):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        return "".join("M" + "L".join("%d,%d" % P(x, y) for x, y in pl.exterior.coords) + "Z" for pl in polys)

    W, H = round((maxx - minx) * cx * k), round((maxy - miny) * k)
    d = json.load(open(a.donnees, encoding="utf-8"))
    c = pd.read_csv(a.classement).set_index("region")
    pan = pd.read_csv(a.panel); d24 = pan[pan.annee_debut == 2024].set_index("region")
    iy = pd.read_csv(a.indice).pivot(index="region", columns="annee_debut", values="indice_risque")
    R = []
    for r in d["regions"]:
        K = r["k"]; geom = g[g.region == K].geometry.iloc[0]; rp = geom.representative_point(); lx, ly = P(rp.x, rp.y)
        R.append(dict(n=r["n"], iy=[round(float(v), 1) for v in iy.loc[K, [2019, 2020, 2021, 2022, 2023, 2024]]], s=r["serie"], p=r["pdi"],
                      m=r["cm1"], o=r["orp"], pp=r["pp"], pe=r["pe"], x=int(c.loc[K, "pdi_pour_100_eleves_retenu"] >= 30),
                      v=int(c.loc[K, "vigilance_orpaillage"]), g=round(float(d24.loc[K, "ach_g"] - d24.loc[K, "ach_f"]), 1),
                      lx=round(lx), ly=round(ly), pa=path(geom)))
    html = open(a.modele, encoding="utf-8").read()
    html = html.replace("@DATA@", json.dumps(R, ensure_ascii=False, separators=(",", ":"))).replace("@W@", str(W)).replace("@H@", str(H))
    open(a.sortie, "w", encoding="utf-8").write(html)
    print("Ecrit :", a.sortie)


if __name__ == "__main__":
    main()
