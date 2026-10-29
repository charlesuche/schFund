"""Provider marks (logo slot) and host-country flags for the public pages.

Each record is matched to a provider by its slug prefix. A record shows its
provider's official logo when its provider_logo field names a file that is in
app/static/logos/ (see app/static/logos/SOURCES.md for where each file came
from); otherwise the page shows the provider's initials, as in the Figma
"Provider mark" component.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"

# key: (display name, initials shown until the official logo is added)
PROVIDERS = {
    "aston": ("Aston University", "ASTON"),
    "boustany": ("Boustany Foundation", "BF"),
    "chalmers": ("Chalmers University of Technology", "CTH"),
    "chevening": ("Chevening Scholarships", "CHEV"),
    "unipv": ("University of Pavia", "UNIPV"),
    "csc": ("Commonwealth Scholarship Commission", "CSC"),
    "daad": ("DAAD", "DAAD"),
    "disco": ("DiSCo Lazio", "DiSCo"),
    "dsu-toscana": ("DSU Toscana", "DSU"),
    "edisu-pavia": ("EDiSU Pavia", "EDiSU"),
    "edisu-piemonte": ("EDISU Piemonte", "EDISU"),
    "ergo": ("ER.GO", "ER.GO"),
    "ersu-messina": ("ERSU Messina", "ERSU"),
    "esu-padova": ("ESU Padova", "ESU"),
    "fao": ("FAO", "FAO"),
    "gates-cambridge": ("Gates Cambridge", "GATES"),
    "glasgow": ("University of Glasgow", "UofG"),
    "hec": ("HEC Paris", "HEC"),
    "intermaths": ("InterMaths", "IM"),
    "knight-hennessy": ("Knight-Hennessy Scholars", "KHS"),
    "kth": ("KTH Royal Institute of Technology", "KTH"),
    "leeds": ("University of Leeds", "LEEDS"),
    "lund": ("Lund University", "LU"),
    "maastricht": ("Maastricht University", "UM"),
    "maeci": ("Italian Ministry of Foreign Affairs", "MAECI"),
    "nawa": ("NAWA", "NAWA"),
    "unipd": ("University of Padova", "UNIPD"),
    "polito": ("Politecnico di Torino", "PoliTO"),
    "rhodes": ("Rhodes Trust", "RHODES"),
    "romania-mfa": ("Romanian Ministry of Foreign Affairs", "MFA"),
    "si": ("Swedish Institute", "SI"),
    "stellenbosch": ("Stellenbosch University", "SU"),
    "stipendium-hungaricum": ("Stipendium Hungaricum", "SH"),
    "strathclyde": ("University of Strathclyde", "STRATH"),
    "turkiye-burslari": ("Türkiye Scholarships", "TB"),
    "unica": ("University of Cagliari", "UNICA"),
    "unical": ("University of Calabria", "UNICAL"),
    "unime": ("University of Messina", "UNIME"),
    "unimore": ("University of Modena and Reggio Emilia", "UNIMORE"),
    "unisi": ("University of Siena", "UNISI"),
    "univr": ("University of Verona", "UNIVR"),
    "uppsala": ("Uppsala University", "UU"),
    "warwick": ("WMG, University of Warwick", "WMG"),
}

# Slug prefix -> provider key. Longest matching prefix wins, so order does not matter.
SLUG_PREFIXES = {
    "aston-": "aston",
    "boustany-": "boustany",
    "chalmers-": "chalmers",
    "chevening-": "chevening",
    "cicops-pavia-": "unipv",
    "civrisk-pavia-": "unipv",
    "csc-": "csc",
    "daad-epos-": "daad",
    "disco-lazio-": "disco",
    "dsu-toscana-": "dsu-toscana",
    "edisu-pavia-": "edisu-pavia",
    "edisu-piemonte-": "edisu-piemonte",
    "ergo-": "ergo",
    "ersu-messina-": "ersu-messina",
    "esu-padova-": "esu-padova",
    "fao-": "fao",
    "gates-cambridge-": "gates-cambridge",
    "glasgow-": "glasgow",
    "hec-": "hec",
    "intermaths-": "intermaths",
    "knight-hennessy-": "knight-hennessy",
    "kth-": "kth",
    "leeds-": "leeds",
    "lund-": "lund",
    "maastricht-": "maastricht",
    "maeci-": "maeci",
    "nawa-": "nawa",
    "padua-": "unipd",
    "polito-": "polito",
    "rhodes-": "rhodes",
    "romania-mfa-": "romania-mfa",
    "si-": "si",
    "stellenbosch-": "stellenbosch",
    "stipendium-hungaricum-": "stipendium-hungaricum",
    "strathclyde-": "strathclyde",
    "turkiye-burslari-": "turkiye-burslari",
    "unica-": "unica",
    "unical-": "unical",
    "unime-": "unime",
    "unimore-": "unimore",
    "unisi-": "unisi",
    "univr-": "univr",
    "uppsala-": "uppsala",
    "warwick-": "warwick",
}

# The four tints used for monograms in the Figma frames.
TONES = ["primary", "info", "danger", "warning"]

# Host country -> flag file in static/flags/ (ISO 3166-1 alpha-2 code).
FLAG_CODES = {
    "Austria": "at", "Egypt": "eg", "France": "fr", "Germany": "de", "Hungary": "hu",
    "Italy": "it", "Jordan": "jo", "Mexico": "mx", "Netherlands": "nl", "Poland": "pl",
    "Romania": "ro", "South Africa": "za", "Spain": "es", "Sweden": "se", "Turkey": "tr",
    "United Kingdom": "gb", "United States": "us",
}


def logo_path(provider_logo: dict | None) -> str | None:
    """Static path of the record's logo file, or None if there is none.

    The validator already fails a record whose logo file is missing; checking
    again here means a file deleted later shows initials, not a broken image.
    """
    if not provider_logo or not provider_logo.get("file"):
        return None
    path = f"logos/{provider_logo['file']}"
    if not (STATIC_DIR / path).is_file():
        return None
    return path


def provider_for(slug: str, provider_logo: dict | None = None) -> dict | None:
    """{key, name, initials, tone, logo} for a record slug, or None if unknown."""
    best = None
    for prefix, key in SLUG_PREFIXES.items():
        if slug.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, key)
    if best is None:
        return None
    key = best[1]
    name, initials = PROVIDERS[key]
    # Same key always gets the same tint.
    tone = TONES[sum(ord(ch) for ch in key) % len(TONES)]
    return {"key": key, "name": name, "initials": initials, "tone": tone, "logo": logo_path(provider_logo)}


def flag_for(country: str | None) -> str | None:
    """Static path of the country's flag, or None when we have no flag file."""
    if not country or country not in FLAG_CODES:
        return None
    path = f"flags/{FLAG_CODES[country]}.svg"
    if not (STATIC_DIR / path).exists():
        return None
    return path
