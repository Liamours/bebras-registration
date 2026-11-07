import re

import pandas as pd

from registration.fields import blank, clean_email, clean_name, clean_phone, text, title_case
from registration.review import Issue

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
META = ["source_file", "source_row"]


def _norm_header(h) -> str:
    h = re.sub(r"\s*/\s*", "/", str(h).strip().lower().replace(".", ""))
    return re.sub(r"\s+", " ", h)


def _kelas(v) -> int | None:
    s = text(v).lower()
    if s in ROMAN:
        return ROMAN[s]
    m = re.match(r"(\d+)", s) or re.match(r"([ivx]+)\b", s)
    if not m:
        return None
    return int(m.group(1)) if m.group(1).isdigit() else ROMAN.get(m.group(1))


def rename_headers(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[Issue]]:
    """Map header spellings to the canonical column names; report columns that are missing."""
    lookup = {_norm_header(c): c for c in cfg["columns"]} | {_norm_header(k): v for k, v in cfg["header_aliases"].items()}
    out = df.rename(columns={c: lookup[_norm_header(c)] for c in df.columns if c not in META and _norm_header(c) in lookup})
    source = df["source_file"].iloc[0] if len(df) else ""
    issues = []
    for c in cfg["columns"]:
        if c not in out.columns:
            out[c] = None
            issues.append(Issue(source, None, c, "", "column missing in file", "error", "missing_column"))
    return out[cfg["columns"] + META], issues


def drop_template_examples(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[Issue]]:
    """Remove the two invented example students that ship with the template."""
    examples = {n.lower() for n in cfg["template_example_names"]}
    is_example = df["Nama Lengkap"].map(lambda v: not blank(v) and text(v).lower() in examples)
    issues = [Issue(r["source_file"], int(r["source_row"]), "Nama Lengkap", text(r["Nama Lengkap"]), "template example row dropped", "warning", "template_example")
              for _, r in df[is_example].iterrows()]
    return df[~is_example], issues


def normalize_values(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[Issue]]:
    """Normalize every value to the accepted lists; anything unclear becomes an issue instead of a guess."""
    nul = cfg["null_value"]
    kode_biro = re.compile(rf"^{re.escape(cfg['bureau_code'])}_\d{{5}}$")  # the only bureau key a sender may type is ours
    lo, hi = cfg["kelas_range"]
    maps = {col: {a: canon for canon, aliases in m.items() for a in [canon.lower(), *aliases]} for col, m in cfg["value_maps"].items()}
    by_kelas = [(name, a, b) for name, (a, b) in cfg["kategori_by_kelas"].items()]
    issues, rows = [], []

    for _, r in df.iterrows():
        file, line = r["source_file"], int(r["source_row"])
        cleaned = {"source_file": file, "source_row": line, "No": r["No"]}

        def flag(col, val, code, reason, severity="error"):
            issues.append(Issue(file, line, col, "" if blank(val) else text(val), reason, severity, code))

        def notes(col, val, found):
            for code, reason in found:
                flag(col, val, code, reason, "warning")

        # names
        for col, student in (("Nama Lengkap", True), ("Nama Pendamping", False)):
            if blank(r[col]):
                cleaned[col] = nul
                flag(col, r[col], "missing_name" if student else "missing_value", "missing", "error" if student else "warning")
            else:
                cleaned[col], found = clean_name(r[col], student=student)
                notes(col, r[col], found)
                if not cleaned[col]:
                    cleaned[col] = nul
                    flag(col, r[col], "missing_name" if student else "missing_value", "missing", "error" if student else "warning")

        # free text
        for col, fn in (("Nama Sekolah", text), ("Kota/Kabupaten", lambda v: title_case(text(v)) if text(v).isupper() or text(v).islower() else text(v))):
            cleaned[col] = nul if blank(r[col]) else fn(r[col])
            if cleaned[col] == nul:
                school = col == "Nama Sekolah"
                flag(col, r[col], "missing_school" if school else "missing_value", "missing", "error" if school else "warning")

        # NISN
        raw = r["NISN"]
        if blank(raw) or not text(raw).replace("-", "").strip():  # a typed "-" is the null symbol
            cleaned["NISN"] = nul
            flag("NISN", raw, "missing_nisn", "missing NISN (needs a bureau code)")
        else:
            s = text(raw).replace(" ", "").replace("-", "")
            if s and s[0] in "'’‘`":  # a text-prefix apostrophe typed into the cell, kept as a character by the form upload
                s = s.lstrip("'’‘`")
                flag("NISN", raw, "nisn_apostrophe", "leading apostrophe removed", "warning")
            if s.isdigit() and len(s) == cfg["nisn_length"] - 1:
                s = s.zfill(cfg["nisn_length"])
                flag("NISN", raw, "nisn_padded", "padded with a leading zero", "warning")
            elif not (s.isdigit() and len(s) == cfg["nisn_length"]) and not kode_biro.match(s.lower()):
                flag("NISN", raw, "nisn_format", f"not 10 digits or a bureau code (length {len(s)})")
            cleaned["NISN"] = s.lower() if kode_biro.match(s.lower()) else s

        # email and phone
        if blank(r["Email"]):
            cleaned["Email"] = nul
            flag("Email", r["Email"], "missing_value", "missing", "warning")
        else:
            cleaned["Email"], found = clean_email(r["Email"])
            notes("Email", r["Email"], found)
        if blank(r["No Kontak Pendamping"]):
            cleaned["No Kontak Pendamping"] = nul
            flag("No Kontak Pendamping", r["No Kontak Pendamping"], "missing_value", "missing", "warning")
        else:
            phone, found = clean_phone(r["No Kontak Pendamping"])
            cleaned["No Kontak Pendamping"] = phone or nul
            notes("No Kontak Pendamping", r["No Kontak Pendamping"], found)
            if not phone:
                flag("No Kontak Pendamping", r["No Kontak Pendamping"], "missing_value", "no digits", "warning")

        # value lists
        for col, m in maps.items():
            if blank(r[col]) and col in cfg["defaults"]:  # the bureau is the one uploading, so an empty bureau column is ours
                cleaned[col] = cfg["defaults"][col]
                flag(col, r[col], "default_filled", f"empty, filled with {cleaned[col]}", "warning")
                continue
            if blank(r[col]):
                cleaned[col] = nul
                if col != "Kategori":
                    flag(col, r[col], "missing_value", "missing", "warning")
                continue
            key = text(r[col]).lower()
            same_as_school = re.sub(r"[^a-z0-9]", "", key) == re.sub(r"[^a-z0-9]", "", text(r["Nama Sekolah"]).lower())
            if key not in m and col in cfg["defaults"] and same_as_school:  # the school name was typed in the bureau column: the bureau is ours
                cleaned[col] = cfg["defaults"][col]
                flag(col, r[col], "default_filled", f"held the school name, replaced with {cleaned[col]}", "warning")
                continue
            cleaned[col] = m.get(key, text(r[col]))
            if key not in m:
                flag(col, r[col], "unknown_value", f"'{text(r[col])}' is not an accepted value for {col}")

        # class and category
        kelas = None if blank(r["Kelas"]) else _kelas(r["Kelas"])
        if kelas is None or not lo <= kelas <= hi:
            cleaned["Kelas"] = nul if blank(r["Kelas"]) else text(r["Kelas"])
            flag("Kelas", r["Kelas"], "kelas_invalid", f"missing or not a class from {lo} to {hi}")
        else:
            cleaned["Kelas"] = kelas
            expected = next(n for n, a, b in by_kelas if a <= kelas <= b)
            if cleaned["Kategori"] == nul:
                cleaned["Kategori"] = expected
                flag("Kategori", r["Kategori"], "kategori_filled", f"missing, set to {expected} from Kelas {kelas}", "warning")
            elif cleaned["Kategori"] != expected:
                flag("Kategori", r["Kategori"], "kategori_mismatch", f"does not match Kelas {kelas} (expected {expected})")

        # session
        sesi = nul if blank(r["Sesi"]) else text(r["Sesi"]).upper()
        cleaned["Sesi"] = sesi
        if sesi == nul:
            flag("Sesi", r["Sesi"], "sesi_missing", "missing", "warning")
        elif sesi not in cfg["sesi_valid"]:
            flag("Sesi", r["Sesi"], "sesi_invalid", f"'{sesi}' is not a session letter")
        elif cleaned["Kategori"] in cfg["sesi_by_kategori"] and sesi not in cfg["sesi_by_kategori"][cleaned["Kategori"]]:
            flag("Sesi", r["Sesi"], "sesi_category", f"session {sesi} is not available for {cleaned['Kategori']}")

        rows.append(cleaned)
    return pd.DataFrame(rows, columns=cfg["columns"] + META), issues
