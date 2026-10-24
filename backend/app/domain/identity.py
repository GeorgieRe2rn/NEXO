from __future__ import annotations

import unicodedata
from datetime import date, datetime

POS_MAP = {
    "goalkeeper": "GK",
    "gk": "GK",
    "defender": "DF",
    "defence": "DF",
    "defense": "DF",
    "df": "DF",
    "midfielder": "MF",
    "midfield": "MF",
    "mf": "MF",
    "attacker": "FW",
    "forward": "FW",
    "offence": "FW",
    "offense": "FW",
    "striker": "FW",
    "fw": "FW",
}

NAT_CODE = {
    "argentina": "ar",
    "belgium": "be",
    "brazil": "br",
    "colombia": "co",
    "croatia": "hr",
    "denmark": "dk",
    "ecuador": "ec",
    "egypt": "eg",
    "england": "gb",
    "france": "fr",
    "georgia": "ge",
    "germany": "de",
    "italy": "it",
    "japan": "jp",
    "mexico": "mx",
    "morocco": "ma",
    "netherlands": "nl",
    "nigeria": "ng",
    "norway": "no",
    "paraguay": "py",
    "poland": "pl",
    "portugal": "pt",
    "scotland": "gb",
    "senegal": "sn",
    "serbia": "rs",
    "south korea": "kr",
    "korea, south": "kr",
    "spain": "es",
    "sweden": "se",
    "switzerland": "ch",
    "turkey": "tr",
    "ukraine": "ua",
    "united states": "us",
    "usa": "us",
    "uruguay": "uy",
    "wales": "gb",
    "gabon": "ga",
    "canada": "ca",
    "chile": "cl",
    "ivory coast": "ci",
    "cote d'ivoire": "ci",
    "cameroon": "cm",
    "ghana": "gh",
    "austria": "at",
    "ireland": "ie",
    "republic of ireland": "ie",
    "northern ireland": "gb",
    "algeria": "dz",
    "tunisia": "tn",
    "mali": "ml",
    "venezuela": "ve",
    "peru": "pe",
    "bolivia": "bo",
    "costa rica": "cr",
    "honduras": "hn",
    "jamaica": "jm",
    "panama": "pa",
    "australia": "au",
    "new zealand": "nz",
    "hungary": "hu",
    "czech republic": "cz",
    "czechia": "cz",
    "slovakia": "sk",
    "slovenia": "si",
    "greece": "gr",
    "finland": "fi",
    "iceland": "is",
    "romania": "ro",
    "bosnia and herzegovina": "ba",
    "albania": "al",
    "kosovo": "xk",
    "north macedonia": "mk",
    "montenegro": "me",
}


def fold(text: str) -> str:
    raw = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()


def club_fits_league(name: str, league_code: str) -> bool:
    """Evita cruces conocidos: Chivas/CHI vs Chicago Fire, Inter vs Inter Miami."""
    n = fold(name)
    code = (league_code or "").upper()
    if code == "MX":
        if "chicago" in n or "miami" in n or "galaxy" in n or "sounders" in n:
            return False
    if code == "MLS":
        if "chivas" in n or "guadalajara" in n:
            return False
        if "internazionale" in n or n in {"inter", "inter milan"}:
            return False
    if code == "SA":
        if "miami" in n:
            return False
    return True


def norm_name(text: str) -> str:
    s = fold(text)
    for token in (
        "football club",
        "calcio",
        "club de futbol",
        "futbol club",
        "cf ",
        " fc",
        "fc ",
        " cf",
        " afc",
        "c.f.",
        "f.c.",
        "club ",
        " de ",
    ):
        s = s.replace(token, " ")
    normalized = " ".join(s.split())
    return {"real racing santander":"racing santander", "racing santander":"racing santander", "como 1907":"como"}.get(normalized, normalized)


def map_position(raw: str | None) -> tuple[str, str]:
    label = (raw or "Midfielder").strip()
    code = POS_MAP.get(label.lower(), "MF")
    if code == "MF" and label.lower() in POS_MAP:
        code = POS_MAP[label.lower()]
    return code, label


def nat_code(nationality: str | None) -> str:
    if not nationality:
        return "UN"
    return NAT_CODE.get(fold(nationality), "UN")


def age_from_dob(dob: str | None, fallback: int = 0) -> int:
    if not dob:
        return fallback
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return fallback
    today = datetime.utcnow().date()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return max(15, min(50, years))
