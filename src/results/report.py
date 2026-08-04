"""Rapport PDF du projet, diffusion des resultats.

Ce module assemble un rapport PDF avec fpdf2. Il presente une page titre puis les trois
volets du projet, diagnostic, validation et levier. Chaque volet porte son titre, une
courte introduction, ses figures et tableaux, puis une courte conclusion qui enchaine vers
l'etape suivante. Le contenu editorial, introductions et conclusions, est defini ici comme
la prose du README. Les chiffres et les figures viennent des modules d'analyse.
"""

from __future__ import annotations

import datetime
import math
import numbers
import os

from fpdf import FPDF

from src.results.metrics import same_threshold_gap

# Police de base de fpdf2, limitee a latin-1. La ligature de Beloeil et plusieurs signes
# francais en sortent, ils deviendraient des points d'interrogation dans le PDF.
BASE_FAMILY = "Helvetica"
# Police Unicode, livree avec matplotlib qui est deja une dependance du projet. Aucun
# fichier de police n'est donc a versionner.
UNICODE_FAMILY = "DejaVuSans"
UNICODE_FILES = {"": "DejaVuSans.ttf", "B": "DejaVuSans-Bold.ttf"}
# Au dela de cette precision, un nombre affiche plus de chiffres que la donnee n'en porte.
MAX_DECIMALS = 6

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

BOUND_TABLE_TITLE = (
    "Meilleure implantation possible de cinq services d'un même type, "
    "couverture de ce seul type"
)

INTRO = {
    "diagnostic": (
        "Ce volet mesure l'accès à pied des aînés aux services essentiels, puis le compare "
        "au reste de la population. Il vérifie si les aînés forment un groupe aux besoins "
        "distincts."
    ),
    "validation": (
        "Ce volet vérifie deux pistes de solution avant de retenir la bonne. Il chiffre le "
        "gain de l'ajout de nouveaux services et l'effet de barrière de la rivière. "
        "L'ajout est chiffré deux fois. La figure et le premier tableau suivent un "
        "scénario réaliste, les services sont ajoutés un à la fois dans l'ordre où chacun "
        "rapporte le plus, et la couverture est pondérée sur les neuf services. Le second "
        "tableau place au contraire les cinq services d'un seul coup par la couverture "
        "maximale, ce qui donne la meilleure implantation possible. Sa couverture porte "
        "sur le seul type ajouté, elle ne se compare donc pas à celle de la figure."
    ),
    "lever": (
        "Ce volet propose la solution retenue. Il recommande aux aînés, dans chaque ville, "
        "le meilleur secteur d'adresses déjà existantes et le meilleur secteur où implanter "
        "du logement, à la marche et au transport. Le nombre de points d'un secteur "
        "d'adresses est son nombre de résidences. Celui d'un secteur de logement est son "
        "nombre de terrains à développer, parfois un seul. Chaque ville obtient son "
        "meilleur secteur même lorsque la cote de ce secteur reste insuffisante, car un "
        "aîné qui tient à cette ville a quand même besoin de connaître le meilleur choix "
        "qui s'y trouve."
    ),
}

CONCLUSION = {
    "diagnostic": (
        "Chaque groupe est mesuré à la distance qu'il peut parcourir, 800 mètres pour un "
        "aîné et 1000 mètres pour le reste de la population. Cette différence de tolérance "
        "est une hypothèse de départ tirée de la littérature, et non un résultat. Ce que le "
        "diagnostic chiffre, c'est sa conséquence sur ce territoire. À distance tolérable, "
        "l'offre existante rend moins de services utilisables aux aînés, et les services "
        "les mieux atteints, l'école et la garderie, sont ceux qui leur servent le moins. "
        "La solution doit donc être pensée pour eux."
    ),
    "validation": (
        "Ajouter des services ne suffit pas. Même placés à la meilleure position possible, "
        "cinq nouveaux services d'un même type laissent la majorité des aînés encore sans "
        "accès à ce type, et il faudrait recommencer pour chacun des neuf services "
        "essentiels. Cette piste ne relève pas non plus de la municipalité, un service est "
        "une entreprise privée. L'effet de barrière de la rivière est de son côté "
        "négligeable. Aucune de ces deux pistes n'est la solution, ce qui ouvre la voie au "
        "levier. Celui ci part des services déjà en place et cherche les meilleurs "
        "secteurs, ceux d'adresses existantes qui donnent un résultat immédiat sans rien "
        "construire, et ceux où implanter du logement pour ajouter de nouvelles places."
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


def _register_font(pdf):
    """Enregistre la police Unicode du rapport et retourne la famille a utiliser.

    Les polices de base de fpdf2 sont limitees a latin-1, ce qui remplace par un point
    d'interrogation tout signe hors de ce jeu, a commencer par la ligature de Beloeil.
    Matplotlib livre DejaVu Sans, une police Unicode complete, et il est deja une
    dependance du projet. Si elle est introuvable, le rapport se produit quand meme avec la
    police de base et la transcription latin-1, un probleme de police ne doit pas arreter le
    pipeline.
    """
    try:
        import matplotlib

        folder = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        paths = {
            style: os.path.join(folder, name) for style, name in UNICODE_FILES.items()
        }
        if not all(os.path.exists(path) for path in paths.values()):
            return BASE_FAMILY
        for style, path in paths.items():
            pdf.add_font(UNICODE_FAMILY, style, path)
        return UNICODE_FAMILY
    except Exception:  # noqa: BLE001  (repli sur la police de base, jamais bloquant)
        return BASE_FAMILY


def _text(pdf, value):
    """Texte pret a ecrire, transcrit en latin-1 seulement si la police l'exige."""
    text = "" if value is None else str(value)
    if getattr(pdf, "doc_family", BASE_FAMILY) == UNICODE_FAMILY:
        return text
    return text.encode("latin-1", "replace").decode("latin-1")


def _french_number(value, decimal_separator):
    """Ecrit un nombre a la francaise, virgule decimale et decimales utiles seulement.

    Le guide de redaction du departement demande la virgule comme signe decimal. Il exempte
    en revanche les tableaux du separateur des milliers, par souci d'esthetique, aucune
    espace n'est donc inseree ici. Un nombre entier perd sa decimale nulle, un compte de
    personnes n'a pas a s'afficher avec un zero apres la virgule.
    """
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return ""
    text = f"{number:.{MAX_DECIMALS}f}".rstrip("0").rstrip(".")
    if text in ("", "-"):
        text = "0"
    return text.replace(".", decimal_separator)


def _cell_value(pdf, value, decimal_separator):
    """Contenu d'une case de tableau, les nombres a la francaise et le texte tel quel."""
    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        return _text(pdf, _french_number(value, decimal_separator))
    return _text(pdf, value)


def _french_date(today):
    """Date du jour en francais, par exemple 23 juillet 2026."""
    return f"{today.day} {MONTHS[today.month - 1]} {today.year}"


def _usable_width(pdf):
    """Largeur utile de la page entre les marges."""
    return pdf.w - pdf.l_margin - pdf.r_margin


def _multi(pdf, text, height, align="L"):
    """Ecrit un bloc de texte sur toute la largeur utile depuis la marge gauche."""
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(_usable_width(pdf), height, _text(pdf, text), align=align)


def _title_page(pdf, config):
    """Ecrit la page titre, logo, titre du projet, cours, auteur et date."""
    report = config["report"]
    pdf.add_page()
    logo = report.get("logo")
    if logo and os.path.exists(logo):
        logo_w = report["logo_width_mm"]
        pdf.image(logo, x=(pdf.w - logo_w) / 2, y=30, w=logo_w)
    pdf.set_y(75)
    pdf.set_font(pdf.doc_family, "B", report["font_size_title"])
    _multi(pdf, report["title"], 10, "C")
    pdf.ln(8)
    pdf.set_font(pdf.doc_family, "", report["font_size_subtitle"])
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
    pdf.set_font(pdf.doc_family, "B", report["font_size_heading"])
    pdf.set_text_color(*report["color_heading"])
    _multi(pdf, text, 9)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _paragraph(pdf, config, text):
    """Ecrit un paragraphe courant."""
    pdf.set_font(pdf.doc_family, "", config["report"]["font_size_body"])
    _multi(pdf, text, 6)
    pdf.ln(2)


def _add_figure(pdf, path):
    """Insere une figure a la largeur de la page, si elle existe."""
    if not path or not os.path.exists(path):
        return
    pdf.image(path, w=_usable_width(pdf))
    pdf.ln(3)


def _add_row(pdf, values, widths, style, sizes, decimal_separator):
    """Ecrit une ligne de tableau, chaque case a la largeur et a la taille de sa colonne."""
    pdf.set_x(pdf.l_margin)
    for value, width, size in zip(values, widths, sizes):
        pdf.set_font(pdf.doc_family, style, size)
        pdf.cell(
            width, 6, _cell_value(pdf, value, decimal_separator), border=1, align="C"
        )
    pdf.ln(6)


def _widest_at(pdf, title, values, size):
    """Largeur de la case la plus large d'une colonne a une taille de police donnee.

    Le titre est mesure en gras et les valeurs dans le style courant, comme ils seront
    ecrits. A taille egale le gras est plus large, c'est donc souvent le titre qui decide.
    """
    pdf.set_font(pdf.doc_family, "B", size)
    widest = pdf.get_string_width(title)
    pdf.set_font(pdf.doc_family, "", size)
    for value in values:
        widest = max(widest, pdf.get_string_width(value))
    return widest


def _column_font_sizes(pdf, df, widths, base_size, min_size, decimal_separator):
    """Taille de police de chaque colonne, la plus grande qui fait tenir toutes ses cases.

    La taille est choisie par colonne et non par case. Une taille par case donnait un
    tableau ou deux valeurs voisines d'une meme colonne n'avaient pas la meme hauteur de
    caractere, ce qui se lit comme un defaut d'impression.
    """
    sizes = []
    for column, width in zip(df.columns, widths):
        title = _text(pdf, column)
        values = [_cell_value(pdf, value, decimal_separator) for value in df[column]]
        chosen = min_size
        for size in range(base_size, min_size - 1, -1):
            if _widest_at(pdf, title, values, size) <= width - 2:
                chosen = size
                break
        sizes.append(chosen)
    return sizes


def _column_widths(pdf, df, base_size, total_width, decimal_separator):
    """Repartit la largeur de la page entre les colonnes selon leur contenu le plus long.

    Des colonnes de largeur egale font tenir un identifiant d'aire de diffusion dans la
    meme case qu'un seuil en metres. La colonne large descend alors a la taille minimale et
    finit par tronquer son texte, pendant que la colonne etroite laisse du vide. La largeur
    demandee par chaque colonne est donc mesuree sur son contenu, puis ramenee au prorata
    sur la largeur disponible. La somme reste exactement egale a cette largeur.
    """
    needs = []
    for column in df.columns:
        pdf.set_font(pdf.doc_family, "B", base_size)
        widest = pdf.get_string_width(_text(pdf, column))
        pdf.set_font(pdf.doc_family, "", base_size)
        for value in df[column]:
            text = _cell_value(pdf, value, decimal_separator)
            widest = max(widest, pdf.get_string_width(text))
        needs.append(widest + 2.0)
    total = sum(needs)
    if total <= 0:
        return [total_width / len(needs)] * len(needs)
    return [total_width * need / total for need in needs]


def _in_french(df, config):
    """Traduit les titres de colonnes et les valeurs internes d'un tableau du rapport.

    Le rapport est le document de diffusion, tout ce qu'il affiche est en francais. Les
    tableaux CSV gardent de leur cote leurs cles anglaises, ils sont lus par une machine.
    Seules les colonnes de texte sont traduites, les colonnes de nombres restent intactes.
    """
    report = config["report"]
    values = report["value_labels"]
    translated = df.copy()
    for column in translated.select_dtypes(include="object").columns:
        translated[column] = translated[column].map(
            lambda value: values.get(value, value) if isinstance(value, str) else value
        )
    return translated.rename(columns=report["column_labels"])


def _add_table(pdf, config, title, df):
    """Insere un tableau, un titre puis l'en-tete et les lignes a largeur egale."""
    if df is None or len(df) == 0:
        return
    df = _in_french(df, config)
    report = config["report"]
    base_size = report["table_font_size"]
    min_size = report["table_min_font_size"]
    separator = report["decimal_separator"]
    columns = list(df.columns)
    widths = _column_widths(pdf, df, base_size, _usable_width(pdf), separator)
    sizes = _column_font_sizes(pdf, df, widths, base_size, min_size, separator)
    pdf.set_font(pdf.doc_family, "B", report["font_size_table_title"])
    _multi(pdf, title, 6)
    _add_row(pdf, columns, widths, "B", sizes, separator)
    for _, row in df.iterrows():
        _add_row(pdf, [row[column] for column in columns], widths, "", sizes, separator)
    pdf.ln(3)


def _add_link(pdf, config, label, url):
    """Ecrit un lien cliquable vers une carte interactive."""
    report = config["report"]
    pdf.set_font(pdf.doc_family, "U", report["font_size_body"])
    pdf.set_text_color(*report["color_link"])
    pdf.set_x(pdf.l_margin)
    pdf.cell(_usable_width(pdf), 7, _text(pdf, label), link=url)
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)


LOCATION_NOTE = (
    "Au même seuil de {threshold} m pour les deux groupes, les aînés sont au contraire "
    "mieux situés que le reste de la population sur {favorable} des {total} types de "
    "service, de {gap} {unit} de pourcentage en moyenne. L'écart mesuré plus haut ne vient "
    "donc pas de l'endroit où vivent les aînés, mais de la distance plus courte qu'ils "
    "peuvent parcourir. C'est précisément ce que le levier cherche à corriger."
)


def diagnostic_conclusion(config, tables):
    """Conclusion du diagnostic, completee par la comparaison a seuil commun.

    Le sommaire de couverture mesure aussi chaque groupe au seuil de l'autre. Quand les
    aines ressortent devant a seuil commun, la phrase le dit, car c'est le fait qui separe
    un probleme de localisation d'un probleme de distance tolerable. Si le sommaire est
    absent ou si le fait ne tient pas, la conclusion reste celle de base.
    """
    base = CONCLUSION["diagnostic"]
    summary = tables.get("coverage")
    if summary is None or len(summary) == 0:
        return base
    threshold = config["optimization"]["coverage_threshold_seniors_m"]
    result = same_threshold_gap(summary, threshold)
    if result is None:
        return base
    favorable, total, gap = result
    if favorable * 2 <= total or gap <= 0:
        return base
    return (
        base
        + " "
        + LOCATION_NOTE.format(
            threshold=threshold,
            favorable=favorable,
            total=total,
            gap=_french_number(gap, config["report"]["decimal_separator"]),
            unit="point" if gap < 2 else "points",
        )
    )


def _section(pdf, config, key, figures, tables, links=(), conclusion=None):
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
    _paragraph(pdf, config, conclusion or CONCLUSION[key])


def build_report(config, figures, tables, logger=None):
    """Assemble le rapport PDF des trois volets a partir des figures et des tableaux.

    figures associe une cle de figure a son chemin PNG. tables associe une cle de tableau a
    son DataFrame. Le rapport est ecrit au chemin de la configuration.
    """
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.doc_family = _register_font(pdf)
    if pdf.doc_family == BASE_FAMILY and logger is not None:
        logger.warning(
            "Police Unicode introuvable, le rapport utilise la police de base et les "
            "signes hors latin-1 seront remplaces"
        )
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
        conclusion=diagnostic_conclusion(config, tables),
    )
    _section(
        pdf,
        config,
        "validation",
        [figures.get("gain")],
        [
            (
                "Effet de chaque ajout sur la couverture pondérée des neuf services",
                tables.get("service_addition"),
            ),
            (
                BOUND_TABLE_TITLE,
                tables.get("addition_bound"),
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
