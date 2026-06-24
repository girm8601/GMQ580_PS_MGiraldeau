# Titre du projet
**Équipe :** Prénom Nom / Prénom Nom  
*Changez le titre du projet, il peut évoluer dans le temps. Nommez les membres du groupe*

## Problématique
*Une courte description de l'objectif du projet*

*Par exemple, posez-vous les questions suivantes :* 
- *Quel phénomène ou enjeu géomatique voulez-vous étudier ?*
- *Pourquoi ce sujet est-il pertinent dans la région choisie ?*
- *Qui serait concerné par les résultats (municipalité, citoyens, urbanistes, chercheurs) ?*
- *Qu'est-ce que vous n'allez pas traiter, pour rester réaliste dans le temps disponible ?*
- *Travaillez-vous à l'échelle du bâtiment, du quartier, de la ville, de la région ?*
- *Avez-vous déjà identifié une source de données qui permettrait de répondre à cette question ?*
- *...*

## Zone d'étude
*Localisation, échelle, pourquoi ce choix ?*

## Données
*Listez les données pertinentes*
| Source | Format | CRS | Accès |
|--------|--------|-----|-------|
|        |        |     |       |

## Modèle de données
*Cette section peut être utile si on s'oriente vers une architecture client/serveur/base de données. On pourra expliquer notre modèle de données.*

## Pipeline de traitement ou Architecture
*Si on souhaite faire simplement un pipeline de traitement, on peut expliquer les étapes. Ou alors proposer une architecture pour une application (ex: client/serveur/db).*

*Schéma ou diagramme Mermaid (https://mermaid.live/)*
```mermaid
flowchart TD
    A[Données brutes] -->|pystac-client / gdown| B[Acquisition]
    B -->|rioxarray / GeoPandas| C[Prétraitement]
    C -->|masquage nuages, reprojection EPSG:32198, découpage zone d'étude| D[Nettoyage & harmonisation]
    D -->|rasterio / numpy / xarray| E[Analyse géospatiale]
    E -->|indice, statistique, série temporelle, etc.| F[Résultats]
    F -->|Folium / Plotly / matplotlib| G[Visualisation]
    G --> H[Rapport & présentation finale]

    style A fill:#EEEDFE,stroke:#534AB7,color:#26215C
    style B fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style C fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style D fill:#E1F5EE,stroke:#0F6E56,color:#04342C
    style E fill:#E6F1FB,stroke:#185FA5,color:#042C53
    style F fill:#FAEEDA,stroke:#854F0B,color:#412402
    style G fill:#FAEEDA,stroke:#854F0B,color:#412402
    style H fill:#FAECE7,stroke:#993C1D,color:#4A1B0C
```

*Si Mermaid est compliqué, on utilise un outil pour faire des diagrammes (https://app.diagrams.net/), on peut simplement utiliser l'image du diagramme.*
![Pipeline du projet](docs/mydiagram.drawio.png)

## Librairies principales (ou stack)
*Liste avec justification du choix*
*Si on développe un STACK, on doit expliquer ce que contient chaque composante, ex: Flask/FastAPI, PostGIS, Leaflet, ...*

## Livrables attendus
*Ce que le projet produira concrètement*

## État d'avancement
*Faites un petit tableau avec des tâches ou des étapes à compléter*
| Étape | Statut |
|-------|--------|
| Acquisition des données | ✅ Complété |
| Masquage nuageux | 🔄 En cours |
| Analyse temporelle | ⏳ À faire |

## Décisions méthodologiques
*Journal des choix importants avec justification  (mis à jour à chaque séance)*

## Difficultés rencontrées
*Problèmes résolus et en cours*