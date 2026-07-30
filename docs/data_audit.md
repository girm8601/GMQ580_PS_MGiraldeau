# Audit des données

Document d'audit par source, tenu à jour au fil du projet. L'audit fait partie de la
démarche scientifique. Un pipeline qui tourne sans erreur ne garantit pas un résultat
valide, « garbage in, garbage out », d'autant plus vrai en géomatique.

## Règles de validation vérifiées

Le module `src/validation/audit.py` rassemble les règles et s'exécute **avant** tout traitement.
Il bloque le pipeline si une donnée est invalide et journalise le résultat dans `outputs/tables/audit_report.csv`.
Toute correction automatique est ainsi retracée, c'est le principe du journal.

Chaque puce nomme la règle du code, la fonction qui l'applique et ce qu'elle attrape.

- **CRS déclaré**, `check_crs`. Le CRS est présent et conforme au CRS cible. Ne jamais supposer qu'un CRS est défini.
- **Emprise réelle**, `check_bounds` sur `gdf.total_bounds`. L'emprise recoupe celle de la zone d'étude. Attrape les coordonnées inversées et les valeurs aberrantes, qu'un CRS correctement déclaré ne suffit pas à écarter.
- **Géométries valides**, `check_valid_geometries`. Correction courante `buffer(0)`, appliquée par `fix_invalid_geometries` et journalisée.
- **Géométries vides**, `check_empty_geometries`.
- **Doublons**, `check_duplicates` sur l'ensemble des colonnes.
- **Couverture de la zone**, `check_zone_overlap` sur `intersects`. Il reste des entités qui touchent la zone d'étude.
- **Attributs nécessaires présents**, `check_required_fields`. `IDUGD` pour les aires de diffusion, `MUS_NM_MUN` pour les limites municipales, `nom_gare` et `nom_train` pour exo, `service_type` pour les services essentiels, un champ dérivé du typage.
- **Cohérence entre sources**. Même CRS après reprojection vers EPSG:2950 avant toute jointure spatiale, garanti par `src/io.py` et couvert par un test.

Deux vérifications se font ailleurs, hors du module d'audit, car elles portent sur un
graphe et non sur une couche. `bridges.py` recoupe les liens qui traversent la rivière par
les rives et par le plan d'eau, et journalise un avertissement si les deux comptes
diffèrent. `demand.py` journalise le taux de jointure du profil du recensement et le
nombre de résidences écartées faute d'aire de diffusion.

CRS cible commun du projet, **EPSG:2950**, soit NAD83(CSRS) / MTM zone 8.

## Fiche d'audit par source

| Source | Date | Format | Qualité observée | Impact potentiel | Correction |
|--------|------|--------|------------------|------------------|------------|
| Réseau piétonnier, OpenStreetMap (OSMnx) | Extrait juillet 2026 | Graphe GraphML, source EPSG:4326 | Complétude variable en milieu périurbain, franchissabilité des ponts par les trottoirs | Chemins manquants → distances de marche faussées, ponts non franchissables → effet de barrière mal estimé | Reprojeter vers EPSG:2950, valider les ponts avec `bridges.py`, croiser avec l'imagerie aérienne, les orthophotos |
| Services essentiels, OpenStreetMap | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Étiquetage `amenity` et `shop` parfois incomplet ou hétérogène, certains établissements portent seulement `healthcare` ou `amenity=childcare` | Services manquants → couverture sous-estimée | Reprojeter vers EPSG:2950, élargir les étiquettes de la config (`healthcare`, `childcare`), croiser avec l'imagerie aérienne, les orthophotos, compléter OSM par contribution directe, documenter les manques |
| Bâtiments résidentiels, OpenStreetMap | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Couverture à vérifier, typage hétérogène, `house`, `detached`, `residential` ou `yes`, et `yes` reste ambigu car il désigne tout type de bâtiment | Origines de la demande incomplètes, bâtiments non résidentiels comptés si `yes` pris tel quel | Reprojeter vers EPSG:2950, filtrer par `kept_types` de la configuration, croiser `yes` avec les polygones OpenStreetMap `landuse=residential`, compléter avec `addr:housenumber`, journaliser les types écartés (audit), vérifier `is_valid` et emprise |
| Nœuds d'adresse, OpenStreetMap | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Nœuds portant `addr:housenumber`, complément des bâtiments non cartographiés, certains portent aussi `building` (déjà comptés) | Doublons de résidences → demande gonflée | Reprojeter vers EPSG:2950, écarter les nœuds portant une étiquette `building`, dédoublonner par géométrie, construire l'étiquette d'adresse avec le numéro et la rue |
| Terrains résidentiels, OpenStreetMap, `landuse=residential` | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Polygones d'usage résidentiel, servent à trancher le sort des bâtiments `yes` | Bâtiments `yes` non résidentiels comptés si le croisement manque | Reprojeter vers EPSG:2950, ne garder que les polygones, découper à la zone, croiser avec les bâtiments `yes`, repli journalisé sur le comportement de GMQ210 si la couche est absente |
| Terrains commerciaux, OpenStreetMap, `landuse` commercial et retail | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Polygones parfois absents ou généralisés, sites candidats de services, un choix plus simple car locaux et sites parfois déjà disponibles | Validation d'ajout sautée si la couche est absente, sites erronés si trop loin du réseau | Reprojeter vers EPSG:2950, ne garder que les polygones, découper à la zone, filtrer par proximité au réseau piétonnier, avertissement journalisé si la couche est absente |
| Terrains à développer, OpenStreetMap, `landuse` brownfield, greenfield et construction | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Friches, terrains vierges et chantiers, sites candidats de logement aîné, parfois absents d'un secteur | Siting du logement sauté si aucun terrain, sites erronés si trop loin du réseau | Reprojeter vers EPSG:2950, ne garder que les polygones, découper à la zone, filtrer par proximité au réseau piétonnier, avertissement journalisé si la couche est absente |
| Plans d'eau, OpenStreetMap, `natural=water` | Extrait juillet 2026 | Vectoriel GeoPackage, source EPSG:4326 | Contexte cartographique seulement (rivière Richelieu), n'entre dans aucun calcul | Aucun impact sur les résultats, carte moins lisible si absent | Reprojeter vers EPSG:2950, ne garder que les polygones, découper à la zone, avertissement journalisé et carte sans rivière si la couche est absente |
| Population et aînés par AD, StatCan, Recensement 2021 | Téléchargé juin 2026, données de 2021 | CSV tabulaire sans géométrie, **encodage latin-1**, les colonnes sont accentuées comme `ID_CARACTÉRISTIQUE` | Population totale à la caractéristique ID 1, 65 ans et plus à l'ID 24, valeur dans `C1_CHIFFRE_TOTAL`, valeurs parfois arrondies pour la confidentialité | Mauvais ID → mauvaise variable, jointure ratée → demande nulle, lecture en UTF-8 → noms de colonnes corrompus | Lire avec l'encodage latin-1 paramètre `csv_encoding` de la configuration, joindre par `IDUGD` (texte, zéros de tête conservés), contrôler le taux de jointure |
| Limites des aires de diffusion, StatCan 2021 | Téléchargé juin 2026 | Shapefile, **source EPSG:3347**, le Lambert de StatCan | Fichier national de 57 932 AD, champ `ADIDU` le code à 8 chiffres et champ `IDUGD` la clé de jointure | Jointure spatiale fausse si non reprojeté, volume inutile | Reprojeter vers EPSG:2950, découper à la zone d'étude avec `clip`, joindre au profil par `IDUGD` |
| Limites municipales, Données Québec | Téléchargé juin 2026 | Shapefile, **source EPSG:4269**, géographique et non projeté | Utiliser la couche de polygones `munic_s` et son champ `MUS_NM_MUN`, la couche de lignes `munic_l` n'a pas de nom de municipalité | Mesures de distance impossibles avant projection, sélection impossible avec `munic_l`, risque de fausse capture avec une recherche partielle, « Saint-Mathieu-de-Beloeil » existe aussi | Reprojeter vers EPSG:2950 avant toute mesure, sélectionner les 4 municipalités par correspondance **exacte** de `MUS_NM_MUN` |
| Arrêts d'autobus, exo, GTFS de l'agence CITVR, soit exo-Vallée du Richelieu | Flux valide du 21 avril au 23 août 2026 | GTFS, coordonnées EPSG:4326 | 434 arrêts au total, 387 arrêts des lignes fixes, dont 193 dans la zone, 10 lignes fixes (`route_type` 3) et 4 lignes à la demande (T23, T24, T26, T30, `route_type` 1501), espaces de tête dans `stop_lat`/`stop_lon` | Parsing erroné si espaces non retirés, confusion réseau fixe / à la demande | Nettoyer et convertir en points, reprojeter EPSG:2950, écarter les `route_type` 1501 (à la demande incomplet) |
| Gares de train, exo | Export 2026-04-02 | GeoJSON de 53 points, EPSG:4326 | Réseau exo complet, deux gares dans la zone, une par rive, Gare McMasterville à l'ouest et Gare Mont-Saint-Hilaire à l'est, `adresse_civique` parfois nulle | Bruit hors zone si non filtré | Reprojeter EPSG:2950, retenir les gares de la ligne Mont-Saint-Hilaire |
| Lignes de train, exo | Export 2026-04-02 | GeoJSON de 6 lignes, EPSG:4326 | Doublon confirmé, la « Ligne Vaudreuil/Hudson » est présente deux fois, géométries MultiLineString | Double comptage possible | Reprojeter EPSG:2950, retirer le doublon avec `duplicated()`, conserver « Ligne Mont-Saint-Hilaire » |

## Notes

- Toute correction automatique appliquée par le pipeline est journalisée dans
  `outputs/tables/audit_report.csv`.
