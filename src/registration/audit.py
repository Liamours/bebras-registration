"""Audit of our own work: the student table of the website against the senders' original cells.

A sender's typo passes. Everything that differs from the sender's cell must be a format change, a listed override or a
rule that keeps the meaning, and every value on the site must be sane. Anything else is an error that is ours.
"""
import csv
import re
from pathlib import Path

import pandas as pd

from registration.fields import EMAIL, EMAIL_DOMAIN_TYPOS, text
from registration.readers import read_workbook
from registration.standardize import rename_headers

ISSUE_COLUMNS = ["check", "severity", "ref", "field", "raw", "site", "why"]
SITE_COLUMNS = {  # canonical column of the upload file -> column of the exported table
    "Nama Lengkap": "Nama Lengkap", "Gender": "Gender", "Email": "Email", "Kelas": "Kelas", "Kategori": "Kategori", "Sesi": "Sesi",
    "Bahasa": "Bahasa", "Jenjang Sekolah": "Jenjang", "Nama Sekolah": "Sekolah", "Kota/Kabupaten": "Kota/Kabupaten",
    "Nama Pendamping": "Pendamping", "No Kontak Pendamping": "No Kontak Pendamping",
}
JENJANG_SITE = {"Preschool", "SD", "MTI", "SMP", "MTs", "SMA", "MA", "SMK", "MAK"}  # the site's own list
JENJANG_KELAS = {"Preschool": (0, 0), "SD": (1, 6), "MTI": (1, 6), "SMP": (7, 9), "MTs": (7, 9), "SMA": (10, 12), "SMK": (10, 12), "MA": (10, 12), "MAK": (10, 12)}
REGIONS = {"Kota Bandung", "Kabupaten Bandung", "Kabupaten Bandung Barat", "Kota Cimahi"}
SCHOOL_ABBREVIATIONS = {"negeri", "swasta", "smpn", "sman", "smkn", "sdit", "smpit", "smait", "mtsn", "madrasah", "sekolah", "dasar", "menengah", "pertama", "atas", "kejuruan"}  # words the school-name rule rewrites
PARTICLES = {"bin", "binti", "bte", "van", "de", "der", "di", "da", "von", "ibn", "al", "el"}


def letters(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str("" if pd.isna(value) else value).casefold())


def read_site(path: Path) -> pd.DataFrame:
    """The table exported by the site: the header row is the one holding Username."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    at = next(i for i, r in enumerate(rows) if "Username" in r)
    header = [re.sub(r"\s+", " ", c).replace("Kota/ ", "Kota/") for c in rows[at]]
    table = pd.DataFrame([r + [""] * (len(header) - len(r)) for r in rows[at + 1 :] if any(r)], columns=header)
    return table.reset_index(drop=True)


def first_phone(value: str) -> str:
    part = re.split(r"[/;,]|\sdan\s|\s{2,}", re.sub(r"\.0$", "", str(value).strip()))[0]
    digits = re.sub(r"\D", "", part)
    return "0" + digits[2:] if digits.startswith("62") else ("0" + digits if digits.startswith("8") else digits)


def explain(col: str, raw: str, site: str) -> str | None:
    """The name of the rule that explains why the site value differs from the sender's cell, or None."""
    if col == "Email":  # dots and underscores count: a mailbox is exact apart from case and the first of several addresses
        a, b = re.split(r"[;,/]", raw.replace(" ", "").casefold())[0].strip(".,;"), site.strip().casefold()
        local, _, domain = a.partition("@")
        if a == b:
            return "format"
        return "domain typo fixed" if domain in EMAIL_DOMAIN_TYPOS and f"{local}@{EMAIL_DOMAIN_TYPOS[domain]}" == b else None
    if letters(raw) == letters(site):
        return "format"
    if col == "Kelas":
        m = re.match(r"\d+", raw.strip())
        return "number format" if m and m.group() == site.strip() else None
    if col == "Gender":
        return "vocabulary" if letters(raw)[:1] == "l" and site in ("L", "Laki-laki") or letters(raw)[:1] == "p" and site in ("P", "Perempuan") else None
    if col == "Sesi":
        m = re.match(r"([A-Za-z]\d?)", raw.strip())
        return "label read as letter" if m and m.group(1).upper() == site.upper() else None
    if col == "No Kontak Pendamping":
        return "phone format" if first_phone(raw) == re.sub(r"\D", "", site) else None
    if col == "Jenjang Sekolah":
        return "site vocabulary" if letters(raw) in ("mi", "mti") and site == "MTI" else None
    if col == "Kota/Kabupaten":
        spelled = re.sub(r"\bkab\.?\s", "kabupaten ", raw.strip().casefold())
        if letters(spelled) == letters(site):
            return "region spelling"
        return "region of the school" if letters(raw) == "bandung" and site in REGIONS else None
    if col == "Nama Sekolah":
        words = [w for w in re.findall(r"[a-z]{4,}", raw.casefold()) if w not in SCHOOL_ABBREVIATIONS]
        same_numbers = re.findall(r"\d+", raw) == re.findall(r"\d+", site)
        return "school name rule" if same_numbers and all(w in site.casefold() for w in words) else None
    if col == "Kategori":
        return "filled from Kelas" if not raw.strip() else None
    if col == "Bahasa":
        return "vocabulary" if letters(site) in letters(raw) or (letters(raw) in ("english", "bingg", "binggris") and site == "Inggris") else None
    return None


def differ_from_files(s: pd.Series, w: pd.Series) -> list[tuple[str, str]]:
    """Columns where the site differs from what our own files hold, stricter than the sender comparison: case counts for names and schools."""
    found = []
    alnum = lambda v: re.sub(r"[^A-Za-z0-9]", "", str(v))
    for col in ("Nama Lengkap", "Nama Sekolah"):  # the site drops punctuation, never case
        if alnum(s[col]) != alnum(w[SITE_COLUMNS[col]]):
            found.append((col, "case or letters differ from our file"))
    for col in ("Kota/Kabupaten", "Kategori", "Sesi", "Bahasa", "Jenjang Sekolah"):
        if str(s[col]).strip() != str(w[SITE_COLUMNS[col]]).strip():
            found.append((col, "differs from our file"))
    if str(s["Email"]).strip().casefold().replace("-", "") != str(w["Email"]).strip().casefold().replace("-", "") and not (s["Email"] in ("", "-") and str(w["Email"]) in ("", "-")):
        found.append(("Email", "differs from our file"))
    if re.sub(r"\D", "", str(s["No Kontak Pendamping"])).lstrip("0") != re.sub(r"\D", "", str(w["No Kontak Pendamping"])).lstrip("0"):
        found.append(("No Kontak Pendamping", "differs from our file"))
    return found


def load_raw(raw_dir: Path, cfg: dict) -> pd.DataFrame:
    frames = []
    for f in sorted(raw_dir.rglob("*.xlsx")):
        if f.name.startswith("~$"):
            continue
        df, _ = rename_headers(read_workbook(f), cfg)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    raw["source_row"] = raw["source_row"].astype(int)
    return raw


def audit(cfg: dict, site_path: Path) -> pd.DataFrame:
    issues: list[list] = []

    def add(check, severity, ref, field="", raw="", site="", why=""):
        issues.append([check, severity, ref, field, raw, site, why])

    raw = load_raw(cfg["paths"]["raw"], cfg)
    std = pd.read_csv(cfg["paths"]["deduplicated"] / "students.csv", dtype=str).fillna("")
    std["source_row"] = std["source_row"].astype(int)
    site = read_site(site_path)
    ov = pd.read_csv(cfg["paths"]["overrides"], dtype=str).fillna("") if cfg["paths"]["overrides"].exists() else pd.DataFrame(columns=["source_file", "row", "column", "new_value", "reason", "student"])
    overrides = {(r["source_file"], int(r["row"]), r["column"]): r["new_value"] for _, r in ov.iterrows() if r["row"].isdigit()}
    dropped = {(f, r) for (f, r, c), v in overrides.items() if v == "__drop__"}
    examples = set(cfg["template_example_names"])
    student_columns = [c for c in cfg["columns"] if c != "No"]

    # 1 coverage: every sender row is on the site or has a reason to be absent
    std_refs = {(f, r): i for i, (f, r) in enumerate(zip(std["source_file"], std["source_row"]))}
    for _, r in raw.iterrows():
        ref = (r["source_file"], r["source_row"])
        filled = [c for c in student_columns if str(r[c]).strip() not in ("", "None", "nan")]
        if not filled or ref in std_refs:
            continue
        name = str(r["Nama Lengkap"]).strip().casefold()
        if name in examples or ref in dropped:
            continue
        add("raw_row_lost", "error", f"{ref[0][:40]}:{ref[1]}", "row", why="a row with data is neither on the site nor dropped for a stated reason")

    site["_key"] = [(letters(n), letters(s)) for n, s in zip(site["Nama Lengkap"], site["Sekolah"])]
    std["_key"] = [(letters(n), letters(s)) for n, s in zip(std["Nama Lengkap"], std["Nama Sekolah"])]
    site_index = {k: i for i, k in enumerate(site["_key"])}
    std_counts, site_counts = std["_key"].value_counts(), site["_key"].value_counts()
    for k, n in site_counts.items():
        if n > std_counts.get(k, 0) and k in set(std["_key"]):
            add("repeated_on_site", "error", "/".join(k), why="the same name and school more often on the site than in the files")
    for u in site["Username"][site["Username"].duplicated()]:
        add("repeated_on_site", "error", u, "Username", why="a username twice")
    std_keys = set(std["_key"])
    for k in site["_key"]:
        if k not in std_keys:
            add("site_extra", "error", "/".join(k), why="a student on the site that no sender row produced")

    # 2 each cell: sender -> site
    raw_by_ref = {(r["source_file"], r["source_row"]): r for _, r in raw.iterrows()}
    for _, s in std.iterrows():
        ref = (s["source_file"], s["source_row"])
        label = f"{ref[0][:40]}:{ref[1]}"
        if s["_key"] not in site_index:
            add("held" if s["has_error"] == "True" else "missing_on_site", "warning" if s["has_error"] == "True" else "error", label, why="held with an error" if s["has_error"] == "True" else "a student of the files is not on the site")
            continue
        if std_counts[s["_key"]] > 1:  # two students with one name and school: the match by name cannot tell them apart
            add("homonym", "warning", label, why="two students with the same name and school, compared by hand")
            continue
        w = site.iloc[site_index[s["_key"]]]
        r = raw_by_ref[ref]
        for col, why in differ_from_files(s, w):
            add("site_differs_from_files", "error", label, col, s[col], str(w[SITE_COLUMNS[col]]), why)
        for col, scol in SITE_COLUMNS.items():
            a, b = text(r[col]) if str(r[col]) not in ("None", "nan") else "", str(w[scol])
            if b == "-":
                b = ""
            o = overrides.get((ref[0], ref[1], col))
            if o is not None:
                if letters(o) != letters(b) and not explain(col, o, b):
                    add("override_not_on_site", "error", label, col, o, b, "the site does not hold the value of the override")
                continue
            if explain(col, a, b) is None:
                add("unexplained_change", "error", label, col, a, b, "the site value is neither the sender's nor a listed rule or override")
        nisn_raw = re.sub(r"\.0+$", "", text(r["NISN"]).lstrip("'"))
        nisn = s["NISN"]
        if nisn_raw != nisn and (ref[0], ref[1], "NISN") not in overrides and nisn_raw.zfill(cfg["nisn_length"]) != nisn and not nisn.startswith(cfg["bureau_code"]):
            add("unexplained_change", "error", label, "NISN", nisn_raw, nisn, "the NISN differs from the sender's without a padded zero, an override or a bureau code")

    # 2b every uploaded file against the site: a later file replaces the earlier rows of the same NISN
    uploaded = cfg["paths"]["submit_ready"] / "uploaded.csv"
    if uploaded.exists() and uploaded.stat().st_size > 20:
        sent = set(pd.read_csv(uploaded, dtype=str)["file"])
        latest: dict[tuple[str, str], tuple[str, pd.Series]] = {}
        for f in sorted(cfg["paths"]["submit_ready"].glob("*/*.xlsx")):
            if f.name in sent:
                for _, u in pd.read_excel(f, dtype=str).fillna("").iterrows():
                    latest[(f.parent.name, u["NISN"])] = (f.name, u)
        for (folder, nisn), (fname, u) in latest.items():
            k = (letters(u["Nama Lengkap"]), letters(u["Nama Sekolah"]))
            if k not in site_index:
                add("upload_file_not_on_site", "error", f"{fname}", "student", why="a student of an uploaded file is not on the site")
                continue
            w = site.iloc[site_index[k]]
            for col in ("Sesi", "Kelas", "Kategori", "Bahasa", "Jenjang Sekolah", "Gender", "Email"):  # what the site cannot edit after the upload
                a, b = str(u[col]).replace(".0", "") if col == "Kelas" else str(u[col]), str(w[SITE_COLUMNS[col]])
                same = (a.casefold() == b.casefold()) or (col == "Gender" and a[:1].upper() == b[:1].upper()) or (col == "Email" and a in ("", "-") and b in ("", "-"))
                if not same:
                    add("upload_file_not_on_site", "error", f"{fname}", col, a, b, "the uploaded file and the site disagree on a value that cannot be edited on the site")

    # 3 sanity of every value on the site: a sender's typo passes, an absurd value is resolved
    nisn_seen: set[str] = set()
    for _, s in std.iterrows():
        if s["NISN"] in nisn_seen:
            add("absurd", "error", s["NISN"], "NISN", site=s["NISN"], why="a NISN repeated")
        nisn_seen.add(s["NISN"])
        if not (re.fullmatch(r"\d{%d}" % cfg["nisn_length"], s["NISN"]) or re.fullmatch(rf"{cfg['bureau_code']}_\d{{5}}", s["NISN"])):
            add("absurd", "error", s["NISN"], "NISN", site=s["NISN"], why="neither 10 digits nor a bureau code")
    lo, hi = cfg["kelas_range"]
    bounds = {k: tuple(v) for k, v in cfg["kategori_by_kelas"].items()}
    for _, w in site.iterrows():
        who = w["Username"]
        name = str(w["Nama Lengkap"])
        problems = []
        if re.search(r"\d|@", name):
            problems.append(("Nama Lengkap", "digits or an @ in a name"))
        if len(letters(name)) < 3:
            problems.append(("Nama Lengkap", "fewer than 3 letters"))
        if re.search(r"\s{2,}|^[\s.,'-]|[\s.,'-]$", name):
            problems.append(("Nama Lengkap", "spacing or punctuation at the edge"))
        if any(x[:1].islower() and x.lower() not in PARTICLES for x in name.split()):
            problems.append(("Nama Lengkap", "a word starting in lower case prints on the certificate"))
        if re.search(r"'[A-Z]", name):
            problems.append(("Nama Lengkap", "capital after an apostrophe"))
        kelas = str(w["Kelas"]).strip()
        if not kelas.isdigit() or not lo <= int(kelas) <= hi:
            problems.append(("Kelas", "not a class from the template"))
        else:
            kat = next((k for k, (a, b) in bounds.items() if a <= int(kelas) <= b), None)
            if w["Kategori"] != kat:
                problems.append(("Kategori", f"does not fit Kelas {kelas}"))
            span = JENJANG_KELAS.get(w["Jenjang"])
            if w["Jenjang"] not in JENJANG_SITE or (span and not span[0] <= int(kelas) <= span[1]):
                problems.append(("Jenjang", "not on the site's list or not fitting Kelas"))
        if w["Sesi"] not in cfg["sesi_by_kategori"].get(w["Kategori"], []):
            problems.append(("Sesi", "not available for the category"))
        if w["Gender"] not in ("L", "P", "Laki-laki", "Perempuan"):
            problems.append(("Gender", "outside the vocabulary"))
        email = str(w["Email"]).strip()
        if email and email != "-" and not (EMAIL.match(email) and len(email) <= 254):
            problems.append(("Email", "not a valid address"))
        phone = re.sub(r"\D", "", str(w["No Kontak Pendamping"]))
        if phone and not (9 <= len(phone) <= 14):
            problems.append(("No Kontak Pendamping", "length outside 9 to 14 digits"))
        if not str(w["Sekolah"]).strip() or not str(w["Kota/Kabupaten"]).strip():
            problems.append(("Sekolah", "school or city empty"))
        for field, why in problems:
            add("absurd", "error", who, field, site=str(w.get(field, w.get("Nama Lengkap", ""))), why=why)

    # 4 our own records
    for i, o in ov.iterrows():
        if not o["reason"].strip() or not o["student"].strip():
            add("record", "error", f"overrides line {i + 2}", why="an override without a reason or a student")
    uploaded = cfg["paths"]["submit_ready"] / "uploaded.csv"
    log = cfg["paths"]["audit"] / "uploads.csv"
    if uploaded.exists() and log.exists():
        done = set(pd.read_csv(uploaded, dtype=str)["file"]) if uploaded.stat().st_size > 20 else set()
        logged = pd.read_csv(log, dtype=str).fillna("")
        verified = set(logged[logged["result"] == "verified"]["file"])
        for f in sorted(done - verified):
            add("record", "error", f, why="an uploaded file without a verified line in the upload log")
    if len(site) != len(std[std["_key"].isin(site_index)]):
        add("count", "error", "site", why=f"{len(site)} students on the site, {len(std[std['_key'].isin(site_index)])} matched in the files")
    return pd.DataFrame(issues, columns=ISSUE_COLUMNS)
