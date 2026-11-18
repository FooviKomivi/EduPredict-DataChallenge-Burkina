#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Relance tout le travail EduPredict, de la donnee brute au tableau de bord, en une commande.

Usage : python lancer_pipeline.py --data data --sortie sortie
Organisation attendue du dossier --data (donnees du challenge, non incluses dans ce depot) :
  data/DONNEES_STATISTQUES__PRESCOLAIRE_ET_PRIMAIRE_2016_2025_DCB.xlsx   (un seul .xlsx a la racine)
  data/PDI_CONASUR/                      (Data Pack : 03_Conditions_de_Vie_et_Emploi/PDI_CONASUR)
  data/Annuaires/                        (Data Pack : 01_Education_MENAPLN_DGESS/CNS_DGESS/Annuaires)
  data/Tableaux_de_bord/                 (Data Pack : 01_Education_MENAPLN_DGESS/CNS_DGESS/Tableaux_de_bord)
  data/COD-AB_limites_administratives/   (Data Pack : 04_Cartographie_SIG/COD-AB_limites_administratives)
"""
import argparse, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data"); ap.add_argument("--sortie", default="sortie"); ap.add_argument("--equipe", default="EDUPREDICT")
a = ap.parse_args()
d, s, here = Path(a.data).resolve(), Path(a.sortie).resolve(), (Path(__file__).parent / "scripts").resolve()
xl = sorted(d.glob("*.xlsx"))
if len(xl) != 1:
    sys.exit(f"Il faut exactement un fichier .xlsx a la racine de {d} (trouve : {len(xl)}).")
panel = s / "nettoyage" / "03_transformation" / f"{a.equipe}_03-transformation_D1_engineer_panel-region-annee-primaire_v1.csv"
pdi, risque = s / "pdi", s / "pdi" / "panel_region_annee_primaire_risque.csv"
etapes = [
    ("nettoyage_education_burkina.py", ["--entree", xl[0], "--sortie", s / "nettoyage", "--equipe", a.equipe, "--defi", "D1"]),
    ("extraction_pdi_conasur.py", ["--entree", d / "PDI_CONASUR", "--sortie", pdi, "--panel", panel]),
    ("definition_risque_decrochage.py", ["--panel", pdi / "panel_region_annee_primaire_pdi.csv", "--sortie", risque]),
    ("indice_risque_decrochage.py", ["--panel", risque, "--sortie", s / "indice"]),
    ("modele_prevision_risque.py", ["--panel", risque, "--sortie", s / "modele"]),
    ("extraction_abandons_annuaires.py", ["--entree", d / "Annuaires", "--sortie", s / "abandons"]),
    ("extraction_causes_abandons.py", ["--tdb", d / "Tableaux_de_bord", "--panel", risque, "--classement", s / "indice" / "classement_2024_2025.csv",
                                       "--abandons", s / "abandons" / "abandons_region_annee.csv", "--sortie", s / "abandons"]),
    ("construire_fond_de_carte.py", ["--cod", d / "COD-AB_limites_administratives", "--sortie", s / "regions_13_simplifie.geojson"]),
    ("carte_et_fiches.py", ["--geo", s / "regions_13_simplifie.geojson", "--classement", s / "abandons" / "classement_2024_2025_avec_abandons.csv",
                            "--panel", pdi / "panel_region_annee_primaire_pdi.csv", "--prevision", s / "modele" / "prevision_2025_2026.csv", "--sortie", s / "carte"]),
    ("construire_tableau_de_bord.py", ["--geo", s / "regions_13_simplifie.geojson", "--donnees", s / "carte" / "donnees_dashboard.json",
                                       "--classement", s / "abandons" / "classement_2024_2025_avec_abandons.csv", "--panel", pdi / "panel_region_annee_primaire_pdi.csv",
                                       "--indice", s / "indice" / "indice_risque_region_annee.csv", "--modele", here / "modele_tableau_de_bord.html",
                                       "--sortie", s / "tableau_de_bord_risque_decrochage.html"]),
]
for i, (script, args) in enumerate(etapes, 1):
    print(f"[{i}/{len(etapes)}] {script}", flush=True)
    r = subprocess.run([sys.executable, str(here / script)] + [str(x) for x in args], cwd=here, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Echec a l'etape {i} ({script}) :\n{r.stderr[-1500:]}")
print("Termine. Resultats dans", s.resolve())
