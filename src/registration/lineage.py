"""The path of each student's values: the sender's cell, the cell of the file we uploaded, our final value and the value on the site.

One line per student and field where any two of them differ, with the reason of each step. The final checks follow this table,
not only the sender's Excel: a value may have been changed by a rule, an override, a later upload or an edit on the site.
"""
import re
from pathlib import Path

import pandas as pd

from registration.audit import SITE_COLUMNS, explain, letters, load_raw, read_site
from registration.fields import text

LINEAGE_COLUMNS = ["school", "source_file", "source_row", "field", "raw", "uploaded", "final", "site", "raw_to_final", "uploaded_to_site", "uploaded_in", "username"]
FIELDS = {**SITE_COLUMNS, "NISN": "NISN"}


def uploads(cfg: dict) -> dict[tuple[str, str], tuple[str, str, pd.Series]]:
    """For each (school folder, NISN) the newest uploaded file that holds it: (file name, time, the row). A later file replaces an earlier one."""
    log = cfg["paths"]["submit_ready"] / "uploaded.csv"
    if not log.exists() or log.stat().st_size < 20:
        return {}
    sent = pd.read_csv(log, dtype=str).set_index("file")["uploaded_at"].to_dict()
    latest = {}
    for f in sorted(cfg["paths"]["submit_ready"].glob("*/*.xlsx")):
        if f.name in sent:
            for _, u in pd.read_excel(f, dtype=str).fillna("").iterrows():
                latest[(f.parent.name, u["NISN"])] = (f.name, sent[f.name], u)
    return latest


def lineage(cfg: dict, site_path: Path | None = None) -> pd.DataFrame:
    raw = load_raw(cfg["paths"]["raw"], cfg).set_index(["source_file", "source_row"])
    std = pd.read_csv(cfg["paths"]["deduplicated"] / "students.csv", dtype=str).fillna("")
    std["source_row"] = std["source_row"].astype(int)
    ov = pd.read_csv(cfg["paths"]["overrides"], dtype=str, keep_default_na=False) if cfg["paths"]["overrides"].exists() else pd.DataFrame(columns=["source_file", "row", "column", "new_value", "reason"])
    overrides = {(r["source_file"], int(r["row"]), r["column"]): r["reason"] for _, r in ov.iterrows() if r["row"].isdigit()}
    sent = uploads(cfg)
    site = {}
    if site_path is not None:
        table = read_site(site_path)
        for _, w in table.iterrows():
            site.setdefault((letters(w["Nama Lengkap"]), letters(w["Sekolah"])), w)
    rows = []
    for _, s in std.iterrows():
        ref = (s["source_file"], s["source_row"])
        r = raw.loc[ref]
        u_file, u_time, u = sent.get((s["school_slug"], s["NISN"]), ("", "", None))
        w = site.get((letters(s["Nama Lengkap"]), letters(s["Nama Sekolah"])))
        for col, scol in FIELDS.items():
            a = text(r[col]) if str(r[col]) not in ("None", "nan") else ""
            f = s[col]
            up = "" if u is None else str(u[col]).replace(".0", "") if col == "Kelas" else ("" if u is None else str(u[col]))
            si = "" if w is None or scol not in w.index else str(w[scol])
            if si == "-":
                si = ""
            raw_to_final = ""
            if a.strip() != ("" if f.strip() == "-" else f.strip()):
                if ref[0] and (ref[0], ref[1], col) in overrides:
                    raw_to_final = f"override: {overrides[(ref[0], ref[1], col)][:80]}"
                elif col == "NISN":
                    raw_to_final = "padded zero" if re.sub(r"\.0+$", "", a.lstrip("'")).zfill(10) == f else ("bureau code" if f.startswith(cfg["bureau_code"]) else "unexplained")
                else:
                    raw_to_final = "rule: " + (explain(col, a, f) or "unexplained")
            uploaded_to_site = ""
            if w is not None and u is not None and col != "NISN" and letters(up) != letters(si) and not explain(col, up, si):
                uploaded_to_site = "site edit or stale file"
            site_vs_final = "" if w is None or col == "NISN" or letters(f) == letters(si) or explain(col, f, si) else "site differs from final"
            if raw_to_final or uploaded_to_site or site_vs_final:
                rows.append([s["Nama Sekolah"], ref[0], ref[1], col, a, up, f, si, raw_to_final, uploaded_to_site or site_vs_final, f"{u_file} at {u_time}" if u_file else "", "" if w is None else str(w["Username"])])
    return pd.DataFrame(rows, columns=LINEAGE_COLUMNS)
