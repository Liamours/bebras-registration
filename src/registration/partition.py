"""Split the checked students into one upload file per school, in the website's upload format."""
import re
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import PatternFill

from registration.schools import slugify

TEXT_COLUMNS = ("NISN", "No Kontak Pendamping")
REPORT_COLUMNS = ["school", "slug", "state", "rows", "file", "reason"]


def upload_header(cfg: dict) -> list[str]:
    """Header of the upload file: the official format file when present, otherwise the configured columns."""
    path = cfg["paths"]["upload_format"]
    if path.exists():
        row = next(openpyxl.load_workbook(path, read_only=True).worksheets[0].iter_rows(min_row=1, max_row=1, values_only=True))
        header = [str(c) for c in row if c not in (None, "")]
        if [h.strip() for h in header] != cfg["columns"]:
            raise ValueError(f"{path.name} has different columns than the configuration")
        return header
    return list(cfg["columns"])


def write_upload(path: Path, rows: pd.DataFrame, header: list[str], null: str) -> None:
    """One workbook, header in row 1, students from row 2; NISN and phone stored as text so leading zeros stay."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(header)
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="D0CECE")
    columns = [h.strip() for h in header]
    for n, (_, r) in enumerate(rows.iterrows(), 1):
        values = []
        for c in columns:
            v = n if c == "No" else r[c]
            values.append(None if (isinstance(v, str) and v == null) else (int(v) if c in ("Kelas", "No") else str(v)))
        ws.append(values)
        for c, cell in zip(columns, ws[ws.max_row]):
            if c in TEXT_COLUMNS:
                cell.number_format = "@"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def earlier_nisns(folder: Path) -> set[str]:
    found: set[str] = set()
    for f in folder.glob("*.xlsx"):
        ws = openpyxl.load_workbook(f, read_only=True).worksheets[0]
        found |= {str(r[2]) for r in ws.iter_rows(min_row=2, values_only=True) if r[2]}
    return found


def school_folder(out_dir: Path, slug: str) -> Path:
    """The existing upload folder of a school (compared without underscores), else the folder of its slug."""
    if out_dir.exists():
        for p in out_dir.iterdir():
            if p.is_dir() and p.name.replace("_", "") == slug.replace("_", ""):
                return p
    return out_dir / slug


def load_checked(input_dir: Path, ignore_codes: set[str] = frozenset()) -> pd.DataFrame:
    """Every processed student row with a flag for rows that still have an error; the deduplicated folder holds one ready table."""
    if (input_dir / "students.csv").exists():
        table = pd.read_csv(input_dir / "students.csv", dtype=str).fillna("")
        table["has_error"] = table["has_error"] == "True"
        return table
    status_path = input_dir / "status.csv"
    if not status_path.exists():
        return pd.DataFrame()
    parts = []
    for _, f in pd.read_csv(status_path, dtype=str).iterrows():
        if f["status"] == "rejected":
            continue
        stem = Path(f["source_file"]).stem
        table = pd.read_csv(input_dir / f"{stem}.csv", dtype=str)
        review = pd.read_csv(input_dir / f"{stem}.review.csv", dtype=str)
        bad = set(review[(review["severity"] == "error") & ~review["code"].isin(ignore_codes)]["source_row"].dropna())
        table["has_error"] = table["source_row"].isin(bad)
        parts.append(table)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def partition(cfg: dict, kategori: list[str] | None = None, stamp: str | None = None) -> pd.DataFrame:
    """Write the upload files and return the report (also saved as partition_report.csv)."""
    input_dir = cfg["paths"][cfg["partition_input"]]
    out_dir = cfg["paths"]["submit_ready"]
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M")
    null = cfg["null_value"]
    data = load_checked(input_dir)
    report = []
    if data.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    header = upload_header(cfg)
    repeated = set(data[data.duplicated("NISN", keep=False)]["NISN"])
    if "school_slug" not in data.columns:
        data["school_slug"] = data["Nama Sekolah"].map(slugify)
    for slug, group in data.groupby("school_slug", sort=True):  # the slug comes from the school master, so an upload folder is never renamed
        school = group["Nama Sekolah"].iloc[0]
        folder = school_folder(out_dir, slug)
        if school == null:
            report.append([school, slug, "held", len(group), "", "school name missing"])
            continue
        n_bad = int(group["has_error"].sum())
        n_dup = int(group["NISN"].isin(repeated).sum())
        if n_bad or n_dup:
            why = "; ".join(p for p in (f"{n_bad} rows with errors" if n_bad else "", f"{n_dup} rows with a repeated NISN" if n_dup else "") if p)
            report.append([school, slug, "held", len(group), "", why])
            continue
        rows = group
        if kategori:
            rows = rows[rows["Kategori"].isin(kategori)]
        rows = rows[~rows["NISN"].isin(earlier_nisns(folder))] if folder.exists() else rows
        rows = rows.sort_values(["Kategori", "Nama Lengkap"]).reset_index(drop=True)
        if rows.empty:
            report.append([school, slug, "nothing_new", 0, "", "no student without an earlier upload file"])
            continue
        path = folder / f"{folder.name}-{stamp}.xlsx"
        write_upload(path, rows, header, null)
        report.append([school, slug, "written", len(rows), path.name, ""])
    out = pd.DataFrame(report, columns=REPORT_COLUMNS)
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "partition_report.csv", index=False, encoding="utf-8")
    return out
