"""Status tables: one line per file (status.csv, rejected.csv) and one per school (school_status.csv)."""
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

STATUS_COLUMNS = ["source_file", "status", "rows", "errors", "warnings", "error_share", "reasons", "processed_at"]
SCHOOL_COLUMNS = ["school", "files", "students", "error_rows", "state"]


def upsert_status(out_dir: Path, row: dict) -> None:
    """Replace the line of this file in status.csv (or add it) and refresh rejected.csv."""
    path = out_dir / "status.csv"
    table = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=STATUS_COLUMNS)
    table = table[table["source_file"] != row["source_file"]]
    table = pd.concat([table, pd.DataFrame([row], columns=STATUS_COLUMNS).astype(str)], ignore_index=True)
    table = table.sort_values("source_file", key=lambda s: s.str.lower())
    table.to_csv(path, index=False, encoding="utf-8")
    table[table["status"] == "rejected"][["source_file", "reasons", "processed_at"]].to_csv(out_dir / "rejected.csv", index=False, encoding="utf-8")


def uploaded_nisns(submit_dir: Path, slug: str) -> set[str]:
    """NISN values already in files marked as uploaded for this school."""
    log = submit_dir / "uploaded.csv"
    if not log.exists():
        return set()
    done = set(pd.read_csv(log, dtype=str)["file"])
    found: set[str] = set()
    for f in (submit_dir / slug).glob("*.xlsx"):
        if f.name in done:
            ws = openpyxl.load_workbook(f, read_only=True).worksheets[0]
            found |= {str(r[2]) for r in ws.iter_rows(min_row=2, values_only=True) if r[2]}
    return found


def mark_uploaded(submit_dir: Path, file_name: str) -> None:
    """Record that an upload file went to the website."""
    log = submit_dir / "uploaded.csv"
    table = pd.read_csv(log, dtype=str) if log.exists() else pd.DataFrame(columns=["file", "uploaded_at"])
    if file_name not in set(table["file"]):
        table.loc[len(table)] = [file_name, datetime.now().isoformat(timespec="seconds")]
    table.to_csv(log, index=False, encoding="utf-8")


def school_status(standardized: Path, submit_dir: Path, slugify, students: pd.DataFrame | None = None) -> pd.DataFrame:
    """One line per school: files, students, rows in error and a state (held, ready or uploaded).

    With the deduplicated table the state is the one `partition` acts on (a key given to a student without a NISN is no error)."""
    if students is not None and not students.empty:
        out = []
        for slug, group in students.groupby("school_slug"):
            errors = int((group["has_error"].astype(str) == "True").sum())
            pending = set(group["NISN"]) - uploaded_nisns(submit_dir, slug)
            out.append([group["Nama Sekolah"].iloc[0], group["source_file"].nunique(), len(group), errors, "held" if errors else ("uploaded" if not pending else "ready")])
        return pd.DataFrame(out, columns=SCHOOL_COLUMNS).sort_values("school", key=lambda s: s.str.lower())
    status_path = standardized / "status.csv"
    if not status_path.exists():
        return pd.DataFrame(columns=SCHOOL_COLUMNS)
    files = pd.read_csv(status_path, dtype=str).fillna("")
    files = files[files["status"].isin(["ok", "flagged"])]
    rows = []
    for _, f in files.iterrows():
        stem = Path(f["source_file"]).stem
        table = pd.read_csv(standardized / f"{stem}.csv", dtype=str)
        review = pd.read_csv(standardized / f"{stem}.review.csv", dtype=str)
        bad_rows = set(review[review["severity"] == "error"]["source_row"].dropna())
        table["error"] = table["source_row"].isin(bad_rows)
        table["file"] = f["source_file"]
        rows.append(table[["Nama Sekolah", "NISN", "error", "file"]])
    if not rows:
        return pd.DataFrame(columns=SCHOOL_COLUMNS)
    all_rows = pd.concat(rows, ignore_index=True)
    out = []
    for school, group in all_rows.groupby("Nama Sekolah"):
        errors = int(group["error"].sum())
        pending = set(group["NISN"]) - uploaded_nisns(submit_dir, slugify(school))
        state = "held" if errors else ("uploaded" if not pending else "ready")
        out.append([school, group["file"].nunique(), len(group), errors, state])
    return pd.DataFrame(out, columns=SCHOOL_COLUMNS).sort_values("school", key=lambda s: s.str.lower())
