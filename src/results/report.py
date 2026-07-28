"""Rapport PDF du projet, diffusion des resultats.

Ce module assemble un rapport PDF avec fpdf2. Il presente une page titre puis les trois
volets du projet, diagnostic, validation et levier. Chaque volet porte son titre, une
courte introduction, ses figures et tableaux, puis une courte conclusion qui enchaine vers
l'etape suivante. Le contenu editorial, introductions et conclusions, est defini ici comme
la prose du README. Les chiffres et les figures viennent des modules d'analyse.
"""

from __future__ import annotations

import datetime
import os

from fpdf import FPDF

MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]

INTRO = {
    "diagnostic": (
        "Ce volet mesure l'accès à pied des aînés aux services essentiels, puis le compare "
        "au reste de la population. Il vérifie si les aînés forment un groupe aux besoins "
        "distincts."
    ),
    "validation": (
        "Ce volet vérifie deux pistes de solution avant de retenir la bonne. Il chiffre le "
        "gain de l'ajout de nouveaux services et l'effet de barrière de la rivière."
    ),
    "lever": (
        "Ce volet propose la solution retenue. Il recommande aux aînés, dans chaque ville, "
        "le meilleur secteur d'adresses déjà existantes et le meilleur secteur où implanter "
        "du logement, à la marche et au transport."
    ),
}

CONCLUSION = {
    "diagnostic": (
        "Le reste de la population est mieux desservi par les différents types de services "
        "et par les services jugés plus importants pour ce groupe, comme l'école et la "
        "garderie. Les aînés ont donc des besoins qui leur sont propres, ce qui justifie "
        "une solution ciblée."
    ),
    "validation": (
        "Le gain de l'ajout de services reste faible peu importe le nombre d'ajouts et "
        "l'effet de barrière de la rivière est négligeable. Aucune de ces deux pistes n'est "
        "la solution, ce qui ouvre la voie au levier."
    ),
    "lever": (
        "Ces secteurs d'adresses résidentielles existantes et d'ajout de logements donnent "
        "le meilleur accès à pied aux services essentiels selon la préférence de "
        "déplacement, seulement la marche ou avec le transport en commun. Un secteur de "
        "chaque type est retenu par ville, ce qui laisse un choix réel dans les quatre "
        "municipalités. Les deux cartes interactives ci-dessous les situent sur le "
        "territoire. Elles répondent au besoin établi par le diagnostic."
    ),
}


def _latin1(text):
    """Ramene un texte a l'encodage des polices de base, hors latin-1 devient un point."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _french_date(today):
    """Date du jour en francais, par exemple 23 juillet 2026."""
    return f"{today.day} {MONTHS[today.month - 1]} {today.year}"


def _usable_width(pdf):
    """Largeur utile de la page entre les marges."""
    return pdf.w - pdf.l_margin - pdf.r_margin


def _multi(pdf, text, height, align="L"):
    """Ecrit un bloc de texte sur toute la largeur utile depuis la marge gauche."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(_usable_width(pdf), height, _latin1(text), align=align)


def _title_page(pdf, config):
    """Ecrit la page titre, logo, titre du projet, cours, auteur et date."""
    report = config["report"]
    pdf.add_page()
    logo = report.get("logo")
    if logo and os.path.exists(logo):
        logo_w = report["logo_width_mm"]
        pdf.image(logo, x=(pdf.w - logo_w) / 2, y=30, w=logo_w)
    pdf.set_y(75)
    pdf.set_font("Helvetica", "B", report["font_size_title"])
    _multi(pdf, report["title"], 10, "C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", report["font_size_subtitle"])
    # Date locale du poste, obtenue depuis un instant date pour rester sans ambiguite.
    today = datetime.datetime.now(datetime.timezone.utc).astimezone().date()
    lines = [
        report["course"],
        report["author"],
        _french_date(today),
    ]
    for line in lines:
        _multi(pdf, line, 8, "C")


def _heading(pdf, config, text):
    """Ecrit le titre d'un volet dans la couleur de la configuration."""
    report = config["report"]
    pdf.set_font("Helvetica", "B", report["font_size_heading"])
    pdf.set_text_color(*report["color_heading"])
    _multi(pdf, text, 9)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _paragraph(pdf, config, text):
    """Ecrit un paragraphe courant."""
    pdf.set_font("Helvetica", "", config["report"]["font_size_body"])
    _multi(pdf, text, 6)
    pdf.ln(2)


def _add_figure(pdf, path):
    """Insere une figure a la largeur de la page, si elle existe."""
    if not path or not os.path.exists(path):
        return
    pdf.image(path, w=_usable_width(pdf))
    pdf.ln(3)


def _fit_font(pdf, text, width, style, base_size, min_size):
    """Choisit la plus grande police qui laisse le texte tenir dans sa case.

    Les titres de colonnes et les identifiants d'aire de diffusion sont longs. La taille
    descend d'un point a la fois jusqu'a ce que le texte entre, sans passer sous la taille
    minimale.
    """
    for size in range(base_size, min_size - 1, -1):
        pdf.set_font("Helvetica", style, size)
        if pdf.get_string_width(text) <= width - 2:
            return
    pdf.set_font("Helvetica", style, min_size)


def _add_row(pdf, values, width, style, base_size, min_size):
    """Ecrit une ligne de tableau, chaque case avec sa propre taille de police."""
    pdf.set_x(pdf.l_margin)
    for value in values:
        text = _latin1(value)
        _fit_font(pdf, text, width, style, base_size, min_size)
        pdf.cell(width, 6, text, border=1, align="C")
    pdf.ln(6)


def _add_table(pdf, config, title, df):
    """Insere un tableau, un titre puis l'en-tete et les lignes a largeur egale."""
    if df is None or len(df) == 0:
        return
    report = config["report"]
    base_size = report["table_font_size"]
    min_size = report["table_min_font_size"]
    columns = list(df.columns)
    width = _usable_width(pdf) / len(columns)
    pdf.set_font("Helvetica", "B", report["font_size_table_title"])
    _multi(pdf, title, 6)
    _add_row(pdf, columns, width, "B", base_size, min_size)
    for _, row in df.iterrows():
        _add_row(
            pdf, [row[column] for column in columns], width, "", base_size, min_size
        )
    pdf.ln(3)


def _add_link(pdf, config, label, url):
    """Ecrit un lien cliquable vers une carte interactive."""
    report = config["report"]
    pdf.set_font("Helvetica", "U", report["font_size_body"])
    pdf.set_text_color(*report["color_link"])
    pdf.set_x(pdf.l_margin)
    pdf.cell(_usable_width(pdf), 7, _latin1(label), link=url)
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)


def _section(pdf, config, key, figures, tables, links=()):
    """Ecrit un volet, titre, introduction, figures, tableaux, liens puis conclusion."""
    pdf.add_page()
    _heading(pdf, config, config["report"]["section_titles"][key])
    _paragraph(pdf, config, INTRO[key])
    for path in figures:
        _add_figure(pdf, path)
    for title, df in tables:
        _add_table(pdf, config, title, df)
    for label, url in links:
        _add_link(pdf, config, label, url)
    _paragraph(pdf, config, CONCLUSION[key])


def build_report(config, figures, tables, logger=None):
    """Assemble le rapport PDF des trois volets a partir des figures et des tableaux.

    figures associe une cle de figure a son chemin PNG. tables associe une cle de tableau a
    son DataFrame. Le rapport est ecrit au chemin de la configuration.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=config["report"]["page_margin_mm"])
    _title_page(pdf, config)
    _section(
        pdf,
        config,
        "diagnostic",
        [figures.get("coverage")],
        [
            (
                "Écart de couverture entre aînés et reste de la population",
                tables.get("comparison"),
            )
        ],
    )
    _section(
        pdf,
        config,
        "validation",
        [figures.get("gain")],
        [
            (
                "Effet de chaque ajout de service, par groupe",
                tables.get("service_addition"),
            ),
            (
                "Effet de barrière de la rivière par groupe et par service",
                tables.get("barrier"),
            ),
        ],
    )
    maps = config["paths"]["map_files"]
    base = config["report"]["maps_base_url"]
    _section(
        pdf,
        config,
        "lever",
        [],
        [
            ("Secteurs recommandés selon la marche", tables.get("recommendation_walk")),
            (
                "Secteurs recommandés selon le transport",
                tables.get("recommendation_transit"),
            ),
        ],
        links=[
            ("Carte interactive du levier à la marche", f"{base}/{maps['lever_walk']}"),
            (
                "Carte interactive du levier au transport",
                f"{base}/{maps['lever_transit']}",
            ),
        ],
    )

    output = config["report"]["output"]
    folder = os.path.dirname(output)
    if folder:
        os.makedirs(folder, exist_ok=True)
    pdf.output(output)
    if logger is not None:
        logger.info("Rapport PDF genere, %s", output)
