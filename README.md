# EduPredict : cartographie et anticipation du risque de décrochage scolaire par région

Solution de l'équipe EduPredict pour le **Data Challenge Burkina, édition Éducation 2026** (Défi 1 : cartographie et anticipation du risque de décrochage scolaire par région).

**Question :** dans quelles régions les enfants ont-ils le moins de chances de terminer le primaire, comment cette situation évolue-t-elle, et quelles régions risquent de passer sous le seuil critique l'an prochain ?

## Ce que fait la solution

1. **Définit le risque** : une région est à risque élevé quand son taux d'achèvement du primaire est inférieur à 50 %. Deux signaux complémentaires repèrent les régions à surveiller (baisse d'au moins 10 points en 3 ans ; forte exposition aux déplacés internes).
2. **Calcule un indice de risque** de 0 à 100 par région (60 % état, 20 % tendance, 20 % exposition), avec paliers et test de robustesse sur 5 pondérations.
3. **Évalue des modèles de prévision** (régression logistique, arbre, Random Forest, Gradient Boosting) par validation chronologique. Leur fiabilité est limitée : ils ne font pas mieux qu'une règle simple (voir la documentation).
4. **Produit une carte, 13 fiches régionales d'une page (PDF) et un tableau de bord interactif** avec recommandations.

Résultats 2024-2025 : 7 régions sur 13 sont sous 50 % d'achèvement ; les plus à risque sont le Centre-Nord, l'Est et le Sahel.

> Limite principale : le taux d'achèvement est utilisé comme indicateur du décrochage, ce n'est pas un taux d'abandon.

## Contenu du dépôt

| Élément | Contenu |
|---|---|
| `scripts/` | Les 10 scripts Python et le modèle de page du tableau de bord |
| `lancer_pipeline.py` | Relance tout le travail en une commande |
| `docs/index.html` | Tableau de bord interactif (page autonome, publiable avec GitHub Pages) |
| `documentation/` | Documentation du projet (PDF, 9 pages) |
| `resultats/` | Carte, 13 fiches régionales, classement, prévision, indice par année |
| `requirements.txt` | Dépendances Python |

## Relancer le travail

```bash
pip install -r requirements.txt
python lancer_pipeline.py --data data --sortie sortie
```

Le dossier `data/` n'est **pas** dans ce dépôt (les données du challenge ne servent qu'au concours). Il faut le recréer avec les fichiers du challenge :

```
data/DONNEES_STATISTQUES__PRESCOLAIRE_ET_PRIMAIRE_2016_2025_DCB.xlsx   fichier principal DGESS (un seul .xlsx à la racine)
data/PDI_CONASUR/                      versions CSV : 03_Conditions_de_Vie_et_Emploi/PDI_CONASUR
data/Annuaires/                        versions CSV : 01_Education_MENAPLN_DGESS/CNS_DGESS/Annuaires
data/Tableaux_de_bord/                 versions CSV : 01_Education_MENAPLN_DGESS/CNS_DGESS/Tableaux_de_bord
data/COD-AB_limites_administratives/   04_Cartographie_SIG/COD-AB_limites_administratives (bfa_admin_boundaries.xlsx et .geojson.zip)
```

Les « versions CSV » sont celles fournies dans le dossier `data/` du Data Pack (même arborescence que les PDF et Excel d'origine). 

## Les 10 étapes

| # | Script | Produit |
|---|---|---|
| 1 | `nettoyage_education_burkina.py` | Tables propres au format long, tableau région × année, journal, contrôles de totaux, anomalies, dictionnaire |
| 2 | `extraction_pdi_conasur.py` | Déplacés internes par région et par année |
| 3 | `definition_risque_decrochage.py` | Drapeaux et niveau de risque par région et année |
| 4 | `indice_risque_decrochage.py` | Indice, rang, paliers, robustesse |
| 5 | `modele_prevision_risque.py` | Modèles, validation chronologique, prévision 2025-2026 |
| 6 | `extraction_abandons_annuaires.py` | Taux d'abandon par région (annuaires DGESS) |
| 7 | `extraction_causes_abandons.py` | Abandons liés à l'orpaillage, aux mariages et aux grossesses |
| 8 | `construire_fond_de_carte.py` | 351 communes COD-AB regroupées en 13 régions |
| 9 | `carte_et_fiches.py` | Carte, 13 fiches régionales PDF, données du tableau de bord |
| 10 | `construire_tableau_de_bord.py` | Tableau de bord HTML autonome |

## Tableau de bord en ligne

Le fichier `docs/index.html` est autonome. 

## Sources

- DGESS, Ministère de l'Éducation nationale : données statistiques préscolaire et primaire 2016-2025 ; annuaires statistiques de l'enseignement primaire 2017-2018 à 2024-2025 ; tableaux de bord du primaire.
- CONASUR : situations des personnes déplacées internes, 2019-2022.
- COD-AB : limites administratives du Burkina Faso, version v03, valide au 1er août 2025.
- Tous via le Data Pack du Data Challenge Burkina 2026. Données utilisées uniquement pour le concours.

## Usage d'un outil d'intelligence artificielle
### Démarche documentaire et contribution personnelle

Afin de mieux comprendre les objectifs du projet et d'identifier les approches méthodologiques adaptées à la problématique du décrochage scolaire, j'ai sollicité l'accompagnement de ChatGPT pour explorer différentes méthodes, notamment le Machine Learning et le Deep Learning.

J'ai ensuite effectué une recherche documentaire pour vérifier et approfondir les propositions méthodologiques à travers des publications scientifiques et des rapports institutionnels.

Concernant la réalisation technique, j'ai personnellement pris en charge l'ensemble du développement : préparation et traitement des données, implémentation des modèles en Python, conception de l'interface web en HTML et présentation des résultats. ChatGPT m'a uniquement accompagné dans la compréhension initiale du sujet et l'exploration des approches possibles. La réalisation technique a été effectuée par mes soins.

**Références consultées :**

1. *Predicting Student Dropout based on Machine Learning and Deep Learning: A Systematic Review* (2023) : https://eudl.eu/pdf/10.4108/eetsis.3586
2. Salinas-Chipana et al., *Machine Learning Models for Predicting Student Dropout, a Review* : https://research.upn.edu.pe/en/publications/machine-learning-models-for-predicting-student-dropouta-review/
3. UNICEF (2023), situation scolaire au Burkina Faso : https://www.unicef.org/press-releases/burkina-faso-new-academic-year-starts-one-million-children-out-school-due-ongoing
4. UNICEF (2019), fermetures d'écoles au Sahel : https://www.unicef.org/wca/press-releases/school-closures-sahel-double-last-two-years-due-growing-insecurity-unicef
5. WATHI (2025), *Education in situations of insecurity in West Africa* : https://wathi.org/wp-content/uploads/2025/04/Education-in-situations-of-insecurity-in-West-Africa.pdf
