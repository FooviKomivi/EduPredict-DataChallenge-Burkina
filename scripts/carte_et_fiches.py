
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PALIERS = {"Tres eleve": ("Très élevé", "#7F0000"), "Eleve": ("Élevé", "#D7301F"), "Modere eleve": ("Modéré élevé", "#FC8D59"),
           "Modere": ("Modéré", "#FDCC8A"), "Faible": ("Faible", "#FEF0D9")}
BLUE = colors.HexColor("#0B4DBB")


def nom(r):
    return r.title().replace(" Du ", " du ")


def points_attention(x):
    p = []
    p.append(f"Taux d'achèvement du primaire de {x['ach_t']:.0f} % en 2024-2025 (seuil de risque : 50 %).")
    if x["delta3_ach_points"] <= -10:
        p.append(f"Baisse de {abs(x['delta3_ach_points']):.0f} points du taux d'achèvement en 3 ans.")
    if x["pdi_pour_100_eleves_retenu"] >= 30:
        p.append(f"Forte exposition aux déplacés internes ({x['pdi_2022']:,.0f} personnes fin 2022).".replace(",", " "))
    if x["vigilance_orpaillage"] == 1:
        p.append(f"Abandons liés à l'orpaillage, aux mariages et aux grossesses : {x['cas_pour_1000_eleves_2022_2023']:.1f} cas pour 1 000 élèves en 2022-2023 (vigilance).")
    g = x["ach_g"] - x["ach_f"]
    if abs(g) >= 8:
        p.append(f"Écart d'achèvement de {abs(g):.0f} points, plus faible chez les {'garçons' if g < 0 else 'filles'}.")
    pe = x["p_moyenne_modeles"]
    lo, hi = sorted([x["p_empirique_persistance"] * 100, pe * 100])
    texte = f"{hi:.0f} %" if round(lo) == round(hi) else f"entre {lo:.0f} % et {hi:.0f} % selon la méthode"
    p.append(f"Prévision 2025-2026 : probabilité d'être sous 50 % estimée à {texte} (estimation peu fiable).")
    return p[:6]


def recommandations(x):
    bas = x["ach_t"] < 50
    expo = x["pdi_pour_100_eleves_retenu"] >= 30
    g = x["ach_g"] - x["ach_f"]
    rc = []
    if bas and expo:
        rc.append("<b>Continuité éducative :</b> recenser les écoles fermées et les élèves déplacés, ouvrir des classes d'accueil et appuyer les enseignants des zones touchées.")
    if bas and not expo:
        rc.append("<b>Diagnostic local :</b> l'achèvement est sous 50 % sans forte exposition aux déplacés : identifier avec les directions provinciales les causes (distance, coûts, mariages précoces) avant d'agir.")
    if x["vigilance_orpaillage"] == 1:
        rc.append("<b>Abandons liés à l'orpaillage, aux mariages et aux grossesses :</b> sensibiliser les familles et les sites miniers, suivre les élèves en CE et CM1, associer les collectivités.")
    if (not bas) and (x["delta3_ach_points"] <= -10 or expo):
        rc.append("<b>Surveillance renforcée :</b> région encore au-dessus de 50 % mais fragile : suivre l'achèvement chaque année et déclencher une alerte sous 55 %.")
    if g <= -8:
        rc.append("<b>Garçons :</b> repérer et accompagner les garçons qui risquent de quitter l'école avant la fin du primaire.")
    if g >= 8:
        rc.append("<b>Filles :</b> repérer et accompagner les filles qui risquent de quitter l'école avant la fin du primaire.")
    if not rc:
        rc.append("<b>Maintenir et partager :</b> risque faible ; poursuivre le suivi annuel et documenter les pratiques qui expliquent ces résultats.")
    return rc


def main():
    ap = argparse.ArgumentParser()
    for k in ("geo", "classement", "panel", "prevision"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--sortie", default="sortie_carte")
    a = ap.parse_args()
    out = Path(a.sortie); out.mkdir(parents=True, exist_ok=True)

    geo = gpd.read_file(a.geo)
    c = pd.read_csv(a.classement).set_index("region")
    p = pd.read_csv(a.panel)
    pv = pd.read_csv(a.prevision).set_index("region")
    d24 = p[p.annee_debut == 2024].set_index("region")
    d22 = p[p.annee_debut == 2022].set_index("region")
    X = c.join(pv[["p_moyenne_modeles", "p_empirique_persistance"]]).join(d24[["ach_f", "ach_g"]])
    X["pdi_2022"] = d22["pdi_total"]
    geo = geo.merge(X.reset_index(), on="region")
    geo["palier_txt"] = geo["palier"].map(lambda s: PALIERS[s][0])
    geo["couleur"] = geo["palier"].map(lambda s: PALIERS[s][1])

    # ---------- carte statique ----------
    fig, ax = plt.subplots(figsize=(9, 7.4))
    geo.plot(ax=ax, color=geo["couleur"], edgecolor="white", linewidth=1.2)
    for _, r in geo.iterrows():
        pt = r.geometry.representative_point()
        dark = r["palier"] in ("Tres eleve", "Eleve")
        ax.annotate(f"{nom(r['region'])}\n{r['indice_risque']:.0f}", (pt.x, pt.y), ha="center", va="center", fontsize=7.5,
                    color="white" if dark else "#222222", fontweight="bold")
    ax.legend(handles=[Patch(color=v[1], label=v[0]) for k, v in PALIERS.items()], title="Palier de risque", loc="lower left", frameon=False, fontsize=8)
    ax.set_axis_off()
    ax.set_title("Indice de risque de décrochage par région, 2024-2025 (0 à 100)", fontsize=12, loc="left")
    fig.text(0.01, 0.01, "Sources : DGESS (primaire) ; CONASUR ; limites administratives COD-AB regroupées en 13 régions. Calculs de l'équipe.", fontsize=7, color="#666666")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(out / "carte_risque_2024_2025.png", dpi=170)
    plt.close(fig)

    # ---------- fiches ----------
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=3)
    bul = ParagraphStyle("bu", parent=base, leftIndent=12, bulletIndent=2)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11, textColor=BLUE, spaceBefore=6, spaceAfter=3)
    small = ParagraphStyle("s", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor("#555555"))
    ach = p.pivot(index="annee_debut", columns="region", values="ach_t")
    S = []
    for i_reg, (_, r) in enumerate(geo.sort_values("indice_risque", ascending=False).iterrows()):
        reg = r["region"]
        # mini-carte
        f1, a1 = plt.subplots(figsize=(2.6, 2.4))
        geo.plot(ax=a1, color="#E6E6E6", edgecolor="white", linewidth=0.5)
        geo[geo.region == reg].plot(ax=a1, color=r["couleur"], edgecolor="#333333", linewidth=0.8)
        a1.set_axis_off(); f1.tight_layout(pad=0.1)
        f1.savefig(out / f"_mini_{i_reg}.png", dpi=130); plt.close(f1)
        # courbe d'achevement
        f2, a2 = plt.subplots(figsize=(5.2, 2.5))
        yrs = [f"{y}" for y in ach.index]
        a2.plot(ach.index, ach[reg], color="#0B4DBB", marker="o", ms=3.5, lw=1.8, label=nom(reg))
        a2.plot(ach.index, ach.median(axis=1), color="#999999", ls="--", lw=1.2, label="Médiane des 13 régions")
        a2.axhline(50, color="#D7301F", lw=1, ls=":")
        a2.text(ach.index.min(), 51.5, "seuil de risque 50 %", color="#D7301F", fontsize=7)
        a2.set_ylim(0, 100); a2.set_xticks(ach.index); a2.set_xticklabels([f"{y}-{str(y+1)[2:]}" for y in ach.index], fontsize=6.5, rotation=45)
        a2.tick_params(axis="y", labelsize=7); a2.set_ylabel("Taux d'achèvement (%)", fontsize=7.5)
        for s in ("top", "right"):
            a2.spines[s].set_visible(False)
        a2.legend(fontsize=7, frameon=False, loc="lower left"); f2.tight_layout()
        f2.savefig(out / f"_courbe_{i_reg}.png", dpi=150); plt.close(f2)

        titre = Table([[Paragraph(f"<font color='white'><b>Fiche régionale : {nom(reg)}</b></font><br/><font color='white' size=9>Risque de décrochage dans le primaire, 2024-2025</font>",
                                  ParagraphStyle("t", parent=base, fontSize=15, leading=19, textColor=colors.white)),
                       Paragraph(f"<font color='white'><b>{r['indice_risque']:.0f}</b>/100</font><br/><font color='white' size=9>Rang {int(r['rang'])}/13 - {r['palier_txt']}</font>",
                                 ParagraphStyle("t2", parent=base, fontSize=22, leading=26, alignment=2, textColor=colors.white))]],
                      colWidths=[11.2 * cm, 5.8 * cm])
        titre.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                   ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        S += [titre, Spacer(1, 8)]
        kp = [["Taux d'achèvement 2024-2025", f"{r['ach_t']:.0f} %"],
              ["Variation sur 3 ans", f"{r['delta3_ach_points']:+.0f} points"],
              ["Déplacés internes (fin 2022)", f"{r['pdi_2022']:,.0f}".replace(",", " ")],
              ["Abandon CM1 (annuaire 2024-2025)", f"{r['abandon_cm1_t_2024_2025']:.0f} %"],
              ["Niveau selon la définition", {"ELEVE": "Élevé", "A SURVEILLER": "À surveiller", "FAIBLE": "Faible"}.get(r["niveau_risque"], r["niveau_risque"])],
              ["Rang selon la pondération", f"{int(r['rang_min'])} à {int(r['rang_max'])} (selon 5 pondérations)"]]
        kt = Table([[Paragraph(a_, base), Paragraph(f"<b>{b_}</b>", base)] for a_, b_ in kp], colWidths=[5.6 * cm, 3.9 * cm])
        kt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        S += [Table([[Image(str(out / f"_mini_{i_reg}.png"), width=4.6 * cm, height=4.25 * cm), kt]], colWidths=[6.2 * cm, 10.8 * cm],
                    style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")]), Spacer(1, 4)]
        S += [Paragraph("Évolution du taux d'achèvement", h2), Image(str(out / f"_courbe_{i_reg}.png"), width=12.4 * cm, height=5.95 * cm)]
        S += [Paragraph("Points d'attention", h2)] + [Paragraph(t, bul, bulletText="\u2022") for t in points_attention(r)]
        S += [Paragraph("Recommandations", h2)] + [Paragraph(t, bul, bulletText="\u2022") for t in recommandations(r)]
        S += [Paragraph("<i>Pistes proposées par l'équipe à partir des indicateurs, à valider avec les directions régionales et provinciales.</i>", small)]
        S += [Spacer(1, 6), Paragraph("<b>Lecture.</b> L'indice combine l'état (60 %), la tendance sur 3 ans (20 %) et l'exposition aux déplacés (20 %). "
                                      "Le taux d'achèvement est un indicateur de décrochage, pas un taux d'abandon. Le Sahel, l'Est et le Centre-Nord changent d'ordre selon la pondération. "
                                      "Les prévisions reposent sur 13 régions et 10 années : elles sont indicatives.", small),
              Paragraph("Sources : DGESS / MEBAPLN (données statistiques et annuaires du primaire) ; CONASUR (déplacés internes) ; COD-AB. Calculs de l'équipe EduPredict, Data Challenge Burkina 2026.", small),
              PageBreak()]
    doc = SimpleDocTemplate(str(out / "fiches_regionales_2024_2025.pdf"), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm, bottomMargin=1.2 * cm,
                            title="Fiches régionales - risque de décrochage 2024-2025", author="Équipe EduPredict")
    doc.build(S[:-1])
    for f in out.glob("_*.png"):
        f.unlink()

    # ---------- donnees dashboard ----------
    ts = p.pivot(index="annee_debut", columns="region", values="ach_t")
    js = {"annees": [int(y) for y in ts.index], "regions": []}
    for _, r in geo.sort_values("indice_risque", ascending=False).iterrows():
        js["regions"].append({"n": nom(r["region"]), "k": r["region"], "i": round(r["indice_risque"], 1), "r": int(r["rang"]), "pal": r["palier_txt"], "c": r["couleur"],
                              "ach": round(r["ach_t"], 1), "d3": round(r["delta3_ach_points"], 1), "pdi": int(r["pdi_2022"]),
                              "cm1": round(r["abandon_cm1_t_2024_2025"], 1), "orp": round(r["cas_pour_1000_eleves_2022_2023"], 1),
                              "pp": round(float(r["p_moyenne_modeles"]) * 100), "pe": round(float(r["p_empirique_persistance"]) * 100),
                              "serie": [round(float(v), 1) for v in ts[r["region"]].values], "pt": points_attention(r)})
    (out / "donnees_dashboard.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    print("ok", len(js["regions"]))


if __name__ == "__main__":
    main()
