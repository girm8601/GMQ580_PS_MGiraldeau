# Dockerfile du projet, niveau 2 de reproductibilite (systeme complet).
# L'image de base fournit deja GDAL et ses dependances systeme, ce qui evite les
# erreurs de version entre GDAL Python et GDAL systeme en geomatique. Sa version est
# epinglee, une image de base flottante ferait deriver le resultat sans avertissement.
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.0

# Journaux ecrits au fil de l'execution plutot qu'a la fin. Le pipeline dure plusieurs
# minutes et son avancement doit rester visible dans la console de docker run.
ENV PYTHONUNBUFFERED=1

# Installation de pip et des outils Python.
RUN apt-get update && apt-get install -y \
    python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie et installation des dependances Python. Le fichier est copie seul et avant le
# code, la couche d'installation est ainsi reutilisee tant que les versions ne bougent pas.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source du projet.
COPY . .

# Dossiers de travail. Le fichier .dockerignore ecarte leur contenu, ils doivent donc
# exister dans l'image pour que le conteneur tourne meme sans montage.
RUN mkdir -p data/raw data/processed outputs/maps outputs/figures outputs/tables logs

# Commande par defaut, le pipeline complet. Elle suppose les couches deja presentes dans
# data. Pour les regenerer, remplacer la commande au lancement,
# docker run ... gmq580_ps_mg python3 download_data.py
CMD ["python3", "main.py"]
