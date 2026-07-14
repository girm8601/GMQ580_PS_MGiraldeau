# Dockerfile du projet, niveau 2 de reproductibilite (systeme complet).
# L'image de base fournit deja GDAL et ses dependances systeme, ce qui evite les
# erreurs de version entre GDAL Python et GDAL systeme en geomatique.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.0

# Installation de pip et des outils Python.
RUN apt-get update && apt-get install -y \
    python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dependances Python.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source du projet.
COPY . .

# Commande executee au demarrage du conteneur, le pipeline complet.
CMD ["python3", "main.py"]
