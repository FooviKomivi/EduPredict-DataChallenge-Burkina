
import argparse
import re
import shutil
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl.utils import get_column_letter


# 0. Utilitaires
JOURNAL = []        # journal de nettoyage
TOTAUX = {}         # lignes de total publiees, gardees pour verification
CONTROLES = []      # resume des controles
ECARTS = []         # detail des ecarts de controle
ANOMALIES = []      # variations suspectes


def log(etape, table, action, nb=""):
    JOURNAL.append({"etape": etape, "table": table, "action": action, "nb_elements": nb})


def sans_accent(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def cle(s):
    """Cle de comparaison : premiere ligne, sans accent, majuscules, lettres/chiffres seulement."""
    s = sans_accent(str(s).split("\n")[0]).upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def propre(s):
    return re.sub(r"\s+", " ", str(s).split("\n")[0]).strip()


def to_num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v)
    s = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_annee(cell):
    """Retourne annee_debut (int) ou None. '2015-2016','2015/16','2024/25' -> debut ; '2016','2016.0' -> 2015."""
    if pd.isna(cell):
        return None
    s = str(cell).split("\n")[0].strip()
    m = re.match(r"^(\d{4})(?:\s*[-/]\s*(\d{2,4}))?", s)
    if not m:
        return None
    y = int(m.group(1))
    return y if m.group(2) else y - 1



# 1. Referentiels et harmonisation des libelles

REGIONS = ["BOUCLE DU MOUHOUN", "CASCADES", "CENTRE", "CENTRE-EST", "CENTRE-NORD", "CENTRE-OUEST",
           "CENTRE-SUD", "EST", "HAUTS-BASSINS", "NORD", "PLATEAU CENTRAL", "SAHEL", "SUD-OUEST"]
CLE_REGION = {cle(r): r for r in REGIONS}
CLE_REGION["HAUTBASSINS"] = "HAUTS-BASSINS"          # variante 'HAUT-BASSINS' dans les feuilles 9 et 13
NATIONAL = {"NATIONAL", "BURKINAFASO", "TOTALGENERAL", "TOTAL"}


def _inconnu(v):
    t = propre(v)
    if "NOTE FOR ANY AUTOMATED" in t.upper():
        t = "<texte parasite adresse a un assistant IA>"
    return "?" + t[:40]


def std_region(v):
    if pd.isna(v):
        return None
    k = cle(v)
    if k in CLE_REGION:
        return CLE_REGION[k]
    if k in NATIONAL:
        return "NATIONAL"
    if k.startswith("TOTAL") and k[5:] in CLE_REGION:
        return "TOTAL:" + CLE_REGION[k[5:]]
    return _inconnu(v)


def std_sexe(v):
    if pd.isna(v):
        return None
    m = {"G": "G", "GARCONS": "G", "GARCON": "G", "F": "F", "FILLES": "F", "FILLE": "F",
         "T": "T", "TOTAL": "T", "ENSEMBLE": "T"}
    return m.get(cle(v), _inconnu(v))


def std_statut(v):
    if pd.isna(v):
        return None
    k = cle(v)
    m = {"PUBLIC": "Public", "PRIVE": "Prive", "PRIVEE": "Prive", "COMMUNAUTAIRE": "Communautaire",
         "TOTAL": "TOTAL", "TOTALGENERAL": "TOTAL", "NATIONAL": "TOTAL"}
    if k in m:
        return m[k]
    if k.startswith("TOTAL"):
        return "TOTAL:" + {"PUBLIC": "Public", "PRIVE": "Prive", "COMMUNAUTAIRE": "Communautaire"}.get(k[5:], k[5:])
    return _inconnu(v)


def std_milieu(v):
    if pd.isna(v):
        return None
    k = cle(v)
    m = {"URBAIN": "Urbain", "RURAL": "Rural", "INDETERMINE": "Indetermine",
         "NATIONAL": "TOTAL", "TOTALGENERAL": "TOTAL", "TOTAL": "TOTAL"}
    return m.get(k, _inconnu(v))


def std_niveau(v):
    if pd.isna(v):
        return None
    k = cle(v)
    m = {"CP1": "CP1", "CP2": "CP2", "CE1": "CE1", "CE2": "CE2", "CM1": "CM1", "CM2": "CM2",
         "GRANDESECTION": "Grande section", "MOYENNESECTION": "Moyenne section",
         "PETITESECTION": "Petite section", "TOTAL": "TOTAL"}
    return m.get(k, _inconnu(v))


STD = {"region": std_region, "sexe": std_sexe, "statut": std_statut, "milieu": std_milieu, "niveau": std_niveau}


def est_total(df, cles):
    m = pd.Series(False, index=df.index)
    for c in cles:
        if c == "sexe":
            continue
        s = df[c].astype(str)
        m |= s.eq("NATIONAL") | s.str.startswith("TOTAL")
    return m



# 2. Lecture et mise en format long
def lire_feuille(xlsx, nom):
    return pd.read_excel(xlsx, sheet_name=nom, header=None, dtype=object)


def scanner_consignes(xlsx):
    """Repere les cellules qui contiennent du texte adresse a un assistant IA (consigne injectee) : on les ignore."""
    for nom in pd.ExcelFile(xlsx).sheet_names:
        df = lire_feuille(xlsx, nom)
        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                v = df.iat[i, j]
                if isinstance(v, str) and "NOTE FOR ANY AUTOMATED" in v.upper():
                    log("00-lecture", nom, f"Cellule {get_column_letter(j + 1)}{i + 1} : texte parasite (consigne "
                        "adressee a un assistant IA) ignore ; seule la 1re ligne de la cellule est conservee", 1)


def en_tetes_annees(ligne, n_cles, sexes=None):
    """Liste des annee_debut pour chaque colonne de valeurs. Si sexes est fourni, l'annee est propagee sur G/F/T."""
    out, cur = [], None
    for j, v in enumerate(ligne[n_cles:]):
        if sexes is not None:
            if pd.notna(v):
                cur = parse_annee(v)
            out.append(cur if (sexes[j] is not None) else None)
        else:
            out.append(parse_annee(v))
    return out


def assembler(table, cles, keys, vals, annees, sexes=None, extra=None):
    """Construit la table longue propre + les lignes de total. keys/vals : DataFrames bruts alignes."""
    k = keys.reset_index(drop=True).copy()
    k.columns = cles
    vals = vals.reset_index(drop=True)
    # Les lignes 'Total ...' sans derniere cle : on met 'Total' comme derniere cle
    premiere = k.iloc[:, 0].map(lambda x: cle(x).startswith("TOTAL") if pd.notna(x) else False)
    k.loc[premiere & k[cles[-1]].isna(), cles[-1]] = "Total"
    for c in cles[:-1]:
        k[c] = k[c].ffill()                       # cles hierarchiques : on propage vers le bas
    frames = []
    for j, a in enumerate(annees):
        if a is None or j >= vals.shape[1]:
            continue
        d = k.copy()
        d["annee_debut"] = a
        if sexes is not None:
            d["sexe"] = sexes[j]
        d["valeur_brute"] = vals.iloc[:, j].values
        frames.append(d)
    long = pd.concat(frames, ignore_index=True)
    n0 = len(long)
    long = long[long[cles[-1]].notna()].copy()    # lignes vides / notes
    cles_all = list(cles) + (["sexe"] if (sexes is not None and "sexe" not in cles) else [])
    for c in cles_all:
        long[c] = long[c].map(STD[c])
    inconnus = long[long[cles_all].apply(lambda s: s.astype(str).str.startswith("?")).any(axis=1)]
    if len(inconnus):
        vus = sorted({str(v)[1:] for c in cles_all for v in inconnus[c] if str(v).startswith("?")})
        log("02-nettoyage", table, f"Libelles non reconnus ignores : {vus[:8]}", len(inconnus))
        long = long.drop(inconnus.index)
    # 'Total X' ranges comme region/statut : on remet la bonne cle et on marque la ligne comme total
    if "region" in cles_all and "statut" in cles_all:
        m = long["region"].astype(str).str.startswith("TOTAL:")
        long.loc[m, "statut"] = "TOTAL"
        long.loc[m, "region"] = long.loc[m, "region"].str[6:]
    if "niveau" in cles_all and "statut" in cles_all:
        m = long["statut"].astype(str).str.startswith("TOTAL:")
        long.loc[m, "niveau"] = "TOTAL"
        long.loc[m, "statut"] = long.loc[m, "statut"].str[6:]
    long["valeur"] = long["valeur_brute"].map(to_num)
    manquants = long["valeur"].isna().sum()
    if manquants:
        log("02-nettoyage", table, "Valeurs vides ou non numeriques supprimees", int(manquants))
    long = long.dropna(subset=["valeur"]).drop(columns="valeur_brute")
    long["annee_debut"] = long["annee_debut"].astype(int)
    long["annee_scolaire"] = long["annee_debut"].astype(str) + "-" + (long["annee_debut"] + 1).astype(str)
    if extra:
        for c, v in extra.items():
            long[c] = v
    t = est_total(long, cles_all)
    totaux = long[t].copy()
    propre_df = long[~t].copy()
    if len(totaux):
        log("02-nettoyage", table, "Lignes de total retirees de la table propre (gardees pour controle)", int(len(totaux)))
    ordre = cles_all + (list(extra) if extra else []) + ["annee_scolaire", "annee_debut", "valeur"]
    return propre_df[ordre].reset_index(drop=True), totaux[ordre].reset_index(drop=True)


def feuille_longue(xlsx, feuille, table, cles, triples=False, entete=1, extra=None):
    df = lire_feuille(xlsx, feuille)
    n = len(cles)
    if triples:
        sexes_brut = df.iloc[entete + 1, n:].tolist()
        sexes = [std_sexe(x) if pd.notna(x) else None for x in sexes_brut]
        annees = en_tetes_annees(df.iloc[entete].tolist(), n, sexes)
        r0 = entete + 2
    else:
        sexes = None
        annees = en_tetes_annees(df.iloc[entete].tolist(), n)
        r0 = entete + 1
    keys, vals = df.iloc[r0:, :n], df.iloc[r0:, n:]
    return assembler(table, cles, keys, vals, annees, sexes, extra)


def bloc_prescolaire(df, debut, fin, table, cles, triples):
    n = len(cles)
    if triples:
        sexes = [std_sexe(x) if pd.notna(x) else None for x in df.iloc[debut + 2, n:].tolist()]
        annees = en_tetes_annees(df.iloc[debut + 1].tolist(), n, sexes)
        r0 = debut + 3
    else:
        sexes = None
        annees = en_tetes_annees(df.iloc[debut + 1].tolist(), n)
        r0 = debut + 2
    return assembler(table, cles, df.iloc[r0:fin, :n], df.iloc[r0:fin, n:], annees, sexes)



# 3. Controles de coherence

def _comparer(table, test, calc, pub, on, tol=0.005):
    m = calc.merge(pub, on=on, suffixes=("_calcule", "_publie"))
    if m.empty:
        CONTROLES.append({"table": table, "test": test, "nb_comparaisons": 0, "nb_ecarts": 0, "ecart_max_pct": np.nan})
        return
    m["ecart_pct"] = (m["valeur_calcule"] - m["valeur_publie"]) / m["valeur_publie"].replace(0, np.nan) * 100
    ko = m[m["ecart_pct"].abs() > tol * 100]
    CONTROLES.append({"table": table, "test": test, "nb_comparaisons": len(m), "nb_ecarts": len(ko),
                      "ecart_max_pct": round(float(m["ecart_pct"].abs().max()), 3)})
    if len(ko):
        d = ko.copy()
        d.insert(0, "test", test)
        d.insert(0, "table", table)
        ECARTS.append(d)


def controle_gft(table, df, cles_hors_sexe):
    p = df.pivot_table(index=cles_hors_sexe + ["annee_debut"], columns="sexe", values="valeur", aggfunc="sum").reset_index()
    if not {"G", "F", "T"}.issubset(p.columns):
        return
    calc = p[cles_hors_sexe + ["annee_debut"]].assign(valeur=p["G"] + p["F"])
    pub = p[cles_hors_sexe + ["annee_debut"]].assign(valeur=p["T"])
    _comparer(table, "garcons + filles = total", calc, pub, cles_hors_sexe + ["annee_debut"])


def controle_somme(table, clean, totaux, dim, etiquette_total, autres):
    """Somme de `dim` dans la table propre = total publie (ligne de total sur `dim`)."""
    t = totaux[totaux[dim] == etiquette_total].copy()
    for c in autres:
        if c == "sexe":
            continue
        s = t[c].astype(str)
        t = t[~(s.eq("NATIONAL") | s.str.startswith("TOTAL"))]
    if t.empty:
        return
    calc = clean.groupby(autres + ["annee_debut"], as_index=False)["valeur"].sum()
    pub = t.groupby(autres + ["annee_debut"], as_index=False)["valeur"].sum()
    _comparer(table, f"somme sur {dim} = total publie", calc, pub, autres + ["annee_debut"])


def detecter_anomalies(table, df, cles_serie, genre):
    d = df.sort_values(cles_serie + ["annee_debut"]).copy()
    g = d.groupby(cles_serie)["valeur"]
    d["valeur_precedente"] = g.shift()
    d["variation"] = d["valeur"] - d["valeur_precedente"]
    if genre == "effectif":
        d["variation_pct"] = d["variation"] / d["valeur_precedente"].replace(0, np.nan) * 100
        drap = (d["variation_pct"].abs() > 40) & (d["valeur_precedente"] >= 50)
    elif genre == "taux":
        d["variation_pct"] = np.nan
        drap = d["variation"].abs() > 25
    else:  # ips
        d["variation_pct"] = np.nan
        drap = d["variation"].abs() > 0.25
    a = d[drap].copy()
    if len(a):
        a.insert(0, "table", table)
        ANOMALIES.append(a)
        log("02-nettoyage", table, "Variations annuelles suspectes signalees dans journal_anomalies (non corrigees)", int(len(a)))



# 4. Programme principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entree", required=True)
    ap.add_argument("--sortie", default="sortie")
    ap.add_argument("--equipe", default="E00", help="code equipe (ex. E07)")
    ap.add_argument("--defi", default="D1", help="D1, D2 ou D3")
    a = ap.parse_args()
    xlsx, out = Path(a.entree), Path(a.sortie)
    d01, d02, d03, d04 = (out / x for x in ("01_collecte", "02_nettoyage", "03_transformation", "04_documentation"))
    for d in (d01, d02, d03, d04):
        d.mkdir(parents=True, exist_ok=True)

    def nom(etape, role, desc, ext="csv", v=1):
        return f"{a.equipe}_{etape}_{a.defi}_{role}_{desc}_v{v}.{ext}"

    def ecrire(df, dossier, fichier):
        df.to_csv(dossier / fichier, index=False, encoding="utf-8-sig")

    shutil.copy(xlsx, d01 / nom("01-collecte", "engineer", "donnees-brutes-dgess-prescolaire-primaire", "xlsx"))
    log("01-collecte", "classeur", "Copie du classeur brut (non modifie)", 1)
    scanner_consignes(xlsx)

    TABLES, TOT = {}, {}

    # ---------------- Primaire ----------------
    P = [
        ("Feuil1", "effectifs_primaire_region", ["region", "sexe"], False, None),
        ("Feuil2", "effectifs_primaire_statut", ["statut", "sexe"], False, None),
        ("Feuil3", "effectifs_primaire_milieu", ["milieu", "sexe"], False, None),
        ("Feuil4", "effectifs_primaire_niveau_statut", ["statut", "niveau", "sexe"], False, None),
        ("Feuil5", "nouveaux_inscrits_cp1_region", ["region", "sexe"], False, None),
        ("Feuil13", "ecoles_primaire_region_statut", ["region", "statut"], False, None),
    ]
    for feuille, table, cles, tr, extra in P:
        TABLES[table], TOT[table] = feuille_longue(xlsx, feuille, table, cles, tr, extra=extra)
        log("02-nettoyage", table, f"Feuille {feuille} mise en format long", len(TABLES[table]))

    ind = []
    for feuille, code in [("Feuil6", "TBA"), ("Feuil7", "TBS"), ("Feuil8", "ACHEVEMENT")]:
        c, t = feuille_longue(xlsx, feuille, f"indicateurs_{code}", ["region"], triples=True, extra={"indicateur": code})
        ind.append(c); TOT[f"indicateurs_{code}"] = t
    c, t = feuille_longue(xlsx, "Feuil9", "indicateurs_CEP", ["region", "sexe"], extra={"indicateur": "CEP"})
    ind.append(c); TOT["indicateurs_CEP"] = t
    TABLES["indicateurs_primaire_region"] = pd.concat(ind, ignore_index=True)
    log("02-nettoyage", "indicateurs_primaire_region",
        "TBA, TBS, taux d'achevement et reussite au CEP regroupes (colonne 'indicateur', valeurs en %)",
        len(TABLES["indicateurs_primaire_region"]))
    log("02-nettoyage", "indicateurs_primaire_region",
        "CEP : annee unique (ex. 2016) interpretee comme fin d'annee scolaire -> annee_debut = annee - 1", "")

    ips = []
    for feuille, code in [("Feuil10", "IPS_TBA"), ("Feuil11", "IPS_TBS"), ("Feuil12", "IPS_TAP")]:
        c, t = feuille_longue(xlsx, feuille, code, ["region"], extra={"indicateur": code})
        ips.append(c); TOT[code] = t
    TABLES["ips_primaire_region"] = pd.concat(ips, ignore_index=True)
    log("02-nettoyage", "ips_primaire_region", "IPS (indice de parite filles/garcons) du TBA, TBS et TAP regroupes",
        len(TABLES["ips_primaire_region"]))

    # ---------------- Prescolaire (7-8 tableaux empiles dans une feuille) ----------------
    dfp = lire_feuille(xlsx, "PRESCOLAIRE")
    titres = [i for i in range(len(dfp)) if isinstance(dfp.iat[i, 0], str) and dfp.iat[i, 0].strip().startswith("Tableau")]
    bornes = {int(re.search(r"Tableau\s*(\d+)", dfp.iat[i, 0]).group(1)): (i, (titres[k + 1] if k + 1 < len(titres) else len(dfp)))
              for k, i in enumerate(titres)}
    S = [(1, "prescolaire_effectifs_region", ["region"], True), (2, "prescolaire_effectifs_statut", ["statut"], True),
         (3, "prescolaire_effectifs_milieu", ["milieu"], True),
         (4, "prescolaire_effectifs_niveau_statut", ["statut", "niveau"], True),
         (5, "prescolaire_tbs_region", ["region"], True), (6, "prescolaire_ips_tbs_region", ["region"], False),
         (7, "prescolaire_structures_region_statut", ["region", "statut"], False),
         (8, "prescolaire_salles_classe_region_statut", ["region", "statut"], False)]
    for num, table, cles, tr in S:
        debut, fin = bornes[num]
        TABLES[table], TOT[table] = bloc_prescolaire(dfp, debut, fin, table, cles, tr)
        log("02-nettoyage", table, f"Tableau {num} de la feuille PRESCOLAIRE extrait et mis en format long", len(TABLES[table]))
    log("02-nettoyage", "prescolaire_effectifs_milieu", "Donnees disponibles seulement a partir de 2018-2019 dans la source", "")

    # ---------------- Controles ----------------
    for t in ["effectifs_primaire_region", "effectifs_primaire_statut", "effectifs_primaire_milieu",
              "effectifs_primaire_niveau_statut", "nouveaux_inscrits_cp1_region", "prescolaire_effectifs_region",
              "prescolaire_effectifs_statut", "prescolaire_effectifs_milieu", "prescolaire_effectifs_niveau_statut"]:
        cs = [c for c in TABLES[t].columns if c not in ("sexe", "annee_scolaire", "annee_debut", "valeur")]
        controle_gft(t, TABLES[t], cs)
    for t, dim, lab, autres in [
        ("effectifs_primaire_region", "region", "NATIONAL", ["sexe"]),
        ("nouveaux_inscrits_cp1_region", "region", "NATIONAL", ["sexe"]),
        ("effectifs_primaire_statut", "statut", "TOTAL", ["sexe"]),
        ("effectifs_primaire_milieu", "milieu", "TOTAL", ["sexe"]),
        ("effectifs_primaire_niveau_statut", "niveau", "TOTAL", ["statut", "sexe"]),
        ("effectifs_primaire_niveau_statut", "statut", "TOTAL", ["niveau", "sexe"]),
        ("ecoles_primaire_region_statut", "statut", "TOTAL", ["region"]),
        ("ecoles_primaire_region_statut", "region", "NATIONAL", ["statut"]),
        ("prescolaire_effectifs_region", "region", "NATIONAL", ["sexe"]),
        ("prescolaire_effectifs_statut", "statut", "TOTAL", ["sexe"]),
        ("prescolaire_effectifs_milieu", "milieu", "TOTAL", ["sexe"]),
        ("prescolaire_effectifs_niveau_statut", "niveau", "TOTAL", ["statut", "sexe"]),
        ("prescolaire_structures_region_statut", "statut", "TOTAL", ["region"]),
        ("prescolaire_structures_region_statut", "region", "NATIONAL", ["statut"]),
        ("prescolaire_salles_classe_region_statut", "statut", "TOTAL", ["region"]),
        ("prescolaire_salles_classe_region_statut", "region", "NATIONAL", ["statut"]),
    ]:
        controle_somme(t, TABLES[t], TOT[t], dim, lab, autres)

    # total national primaire par niveau et statut : somme sur statut ET niveau = total publie
    tn = TOT["effectifs_primaire_niveau_statut"]
    pub = tn[(tn["statut"] == "TOTAL") & (tn["niveau"] == "TOTAL")].groupby(["sexe", "annee_debut"], as_index=False)["valeur"].sum()
    calc = TABLES["effectifs_primaire_niveau_statut"].groupby(["sexe", "annee_debut"], as_index=False)["valeur"].sum()
    _comparer("effectifs_primaire_niveau_statut", "somme sur statut et niveau = total national publie", calc, pub, ["sexe", "annee_debut"])

    # ---------------- Anomalies ----------------
    for t, genre in [("effectifs_primaire_region", "effectif"), ("nouveaux_inscrits_cp1_region", "effectif"),
                     ("ecoles_primaire_region_statut", "effectif"), ("prescolaire_effectifs_region", "effectif"),
                     ("prescolaire_structures_region_statut", "effectif"),
                     ("prescolaire_salles_classe_region_statut", "effectif")]:
        cs = [c for c in TABLES[t].columns if c in ("region", "statut", "sexe")]
        detecter_anomalies(t, TABLES[t], cs, genre)
    detecter_anomalies("indicateurs_primaire_region", TABLES["indicateurs_primaire_region"], ["region", "indicateur", "sexe"], "taux")
    detecter_anomalies("ips_primaire_region", TABLES["ips_primaire_region"], ["region", "indicateur"], "ips")

    # ---------------- Ecriture des tables propres (etape 02) ----------------
    for t, df in TABLES.items():
        ecrire(df, d02, nom("02-nettoyage", "engineer", t.replace("_", "-")))
    # ---------------- Transformation (etape 03) ----------------
    eff = TABLES["effectifs_primaire_region"].pivot_table(index=["region", "annee_debut"], columns="sexe", values="valeur").reset_index()
    eff = eff.rename(columns={"G": "eff_g", "F": "eff_f", "T": "eff_t"})
    nv = TABLES["nouveaux_inscrits_cp1_region"].pivot_table(index=["region", "annee_debut"], columns="sexe", values="valeur").reset_index()
    nv = nv.rename(columns={"G": "cp1_g", "F": "cp1_f", "T": "cp1_t"})
    ii = TABLES["indicateurs_primaire_region"].copy()
    ii["col"] = ii["indicateur"].str.lower().str.replace("achevement", "ach") + "_" + ii["sexe"].str.lower()
    ii = ii.pivot_table(index=["region", "annee_debut"], columns="col", values="valeur").reset_index()
    ip = TABLES["ips_primaire_region"].pivot_table(index=["region", "annee_debut"], columns="indicateur", values="valeur").reset_index()
    ip = ip.rename(columns={"IPS_TBA": "ips_tba", "IPS_TBS": "ips_tbs", "IPS_TAP": "ips_tap"})
    ec = TABLES["ecoles_primaire_region_statut"].pivot_table(index=["region", "annee_debut"], columns="statut", values="valeur").reset_index()
    ec = ec.rename(columns={"Public": "ecoles_public", "Prive": "ecoles_prive"})
    ec["ecoles_total"] = ec["ecoles_public"] + ec["ecoles_prive"]

    panel = eff
    for x in (nv, ii, ip, ec):
        panel = panel.merge(x, on=["region", "annee_debut"], how="left")
    panel["annee_scolaire"] = panel["annee_debut"].astype(str) + "-" + (panel["annee_debut"] + 1).astype(str)
    panel = panel.sort_values(["region", "annee_debut"]).reset_index(drop=True)
    g = panel.groupby("region")
    panel["part_filles_pct"] = panel["eff_f"] / panel["eff_t"] * 100
    panel["variation_eff_t_pct"] = g["eff_t"].pct_change() * 100
    panel["eleves_par_ecole"] = panel["eff_t"] / panel["ecoles_total"]
    panel["part_prive_ecoles_pct"] = panel["ecoles_prive"] / panel["ecoles_total"] * 100
    panel["taux_non_achevement_t"] = 100 - panel["ach_t"]
    panel["ecart_ach_f_moins_g"] = panel["ach_f"] - panel["ach_g"]
    panel["ecart_cep_f_moins_g"] = panel["cep_f"] - panel["cep_g"]
    panel["ecart_tbs_moins_tba_t"] = panel["tbs_t"] - panel["tba_t"]
    panel["flag_rupture_2022_2023"] = (panel["annee_debut"] == 2022).astype(int)
    cols = ["region", "annee_scolaire", "annee_debut"] + [c for c in panel.columns if c not in ("region", "annee_scolaire", "annee_debut")]
    panel = panel[cols]
    ecrire(panel, d03, nom("03-transformation", "engineer", "panel-region-annee-primaire"))
    log("03-transformation", "panel_region_annee_primaire",
        "Table d'analyse 13 regions x 10 annees avec indicateurs derives (non-achevement, ecarts F-G, eleves par ecole...)", len(panel))

    # flux de cohorte national CP1 -> CM2 (apparent : ne tient pas compte des redoublements ni des transferts)
    n = TABLES["effectifs_primaire_niveau_statut"]
    nat = n.groupby(["niveau", "sexe", "annee_debut"], as_index=False)["valeur"].sum()
    flux = []
    for deb in range(2015, 2020):
        cp1 = nat[(nat.niveau == "CP1") & (nat.annee_debut == deb)].set_index("sexe")["valeur"]
        cm2 = nat[(nat.niveau == "CM2") & (nat.annee_debut == deb + 5)].set_index("sexe")["valeur"]
        for s in ("G", "F", "T"):
            if s in cp1 and s in cm2:
                flux.append({"cohorte_entree_cp1": f"{deb}-{deb + 1}", "annee_cm2": f"{deb + 5}-{deb + 6}", "sexe": s,
                             "effectif_cp1": cp1[s], "effectif_cm2_5ans_apres": cm2[s],
                             "taux_survie_apparent_pct": round(cm2[s] / cp1[s] * 100, 2)})
    flux = pd.DataFrame(flux)
    ecrire(flux, d03, nom("03-transformation", "engineer", "flux-cohorte-national-cp1-cm2"))
    log("03-transformation", "flux_cohorte_national", "Taux de survie apparent CP1 -> CM2 (national, public+prive) ; "
        "approximation (redoublements, transferts et migrations non pris en compte)", len(flux))

    # ---------------- Documentation (etape 04) ----------------
    controles = pd.DataFrame(CONTROLES)
    ecarts = pd.concat(ECARTS, ignore_index=True) if ECARTS else pd.DataFrame(columns=["table", "test"])
    anomalies = pd.concat(ANOMALIES, ignore_index=True) if ANOMALIES else pd.DataFrame()
    journal = pd.DataFrame(JOURNAL)
    ecrire(journal, d04, nom("02-nettoyage", "engineer", "journal-de-nettoyage"))
    ecrire(controles, d04, nom("02-nettoyage", "engineer", "controles-totaux-resume"))
    ecrire(ecarts, d04, nom("02-nettoyage", "engineer", "controles-totaux-ecarts"))
    ecrire(anomalies, d04, nom("02-nettoyage", "engineer", "journal-anomalies"))
    dico = dictionnaire()
    ecrire(dico, d04, nom("02-nettoyage", "architect", "dictionnaire-variables"))

    # classeur de relecture (toutes les tables dans un seul fichier)
    with pd.ExcelWriter(out / nom("02-nettoyage", "engineer", "classeur-relecture", "xlsx"), engine="openpyxl") as w:
        panel.to_excel(w, sheet_name="panel_region_annee", index=False)
        flux.to_excel(w, sheet_name="flux_cohorte_national", index=False)
        for t, df in TABLES.items():
            df.to_excel(w, sheet_name=t[:31], index=False)
        controles.to_excel(w, sheet_name="controles_resume", index=False)
        ecarts.to_excel(w, sheet_name="controles_ecarts", index=False)
        anomalies.to_excel(w, sheet_name="anomalies", index=False)
        journal.to_excel(w, sheet_name="journal_nettoyage", index=False)
        dico.to_excel(w, sheet_name="dictionnaire", index=False)
    (d04 / "LISEZ-MOI.txt").write_text(lisez_moi(a), encoding="utf-8")
    print(f"Termine. Fichiers ecrits dans : {out.resolve()}")
    print(controles.to_string(index=False))


def dictionnaire():
    L = [
        ("toutes les tables longues", "region", "Region (13 anciennes regions, noms harmonises : HAUTS-BASSINS, etc.)", "texte"),
        ("toutes les tables longues", "sexe", "G = garcons, F = filles, T = total", "texte"),
        ("toutes les tables longues", "statut", "Public, Prive, Communautaire (prescolaire)", "texte"),
        ("toutes les tables longues", "milieu", "Urbain, Rural, Indetermine (prescolaire)", "texte"),
        ("toutes les tables longues", "niveau", "CP1..CM2 (primaire) ; sections du prescolaire", "texte"),
        ("toutes les tables longues", "annee_scolaire", "Annee scolaire, ex. 2015-2016", "texte"),
        ("toutes les tables longues", "annee_debut", "Annee de debut de l'annee scolaire (2015 = 2015-2016)", "entier"),
        ("toutes les tables longues", "valeur", "Valeur de l'indicateur (effectif, nombre, % ou indice selon la table)", "nombre"),
        ("indicateurs_primaire_region", "indicateur", "TBA, TBS, ACHEVEMENT, CEP (valeurs en %)", "texte"),
        ("ips_primaire_region", "indicateur", "IPS_TBA, IPS_TBS, IPS_TAP (indice de parite filles/garcons ; 1 = parite)", "texte"),
        ("panel_region_annee_primaire", "eff_g / eff_f / eff_t", "Effectifs du primaire : garcons, filles, total", "eleves"),
        ("panel_region_annee_primaire", "cp1_g / cp1_f / cp1_t", "Nouveaux inscrits au CP1", "eleves"),
        ("panel_region_annee_primaire", "tba_*", "Taux brut d'admission (g, f, t)", "%"),
        ("panel_region_annee_primaire", "tbs_*", "Taux brut de scolarisation (g, f, t)", "%"),
        ("panel_region_annee_primaire", "ach_*", "Taux d'achevement du primaire (g, f, t)", "%"),
        ("panel_region_annee_primaire", "cep_*", "Taux de reussite au CEP (g, f, t) ; annee = fin d'annee scolaire", "%"),
        ("panel_region_annee_primaire", "ips_tba / ips_tbs / ips_tap", "Indice de parite filles/garcons", "ratio"),
        ("panel_region_annee_primaire", "ecoles_public / ecoles_prive / ecoles_total", "Nombre d'ecoles primaires", "ecoles"),
        ("panel_region_annee_primaire", "part_filles_pct", "eff_f / eff_t x 100", "%"),
        ("panel_region_annee_primaire", "variation_eff_t_pct", "Variation annuelle des effectifs totaux", "%"),
        ("panel_region_annee_primaire", "eleves_par_ecole", "eff_t / ecoles_total (proxy de la pression sur les ecoles)", "eleves/ecole"),
        ("panel_region_annee_primaire", "taux_non_achevement_t", "100 - taux d'achevement (proxy de decrochage, a justifier)", "%"),
        ("panel_region_annee_primaire", "ecart_ach_f_moins_g", "Achevement filles moins achevement garcons", "points"),
        ("panel_region_annee_primaire", "ecart_cep_f_moins_g", "Reussite CEP filles moins garcons", "points"),
        ("panel_region_annee_primaire", "ecart_tbs_moins_tba_t", "TBS - TBA (total)", "points"),
        ("panel_region_annee_primaire", "flag_rupture_2022_2023", "1 pour 2022-2023 (rupture visible dans les effectifs de plusieurs regions)", "0/1"),
        ("flux_cohorte_national_cp1_cm2", "taux_survie_apparent_pct", "Effectif CM2 5 ans apres / effectif CP1 (national) - approximation", "%"),
    ]
    return pd.DataFrame(L, columns=["table", "variable", "description", "unite"])


def lisez_moi(a):
    return f"""LISEZ-MOI - Donnees nettoyees (equipe {a.equipe}, defi {a.defi})
Source : DGESS, Ministere de l'Education nationale - Donnees statistiques prescolaire et primaire 2016-2025
(fichier fourni par le Data Challenge Burkina, edition Education 2026). Donnees utilisees uniquement pour le concours.

01_collecte/        classeur brut, non modifie
02_nettoyage/       tables propres au format long (une ligne = region/statut/niveau x sexe x annee)
03_transformation/  panel region x annee (13 regions x 10 annees) + flux de cohorte national
04_documentation/   journal de nettoyage, controles de totaux, anomalies, dictionnaire des variables

Points d'attention
- annee_debut 2015 = annee scolaire 2015-2016. Le CEP est indexe par annee civile : 2016 -> 2015-2016.
- Seulement les 13 anciennes regions (pas de provinces, pas des 17 nouvelles regions).
- Rupture 2022-2023 dans plusieurs regions (effectifs en forte baisse) : a modeliser, pas a lisser.
- Le taux d'abandon n'existe pas dans la source : 'taux_non_achevement_t' et le flux de cohorte en sont des proxies.
- Les anomalies listees dans journal_anomalies n'ont PAS ete corrigees : a verifier aupres des publications d'origine.
"""


if __name__ == "__main__":
    main()
