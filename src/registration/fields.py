"""Cleaning of single person fields: names, phone numbers, email addresses.

Each function returns the cleaned value and a list of (code, reason) notes for the review report.
"""
import re

import pandas as pd

# "valid email address" of the HTML Standard (4.10.5.1.5, a willful violation of RFC 5322); lengths from RFC 5321 4.5.3.1: local part 64, whole address 254
EMAIL = re.compile(r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$")
EMAIL_LOCAL_MAX, EMAIL_MAX = 64, 254
EMAIL_DOMAIN_TYPOS = {
    "gmial.com": "gmail.com", "gmal.com": "gmail.com", "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.con": "gmail.com",
    "gmail.co": "gmail.com", "gmail.cm": "gmail.com", "yahoo.co": "yahoo.com", "yaho.com": "yahoo.com",
}
# degrees that are removed from a student's name; the dot after S or M is required so that an initial such as "M. Ali" stays
_DEGREE = r"(?:S\.\s?(?:Pd|Kom|Si|T|E|Ag|H|Hum|Sos|Psi|Kep|Farm)|M\.\s?(?:Pd|Si|Kom|T|M|Hum|Ag|Kes|Psi))\.?"
TRAILING_DEGREES = re.compile(rf"(?:(?:,\s*|\s+){_DEGREE})+\s*$", re.I)
LEADING_TITLE = re.compile(r"^(?:Dr|Drs|Dra|Ir|Prof)\.?\s+", re.I)
ROMAN_TOKEN = re.compile(r"^(?:ii|iii|iv|vi|vii|viii|ix)$", re.I)
NAME_PARTICLES = {"bin", "binti", "bte", "van", "de", "der", "di", "da", "von", "ibn", "al", "el"}  # words that stay in lower case inside a name


def blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def text(value) -> str:
    """A cell as one-line text; a whole-number float (Excel numeric cell) loses its ".0"."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"\s+", " ", str(value).replace(" ", " ").strip())


def title_case(s: str) -> str:
    s = s.title()
    s = re.sub(r"(?<=[a-z])'([A-Z])", lambda m: "'" + m.group(1).lower(), s)  # Ma'ruf: str.title() would capitalize the letter after the apostrophe
    return " ".join(w.upper() if ROMAN_TOKEN.match(w) else w for w in s.split(" "))


def clean_name(value, *, student: bool) -> tuple[str, list[tuple[str, str]]]:
    """Normal case, one space between words, stray characters removed.

    A student's name also loses academic degrees; an accompanying person keeps them.
    """
    notes: list[tuple[str, str]] = []
    s = re.sub(r"_x[0-9a-fA-F]{4}_", "", text(value))   # Excel's escape for an invisible control character
    s = s.replace("’", "'").replace("`", "'")
    unbracketed = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", s)
    if unbracketed != s:
        notes.append(("name_brackets", "text in brackets removed"))
        s = unbracketed
    kept = re.sub(r"[^\w\s'.,\-]|_", "", s)
    if kept != s:
        notes.append(("name_chars", "stray characters removed"))
        s = kept
    if student:
        stripped = LEADING_TITLE.sub("", TRAILING_DEGREES.sub("", s))
        if stripped != s:
            notes.append(("name_title_removed", "academic title removed from a student name"))
            s = stripped
    s = " ".join(s.split()).strip(" ,-")
    if re.search(r"\d", s):
        notes.append(("name_digits", "digits in a name"))
    if s and (s.isupper() or s.islower()):
        if "'" in s:  # most Indonesian names use it as a glottal stop (Ma'ruf), a few keep a capital (D'Angelo): a person checks
            notes.append(("name_apostrophe", "capital letters of a name with an apostrophe were converted: the letter after the apostrophe is lower case, check the spelling"))
        s = title_case(s)
    elif s:  # mixed case is kept as typed, except a word that starts in lower case: it prints on the certificate
        fixed = " ".join(w if w.lower() in NAME_PARTICLES or not w[:1].islower() else w[:1].upper() + w[1:] for w in s.split(" "))
        if fixed != s:
            notes.append(("name_word_case", "a word starting in lower case was capitalized"))
            s = fixed
    if student and s and len(s.split()) == 1:
        notes.append(("name_single_word", "name has a single word"))
    return s, notes


def clean_phone(value) -> tuple[str, list[tuple[str, str]]]:
    """Digits only in the 08... form; with several numbers the first is kept."""
    notes: list[tuple[str, str]] = []
    raw = value.strip() if isinstance(value, str) else text(value)  # the whitespace is kept so that two numbers separated by spaces can be told apart
    parts = [p for p in re.split(r"[/;,]|\sdan\s|\s{2,}", raw) if re.sub(r"\D", "", p)]
    if len(parts) > 1:
        notes.append(("phone_multiple", "several numbers, the first is kept"))
    digits = re.sub(r"\D", "", parts[0]) if parts else ""
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    elif digits.startswith("8"):
        digits = "0" + digits
    if digits and not 9 <= len(digits) <= 14:
        notes.append(("phone_length", f"unexpected phone length ({len(digits)} digits)"))
    return digits, notes


def clean_email(value) -> tuple[str, list[tuple[str, str]]]:
    notes: list[tuple[str, str]] = []
    parts = [p for p in re.split(r"[;,/]", text(value).lower().replace(" ", "")) if p]
    if len(parts) > 1:
        notes.append(("email_multiple", "several addresses, the first is kept"))
    s = (parts[0] if parts else "").strip(".,;")
    if not EMAIL.match(s) or len(s) > EMAIL_MAX or len(s.split("@", 1)[0]) > EMAIL_LOCAL_MAX or "." not in s.split("@", 1)[1]:
        notes.append(("invalid_email", "not a valid email address"))
    elif s.split("@", 1)[1] in EMAIL_DOMAIN_TYPOS:  # a clear typo in the domain is fixed by us (owner's rule, 2026-11-07) and listed
        local, domain = s.split("@", 1)
        s = f"{local}@{EMAIL_DOMAIN_TYPOS[domain]}"
        notes.append(("email_domain_fixed", f"domain @{domain} read as @{EMAIL_DOMAIN_TYPOS[domain]}"))
    return s, notes
