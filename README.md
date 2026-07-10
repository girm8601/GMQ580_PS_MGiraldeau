# Équité piétonne face à la barrière fluviale : optimisation des services essentiels à Beloeil et Mont-Saint-Hilaire
**Équipe :** Mylène Giraldeau

![Tests](https://github.com/girm8601/GMQ580_PS_MGiraldeau/actions/workflows/ci.yml/badge.svg)


## Problématique
L'accès aux services essentiels à pied est un enjeu d'autonomie et d'inclusion pour les résidents qui ne disposent pas d'un accès facile à l'automobile. Les personnes âgées (65 ans et plus) en sont le groupe vulnérable candidat principal, plusieurs cessent de conduire tout en demeurant capables de marcher sur de courtes distances.

Le projet porte sur Beloeil (rive ouest) et Mont-Saint-Hilaire (rive est), séparées par la rivière Richelieu, franchissable seulement aux ponts. Cette barrière structure fortement l'accessibilité piétonne entre les deux rives, ce qui en fait un cas pertinent pour étudier l'équité d'accès.

L'accès aux services ne se limite toutefois pas à la marche, le réseau de transport collectif élargit la portée réelle des résidents vers les services situés au-delà d'une distance marchable. Le projet intègre donc le réseau fixe d'exo (emplacements des arrêts d'autobus et des gares de train) comme dimension complémentaire d'accès, sans tenir compte des horaires ni du temps réel.

Le projet évalue si les résidents les plus dépendants de la marche disposent d'un accès équitable aux services essentiels, afin de déterminer la nature et la localisation des nouveaux services à implanter pour maximiser la couverture. Il reprend et étend, avec l'accord de l'enseignant, le projet de session du cours GMQ210.

Les résultats concernent les villes visées et les décideurs publics, communautaires et privés. Le projet se limite à un diagnostic prospectif (l'implantation réelle revient aux décideurs) et n'aborde ni les horaires d'ouverture ni un indice de vulnérabilité multicritère.

La demande est analysée à l'échelle de l'aire de diffusion (Recensement 2021).

## Zone d'étude
Le territoire couvre Beloeil (rive ouest) et Mont-Saint-Hilaire (rive est), séparées par la rivière Richelieu. La demande est analysée à l'échelle de l'aire de diffusion, et les distances à l'échelle du réseau piétonnier.

Une zone tampon incluant les secteurs contigus de McMasterville et d'Otterburn Park sert à extraire le réseau, les services existants et les points d'accès au transport collectif (arrêts et gares), afin d'éviter les effets de bordure.

La demande n'est toutefois mesurée que dans Beloeil et Mont-Saint-Hilaire. Ce choix se justifie par la rivière, franchissable seulement aux ponts, qui contraint fortement l'accessibilité piétonne entre les deux rives.

## Données

| Source | Format | CRS | Accès |
|--------|--------|-----|-------|
| Réseau piétonnier (OpenStreetMap) | Graphe (GraphML) | EPSG:2950 (MTM 8) | Extrait via [OSMnx](https://osmnx.readthedocs.io/en/stable/), reprojeté depuis EPSG:4326 |
| Points d'intérêt, services essentiels (OpenStreetMap) | Vectoriel (GeoPackage) | EPSG:2950 (MTM 8) | Extrait via OSMnx (étiquettes `amenity`, `shop`), reprojeté depuis EPSG:4326 |
| Bâtiments résidentiels (OpenStreetMap) | Vectoriel (GeoPackage) | EPSG:2950 (MTM 8) | Extrait via OSMnx (étiquette `building`), reprojeté depuis EPSG:4326 |
| Population et aînés (65 ans et plus) par aire de diffusion | CSV tabulaire | Aucun (table jointe par code d'AD) | [Statistique Canada, Recensement 2021 (profil)](https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=F) |
| Limites des aires de diffusion | Shapefile | EPSG:2950 (MTM 8), reprojeté depuis EPSG:3347 | [Statistique Canada, limites 2021](https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-fra.cfm?year=21) |
| Limites municipales | Shapefile | EPSG:2950 (MTM 8), reprojeté depuis EPSG:4269 | [Données Québec, découpages administratifs](https://www.donneesquebec.ca/recherche/dataset/decoupages-administratifs/resource/b368d470-71d6-40a2-8457-e4419de2f9c0) |
| Utilisation du sol (contraintes territoriales) | Vectoriel (Shapefile) | EPSG:2950 (MTM 8), reprojeté depuis EPSG:32188 | [CMM, utilisation du sol 2022](https://observatoire.cmm.qc.ca/produits/donnees-georeferencees/#utilisation_du_sol) |
| Arrêts du réseau d'autobus (exo – Vallée du Richelieu) | GTFS (fichiers texte) | EPSG:2950 (MTM 8), reprojeté depuis EPSG:4326 | [exo, données ouvertes (GTFS)](https://exo.quebec/fr/a-propos/donnees-ouvertes) |
| Gares de train (exo) | GeoJSON (points) | EPSG:2950 (MTM 8), reprojeté depuis EPSG:4326 | [Données Québec, gares de train exo](https://www.donneesquebec.ca/recherche/dataset/gares-de-train-exo/resource/8c169002-866c-40e8-babd-2be7186cb17c) |
| Lignes de train (exo) | GeoJSON (lignes) | EPSG:2950 (MTM 8), reprojeté depuis EPSG:4326 | [Données Québec, lignes de train exo](https://www.donneesquebec.ca/recherche/dataset/lignes-de-train-exo/resource/0f7d6393-e43e-48b3-ab8c-a3d48b36cac6) |
| Territoire desservi par exo | GeoJSON (polygone) | EPSG:2950 (MTM 8), reprojeté depuis EPSG:4326 | [Données Québec, limites du territoire exo](https://www.donneesquebec.ca/recherche/dataset/limites-du-territoire-exo) |

Toutes les couches sont ramenées au CRS cible commun EPSG:2950 (NAD83(CSRS) / MTM zone 8) avant analyse. Les données brutes ne sont pas versionnées, elles sont régénérées par `download_data.py` (voir `.gitignore`).

## Modèle de données
Ce projet n'utilise pas de serveur de base de données.

## Pipeline de traitement
**Structure du projet évolutive.** L'arborescence suit le principe « un module, une responsabilité » et reprend les catégories du cours. Elle pourra évoluer en cours de route. Des modules très courts et toujours modifiés ensemble pourront être fusionnés, et de nouveaux pourront être ajoutés si une étape se précise.

Le traitement suit une chaîne séquentielle et reproductible. L'accessibilité est mesurée de deux façons complémentaires : une cote par type de service par lieu résidentiel, qui révèle quel service manque et où, et un indicateur de couverture des résidents vulnérables par aire de diffusion, qui pilote l'optimisation. L'accès marchable est complété par l'accès au réseau de transport collectif fixe (arrêts d'autobus et gares comme points d'accès). L'optimisation par couverture maximale détermine à la fois où ajouter des services et de quels types.
```mermaid
flowchart TD
    A["Données ouvertes<br/>OSM, Recensement 2021 (StatCan), Données Québec, exo, CMM"]

    subgraph P1["1. Acquisition et préparation"]
        B["Acquisition des données"]
        T["Réseau de transport collectif exo<br/>arrêts d'autobus (GTFS), gares et lignes de train"]
        C["Vérification et contrôle qualité"]
        D["Validation de la franchissabilité<br/>des ponts dans le graphe"]
        E["Délimitation de la zone d'étude<br/>Beloeil et Mont-Saint-Hilaire, zone tampon"]
    end

    subgraph P2["2. Analyse d'accessibilité (état actuel, S0)"]
        F["Réseau piétonnier, distances de marche<br/>(Dijkstra)"]
        G["Cote d'accessibilité<br/>par type de service"]
        TA["Accès complémentaire par le réseau fixe<br/>arrêts et gares comme points d'accès"]
        I["Demande pondérée par la vulnérabilité<br/>(aînés par aire de diffusion)"]
        H["Indicateur de couverture<br/>des résidents vulnérables"]
    end

    subgraph P3["3. Optimisation (scénario S1)"]
        J["Définition et filtrage des sites candidats<br/>y compris à proximité des arrêts fixes et des gares"]
        K["Optimisation par couverture maximale<br/>où et quel type, n de 1 à 5"]
        L["Analyse de sensibilité d'équité<br/>pondération vulnérable ou totale"]
    end

    subgraph P4["4. Résultats et diffusion"]
        M["Gains de couverture (S0 et S1)<br/>et effet de barrière de la rivière"]
        N["Visualisation<br/>cartes interactives, courbe de gain"]
        O["Rapport écrit et présentation orale"]
    end

    A -->|"osmnx, pandas"| B
    A -->|"geopandas, pandas"| T
    B --> C
    T --> C
    C -->|"networkx"| D
    D -->|"geopandas"| E
    E -->|"networkx, Dijkstra"| F
    E -->|"pandas, geopandas"| I
    F --> G
    T --> TA
    F --> TA
    G --> H
    TA --> H
    I --> H
    H -->|"geopandas"| J
    T --> J
    J -->|"spopt, PySAL"| K
    K --> L
    K --> M
    L --> M
    M -->|"folium, matplotlib"| N
    N --> O

    style A fill:#EEEDFE,stroke:#534AB7,color:#26215C
    style B fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style T fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style C fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style D fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style E fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style F fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style G fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style TA fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style H fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style I fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style J fill:#E8EEF9,stroke:#3B53A4,color:#1B244F
    style K fill:#E8EEF9,stroke:#3B53A4,color:#1B244F,stroke-width:2px
    style L fill:#E8EEF9,stroke:#3B53A4,color:#1B244F
    style M fill:#FAEEDA,stroke:#854F0B,color:#412402
    style N fill:#FAEEDA,stroke:#854F0B,color:#412402
    style O fill:#FAECE7,stroke:#993C1D,color:#4A1B0C
```

## Librairies principales
- **osmnx** : téléchargement et modélisation du réseau piétonnier et des points d'intérêt d'OpenStreetMap.
- **networkx** : plus courts chemins avec l'algorithme de Dijkstra pour mesurer les distances réelles de marche.
- **geopandas / pandas** : manipulation des données géospatiales et tabulaires, lecture des fichiers GTFS et GeoJSON du réseau de transport, jointures et reprojections (EPSG:2950).
- **spopt (PySAL)** : modèle de localisation-allocation à couverture maximale.
- **folium** : cartes de couverture interactives avant et après optimisation.
- **matplotlib** : graphiques de performance, dont la courbe de rendement de l'ajout de 1 à 5 services.
- **pytest / pytest-cov** : tests unitaires des fonctions critiques (reprojection, géométries, calculs d'accessibilité) et mesure de couverture, exécutés en intégration continue (GitHub Actions).

## Installation et environnement
Les paramètres (CRS cible EPSG:2950, zone d'étude, seuils de marche, types de services, chemins) sont centralisés dans `config.yaml` et chargés par `config_loader.py`, qui valide la configuration avant tout accès aux données. Aucun paramètre n'est codé en dur dans les scripts.

**Avec conda (recommandé)**
```bash
conda env create -f environment.yml
conda activate gmq580_ps_mg
```

**Avec pip**
```bash
python -m venv venv
source venv/bin/activate      # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
```

**Régénérer les données puis exécuter le pipeline**
```bash
python download_data.py       # régénère les données brutes (non versionnées)
python main.py                # exécute le pipeline complet
```

## Tests et intégration continue
Les tests ciblent les fonctions critiques où un bug reste silencieux mais fausse le résultat spatial (reprojection vers EPSG:2950, validité des géométries, cote d'accessibilité, pondération de la demande). Les données de test sont de petits objets synthétiques (`tests/fixtures/`), jamais les données réelles du projet. Les tests de la reprojection et du chargeur de configuration sont implantés, les autres fichiers seront remplis au fur et à mesure que les modules correspondants seront écrits.

**Lancer les tests localement**
```bash
pytest tests/ -v
```

**Couverture de code**
```bash
pytest tests/ --cov=src --cov-report=term-missing
```

Le workflow GitHub Actions (`.github/workflows/ci.yml`) vérifie la qualité du code avec `ruff` puis rejoue `pytest` à chaque `push` et `pull request` sur `main`. Le badge en haut de ce README reflète l'état du dernier passage (vert = tests réussis). Les hooks `pre-commit` (`black`, `ruff`) appliquent les mêmes règles localement avant chaque commit.

| Test | Vérifie | Statut |
|------|---------|--------|
| `test_io.py` | Reprojection correcte vers EPSG:2950. Lecture/écriture GeoPackage sans perte de CRS | ✅ Implanté (reprojection) |
| `test_config_loader.py` | Chargement et validation de `config.yaml` (sections obligatoires, CRS cible) | ✅ Implanté |
| `test_graph.py` | Distances de plus court chemin (Dijkstra) sur un mini-graphe connu | ⏳ À écrire |
| `test_accessibility.py` | Cote d'accessibilité par type de service sur données synthétiques | ⏳ À écrire |
| `test_demand.py` | Pondération de la demande par la vulnérabilité (aînés par AD) | ⏳ À écrire |
| `test_validation.py` | Règles d'audit : CRS attendu, géométries valides et non vides, absence de doublons | ⏳ À écrire |

## Livrables attendus
- Un dépôt GitHub reproductible contenant l'ensemble du pipeline, avec tests unitaires et intégration continue.
- Une carte interactive de la couverture actuelle (S0) des populations vulnérables, marche et réseau de transport fixe.
- Une carte interactive des scénarios optimisés (S1) avec la localisation et le type des services recommandés.
- Une courbe de gain selon le nombre de services ajoutés (de 1 à 5).
- Une analyse de sensibilité d'équité (pondération vulnérable contre population totale).
- Un chiffrage de l'effet de barrière de la rivière Richelieu.
- Un rapport final écrit (15 à 20 pages) et une présentation orale (10 à 15 minutes).

## État d'avancement

| Étape | Statut |
|-------|--------|
| Cadrage et réorientation du projet (services essentiels) | ✅ Complété |
| Structuration du dépôt GitHub (arborescence du projet, `.gitignore`, branches) | 🔄 En cours |
| Acquisition des données (OSM, recensement, Données Québec, exo, CMM) | 🔄 En cours |
| Intégration du réseau de transport collectif (arrêts d'autobus, gares et lignes de train) | 🔄 En cours |
| Environnement conda (`environment.yml`) et dépendances (`requirements.txt`) | ✅ Complété |
| Tests unitaires (`pytest`) et intégration continue (GitHub Actions) | 🔄 En cours |
| Vérification et contrôle qualité des données | ⏳ À faire |
| Validation de la franchissabilité des ponts dans le graphe | ⏳ À faire |
| Délimitation de la zone d'étude et de la zone tampon | ⏳ À faire |
| Calcul de l'accessibilité par type de service (état actuel, S0) | ⏳ À faire |
| Accès complémentaire par le réseau de transport fixe (arrêts, gares) | ⏳ À faire |
| Pondération de la demande par la vulnérabilité (aînés par AD) | ⏳ À faire |
| Définition et filtrage des sites candidats | ⏳ À faire |
| Optimisation par couverture maximale avec `spopt` (S1, n = 1 à 5) | ⏳ À faire |
| Analyse de sensibilité d'équité | ⏳ À faire |
| Production des résultats (gains, effet de barrière) | ⏳ À faire |
| Cartes interactives et graphiques | ⏳ À faire |
| Rédaction du rapport et préparation de la présentation orale | ⏳ À faire |

## Décisions méthodologiques
- **Réorientation du projet.** Après le constat que la zone était déjà saturée d'arrêts à la demande (ancienne version sur le transport collectif), le projet a évolué vers l'accessibilité aux services essentiels, ce qui permet aussi d'optimiser le type de service à ajouter.
- **Reprise et extension de GMQ210.** Avec l'accord de l'enseignant, le projet réutilise l'approche d'accessibilité piétonne de GMQ210 (OSM, Dijkstra, cotation par type), à laquelle s'ajoutent la pondération par la vulnérabilité, la barrière fluviale et l'optimisation.
- **Facteur de vulnérabilité.** Le choix de travail s'arrête sur les 65 ans et plus, une donnée robuste du recensement qui évite les biais des données manquantes et des indices composites.
- **Mesure par la couverture.** La couverture, plutôt que la distance moyenne, est retenue comme indicateur principal. Les seuils de marche seront fixés à partir des paliers de GMQ210 et de valeurs plus usuelles comme 400 et 800 mètres par exemple.
- **Posture diagnostique.** L'optimisation indique où le manque est le plus grand et quel type de service le comblerait le mieux, ce qui sert autant les décideurs publics et communautaires que les acteurs privés.
- **Intégration du réseau de transport collectif (7 juillet 2026).** L'accès aux services ne se mesure pas uniquement par la marche réelle, les villes à l'étude sont desservies par le réseau d'exo. Le réseau fixe (arrêts d'autobus du GTFS de la CITVR, gares de train) est donc intégré comme dimension complémentaire d'accès, les arrêts et gares agissant comme points d'accès vers les services situés au-delà d'une distance marchable.
- **Réseau fixe seulement, sans horaires ni temps réel (7 juillet 2026).** Seuls les emplacements des arrêts et des gares sont considérés, sans horaires, fréquences ni temps réel. Les villes sont aussi couvertes par un service de transport à la demande, mais les emplacements des arrêts de ce service ne sont pas diffusés ([exo à la demande](https://exoalademande.exo.quebec/search)). À défaut de cette source, l'analyse se limite au réseau fixe, ce qui garde le traitement reproductible et vérifiable.
- **Rôle du train, complémentaire (7 juillet 2026).** La zone compte deux gares (McMasterville et Mont-Saint-Hilaire, ligne Mont-Saint-Hilaire), soit des points d'accès complémentaires au même titre que les arrêts d'autobus, mais bien moins nombreux. Elles servent surtout d'ancrages ponctuels pour les sites candidats, alors que les arrêts d'autobus (plus denses) constituent la principale couche d'accès. Les lignes de train ne sont conservées que comme contexte cartographique et corridor indicatif.
- **Étiquettes OSM des bâtiments résidentiels (9 juillet 2026).** L'expérience de GMQ210 a montré qu'une seule étiquette ne suffit pas à capter toutes les résidences. La liste des valeurs `building` retenues est donc centralisée dans `config.yaml` (dont `house`, absente de la liste GMQ210, et les valeurs usuelles en banlieue québécoise), complétée par les nœuds d'adresse isolés (`addr:housenumber`) et par le réseau piétonnier extrait avec `network_type` défini en configuration. La valeur générique `yes`, ambiguë, ne compte comme résidentielle que si le bâtiment tombe dans un polygone d'usage résidentiel de la CMM (codes 100 à 114). Les types écartés seront journalisés par l'audit afin de vérifier qu'aucun type pertinent ne manque dans la zone.

## Difficultés rencontrées
- **Complétude d'OpenStreetMap.** La qualité des données en milieu périurbain (Beloeil et Mont-Saint-Hilaire) peut varier, pour le réseau comme pour les services. Aucune couche équivalente de Données Québec ou de la MRC n'est diffusée pour permettre un croisement systématique. La vérification s'appuiera donc sur l'imagerie aérienne (orthophotos) et une inspection manuelle ciblée, et les manques résiduels seront documentés comme une limite du projet.
- **Franchissabilité des ponts dans OSM.** La franchissabilité piétonne des ponts sur le Richelieu doit être validée à partir de ce qu'OSM fournit réellement (présence ou non des trottoirs sur les ponts). État : à vérifier. Piste : un module dédié (`bridges.py`) contrôle la présence d'un chemin piéton continu d'une rive à l'autre, croisé au besoin avec l'imagerie aérienne (orthophotos).
- **Données du transport à la demande indisponibles.** Les emplacements des arrêts du service exo à la demande ne sont pas diffusés publiquement. État : contourné. Piste : se limiter au réseau fixe (arrêts du GTFS et gares de train).
- **Hétérogénéité des systèmes de coordonnées.** Les sources arrivent dans des CRS différents (OSM et exo en EPSG:4326, aires de diffusion en EPSG:3347, limites municipales en EPSG:4269, utilisation du sol en EPSG:32188). État : maîtrisé. Piste : une fonction de reprojection unique vers EPSG:2950, couverte par un test unitaire, appliquée à toutes les couches avant analyse pour éviter les jointures spatiales silencieusement fausses.
- **Effet de bordure spatiale.** Découper l'analyse strictement aux frontières municipales aurait ignoré des commerces limitrophes essentiels, la zone tampon règle ce problème, tout en mesurant la demande uniquement dans Beloeil et Mont-Saint-Hilaire.
- **Agrégation des données de recensement.** La demande est diffusée par aire de diffusion, pas par adresse, alors que le calcul d'accessibilité se fait entre points précis (résidences et services), ce qui introduit une perte de précision à garder en tête.
- **Choix du facteur de vulnérabilité.** Le facteur est limité aux données disponibles. Un seul critère est retenu (65 ans et plus) par souci de simplicité, alors que plusieurs pourraient être combinés et pondérés. 
- **Modélisation simplifiée de l'offre et de la demande.** La demande compte les personnes sans nuance d'intensité du besoin, et l'offre traite chaque service comme équivalent, sans tenir compte de sa taille ni de sa capacité. Ces raffinements sont écartés par manque de données.