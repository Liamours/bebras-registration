import re

import pandas as pd

from registration.review import Issue

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
META = ["source_file", "source_row"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
KODE_BIRO = re.compile(r"^kode_biro_\d+$")


def _norm_header(h) -> str:
    h = re.sub(r"\s*/\s*", "/", str(h).strip().lower().replace(".", ""))
    return re.sub(r"\s+", " ", h)


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _text(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return re.sub(r"\s+", " ", str(v).strip())


def _name(v) -> str:
    s = _text(v)
    return s.title() if s.isupper() or s.islower() else s


def _kelas(v) -> int | None:
    s = _text(v).lower()
    if s in ROMAN:
        return ROMAN[s]
    m = re.match(r"(\d+)", s) or re.match(r"([ivx]+)\b", s)
    if not m:
        return None
    return int(m.group(1)) if m.group(1).isdigit() else ROMAN.get(m.group(1))


def _phone(v) -> str:
    d = re.sub(r"\D", "", _text(v))
    if d.startswith("62"):
        d = "0" + d[2:]
    elif d.startswith("8"):
        d = "0" + d
    return d


def rename_headers(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[Issue]]:
    """Map header spellings to the canonical column names; report columns that are missing."""
    lookup = {_norm_header(c): c for c in cfg["columns"]} | {_norm_header(k): v for k, v in cfg["header_aliases"].items()}
    out = df.rename(columns={c: lookup[_norm_header(c)] for c in df.columns if c not in META and _norm_header(c) in lookup})
    source = df["source_file"].iloc[0] if len(df) else ""
    issues = []
    for c in cfg["columns"]:
        if c not in out.columns:
            out[c] = None
            issues.append(Issue(source, None, c, "", "column missing in file", "error"))
    return out[cfg["columns"] + META], issues


def normalize_values(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[Issue]]:
    """Normalize every value to the accepted lists; anything unclear becomes an issue instead of a guess."""
    nul = cfg["null_value"]
    lo, hi = cfg["kelas_range"]
    maps = {col: {a: canon for canon, aliases in m.items() for a in [canon.lower(), *aliases]} for col, m in cfg["value_maps"].items()}
    by_kelas = [(name, a, b) for name, (a, b) in cfg["kategori_by_kelas"].items()]
    issues, rows = [], []

    for _, r in df.iterrows():
        file, line = r["source_file"], int(r["source_row"])
        new = {"source_file": file, "source_row": line, "No": r["No"]}

        def flag(col, val, reason, severity):
            issues.append(Issue(file, line, col, "" if _blank(val) else str(val), reason, severity))

        for col, text_fn in (("Nama Lengkap", _name), ("Nama Pendamping", _name), ("Kota/Kabupaten", _name), ("Nama Sekolah", _text)):
            new[col] = nul if _blank(r[col]) else text_fn(r[col])
            if new[col] == nul:
                flag(col, r[col], "missing", "error" if col in ("Nama Lengkap", "Nama Sekolah") else "warning")

        raw = r["NISN"]
        if _blank(raw):
            new["NISN"] = nul
            flag("NISN", raw, "missing NISN (needs kode_biro)", "error")
        else:
            s = _text(raw).replace(" ", "").replace("-", "")
            if s.isdigit() and len(s) == cfg["nisn_length"] - 1:
                s = s.zfill(cfg["nisn_length"])
                flag("NISN", raw, "padded with a leading zero", "warning")
            elif not KODE_BIRO.match(s) and not (s.isdigit() and len(s) == cfg["nisn_length"]):
                flag("NISN", raw, f"unexpected NISN format (length {len(s)})", "warning")
            new["NISN"] = s

        email = "" if _blank(r["Email"]) else _text(r["Email"]).lower()
        new["Email"] = email or nul
        if not email:
            flag("Email", r["Email"], "missing", "warning")
        elif not EMAIL.match(email):
            flag("Email", r["Email"], "invalid email", "warning")

        for col, m in maps.items():
            if _blank(r[col]):
                new[col] = nul
                if col != "Kategori":
                    flag(col, r[col], "missing", "warning")
                continue
            key = _text(r[col]).lower()
            new[col] = m.get(key, _text(r[col]))
            if key not in m:
                flag(col, r[col], "value not in the accepted list", "error")

        kelas = None if _blank(r["Kelas"]) else _kelas(r["Kelas"])
        if kelas is None or not lo <= kelas <= hi:
            new["Kelas"] = nul if _blank(r["Kelas"]) else _text(r["Kelas"])
            flag("Kelas", r["Kelas"], "missing or not a class from %d to %d" % (lo, hi), "error")
        else:
            new["Kelas"] = kelas
            expected = next(n for n, a, b in by_kelas if a <= kelas <= b)
            if new["Kategori"] == nul:
                new["Kategori"] = expected
                flag("Kategori", r["Kategori"], f"missing, set to {expected} from Kelas {kelas}", "warning")
            elif new["Kategori"] != expected:
                flag("Kategori", r["Kategori"], f"does not match Kelas {kelas} (expected {expected})", "error")

        sesi = nul if _blank(r["Sesi"]) else _text(r["Sesi"]).upper()
        new["Sesi"] = sesi
        if sesi == nul:
            flag("Sesi", r["Sesi"], "missing", "warning")
        elif sesi not in cfg["sesi_valid"]:
            flag("Sesi", r["Sesi"], "not a valid session letter", "warning")

        phone = _phone(r["No Kontak Pendamping"]) if not _blank(r["No Kontak Pendamping"]) else ""
        new["No Kontak Pendamping"] = phone or nul
        if not phone:
            flag("No Kontak Pendamping", r["No Kontak Pendamping"], "missing", "warning")
        elif not 9 <= len(phone) <= 14:
            flag("No Kontak Pendamping", r["No Kontak Pendamping"], "unexpected phone length", "warning")

        rows.append(new)
    return pd.DataFrame(rows, columns=cfg["columns"] + META), issues
