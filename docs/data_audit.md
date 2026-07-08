# Audit des données

Document d'audit par source, tenu à jour au fil du projet. L'audit fait partie de la
démarche scientifique : un pipeline qui tourne sans erreur ne garantit pas un résultat
valide (« garbage in, garbage out », d'autant plus vrai en géomatique).

## Règles de validation vérifiées

Le module `src/validation/audit.py` rassemble les règles et s'exécute **avant** tout
traitement. Il bloque le pipeline si une donnée est invalide et journalise le résultat
dans `outputs/tables/audit_report.csv` (principe du LOG : toute correction automatique
est retracée).

- **CRS déclaré** (`gdf.crs`) : présent et attendu, ne jamais supposer qu'un CRS est défini.
- **Emprise réelle** (`gdf.total_bounds`) : cohérente avec la zone d'étude (pas de coordonnées inversées ni aberrantes).
- **Géométries valides** (`gdf.geometry.is_valid.all()`) ; correction courante `buffer(0)`.
- **Géométries vides** (`gdf.geometry.isna().sum()`).
- **Doublons** (`gdf.duplicated().sum()`).
- **Couverture de la zone** (`gdf.clip(zone_etude)`) : il reste des entités après découpage.
- **Attributs nécessaires présents** : `IDUGD` (aires de diffusion), `UTIL_SOL` (utilisation du sol), `MUS_NM_MUN` (limites municipales), `stop_lat`/`stop_lon` (GTFS), `nom_gare`/`nom_train` (exo).
- **Cohérence entre sources** : même CRS après reprojection vers EPSG:2950 avant toute jointure spatiale.

CRS cible commun du projet : **EPSG:2950 (NAD83(CSRS) / MTM zone 8)**.

## Fiche d'audit par source

| Source | Date | Format | Qualité observée | Impact potentiel | Correction |
|--------|------|--------|------------------|------------------|------------|
| Réseau piétonnier - OpenStreetMap (OSMnx) | Extrait juillet 2026 | Graphe (GraphML), source EPSG:4326 | Complétude variable en milieu périurbain ; franchissabilité des ponts à confirmer (trottoirs) | Chemins manquants → distances de marche faussées ; ponts non franchissables → effet de barrière mal estimé | Reprojeter vers EPSG:2950 ; valider les ponts (`bridges.py`) ; croiser avec l'imagerie aérienne (orthophotos) |
| Services essentiels (POI) - OpenStreetMap | Extrait juillet 2026 | Vectoriel (GeoPackage), source EPSG:4326 | Étiquetage `amenity`/`shop` parfois incomplet ou hétérogène | Services manquants → couverture sous-estimée | Reprojeter vers EPSG:2950 ; croiser avec l'imagerie aérienne (orthophotos) ; documenter les manques |
| Bâtiments résidentiels - OpenStreetMap | Extrait juillet 2026 | Vectoriel (GeoPackage), source EPSG:4326 | Couverture des bâtiments à vérifier | Origines de la demande incomplètes | Reprojeter vers EPSG:2950 ; vérifier `is_valid` et emprise |
| Population et aînés par AD - StatCan, Recensement 2021 | Téléchargé juin 2026 (données 2021) | CSV tabulaire (pas de géométrie) | Population totale = caractéristique ID 1 ; 65 ans et plus = ID 24 (valeur dans `C1_CHIFFRE_TOTAL`) ; valeurs arrondies possibles (confidentialité) | Mauvais ID → mauvaise variable ; jointure ratée → demande nulle | Joindre par `IDUGD` (texte, zéros de tête conservés) ; contrôler le taux de jointure |
| Limites des aires de diffusion - StatCan 2021 | Téléchargé juin 2026 | Shapefile, **source EPSG:3347** (Lambert StatCan) | Fichier national : 57 932 AD ; champs `ADIDU` (code à 8 chiffres) et `IDUGD` (clé de jointure) | Jointure spatiale fausse si non reprojeté ; volume inutile | Reprojeter vers EPSG:2950 ; découper à la zone d'étude (`clip`) ; joindre au profil par `IDUGD` |
| Limites municipales - Données Québec | Téléchargé juin 2026 | Shapefile, **source EPSG:4269** (géographique, non projeté) | Utiliser la couche de polygones `munic_s` (champ `MUS_NM_MUN`) ; la couche de lignes `munic_l` n'a pas de nom de municipalité | Mesures de distance impossibles avant projection ; sélection impossible avec `munic_l` | Reprojeter vers EPSG:2950 avant toute mesure ; sélectionner les 4 municipalités par `MUS_NM_MUN` |
| Utilisation du sol - CMM 2022 | Téléchargé juin 2026 (données 2022) | **Vectoriel (Shapefile), source EPSG:32188** (MTM 8) | Fournie segmentée par municipalité : 4 fichiers conservés (Beloeil 1690, Mont-Saint-Hilaire 1582, McMasterville 406, Otterburn Park 605 polygones) ; champ de filtrage `UTIL_SOL`. Simple sélection, aucune modification de géométrie | Datum légèrement différent d'EPSG:2950 ; codes d'usage à interpréter | Reprojeter EPSG:32188 → EPSG:2950 ; fusionner les 4 fichiers ; filtrer `UTIL_SOL` selon le dictionnaire CMM |
| Arrêts d'autobus - exo, GTFS (agence CITVR = exo-Vallée du Richelieu) | Feed valide 2026-04-21 → 2026-08-23 | GTFS (`stops.txt`, etc.), coordonnées EPSG:4326 | 434 arrêts (204 dans la zone) ; 10 lignes fixes (`route_type` 3) et 4 lignes à la demande (T23, T24, T26, T30 ; `route_type` 1501) ; espaces de tête dans `stop_lat`/`stop_lon` | Parsing erroné si espaces non retirés ; confusion réseau fixe / à la demande | Nettoyer et convertir en points ; reprojeter EPSG:2950 ; écarter les `route_type` 1501 (à la demande) |
| Gares de train - exo | Export 2026-04-02 | GeoJSON (points, 53 entités), EPSG:4326 | Réseau exo complet ; deux gares dans la zone, une par rive : Gare McMasterville (rive ouest) et Gare Mont-Saint-Hilaire (rive est) ; `adresse_civique` parfois nulle | Bruit hors zone si non filtré | Reprojeter EPSG:2950 ; retenir les gares de la zone (ligne Mont-Saint-Hilaire) |
| Lignes de train - exo | Export 2026-04-02 | GeoJSON (lignes, 6 entités), EPSG:4326 | Doublon confirmé : « Ligne Vaudreuil/Hudson » présente deux fois ; géométries MultiLineString | Double comptage possible | Reprojeter EPSG:2950 ; retirer le doublon (`duplicated()`) ; conserver « Ligne Mont-Saint-Hilaire » |
| Territoire desservi - exo | Export 2026-04-02 | GeoJSON (polygone, 1 entité), EPSG:4326 | Emprise à vérifier vs zone d'étude | Contexte de desserte mal cadré | Reprojeter EPSG:2950 ; usage indicatif (cadrage) |

## Notes

- Les cases « à vérifier » seront complétées après la première exécution de `audit.py`
  sur les données réelles (emprises, géométries invalides, taux de jointure, doublons).
- Toute correction automatique appliquée par le pipeline est journalisée dans
  `outputs/tables/audit_report.csv`.