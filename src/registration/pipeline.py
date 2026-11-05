"""Standardize one workbook: read, check the structure, fix what is certain, report the rest."""
from datetime import datetime
from pathlib import Path

import pandas as pd

from registration.overrides import apply_overrides
from registration.readers import read_workbook
from registration.rejection import REJECT_CODES, error_share, structure_reasons
from registration.replies import build_reply
from registration.review import Issue, write_report
from registration.standardize import drop_template_examples, normalize_values, rename_headers
from registration.status import upsert_status


def _finish(path: Path, out_dir: Path, replies: dict, *, status: str, rows: int = 0, issues=None, share: float = 0.0,
            rejected=None, school: str = "") -> dict:
    """Write the reply draft, record the status line and return it."""
    issues = issues or []
    errors = sum(i.severity == "error" for i in issues)
    reply_dir = out_dir / "replies"
    reply_dir.mkdir(exist_ok=True)
    reply = build_reply(replies, issues, school, [(c, d) for c, _, d in rejected] if rejected else None)
    reply_path = reply_dir / f"{path.stem}.txt"
    if reply:
        reply_path.write_text(reply, encoding="utf-8")
    elif reply_path.exists():
        reply_path.unlink()
    row = {
        "source_file": path.name, "status": status, "rows": rows, "errors": errors, "warnings": len(issues) - errors,
        "error_share": round(share, 3), "reasons": "; ".join(t for _, t, _ in rejected) if rejected else "",
        "processed_at": datetime.now().isoformat(),  # full precision: a file saved in the same second must still count as older
    }
    upsert_status(out_dir, row)
    return row


def _reject(path: Path, out_dir: Path, replies: dict, reasons) -> dict:
    for suffix in (".csv", ".review.csv"):
        (out_dir / f"{path.stem}{suffix}").unlink(missing_ok=True)
    return _finish(path, out_dir, replies, status="rejected", rejected=reasons)


def process_file(path: Path, cfg: dict, replies: dict, out_dir: Path, accept_old_template: bool = False) -> dict:
    """Return the status line of the file: status is ok, flagged (many rows in error) or rejected."""
    try:
        raw = read_workbook(path)
    except ValueError:
        return _reject(path, out_dir, replies, [("reject_no_table", REJECT_CODES["reject_no_table"], "")])
    except Exception:  # not an xlsx, damaged or password protected: openpyxl raises several different errors
        return _reject(path, out_dir, replies, [("reject_unreadable", REJECT_CODES["reject_unreadable"], "")])
    if raw.empty:
        return _reject(path, out_dir, replies, [("reject_no_rows", REJECT_CODES["reject_no_rows"], "")])

    df, header_issues = rename_headers(raw, cfg)
    reasons = structure_reasons(header_issues, cfg, accept_old_template)
    if reasons:
        return _reject(path, out_dir, replies, reasons)

    df, override_issues = apply_overrides(df, cfg["paths"]["overrides"], path.name)
    df, example_issues = drop_template_examples(df, cfg)
    if df.empty:
        return _reject(path, out_dir, replies, [("reject_no_rows", REJECT_CODES["reject_no_rows"], "")])
    table, value_issues = normalize_values(df, cfg)

    issues: list[Issue] = header_issues + override_issues + example_issues + value_issues
    table.to_csv(out_dir / f"{path.stem}.csv", index=False, encoding="utf-8")
    write_report(issues, out_dir / f"{path.stem}.review.csv")
    share = error_share(table, issues)
    schools = [s for s in table["Nama Sekolah"].unique() if s != cfg["null_value"]]
    return _finish(path, out_dir, replies, status="flagged" if share > cfg["flag_error_share"] else "ok", rows=len(table),
                   issues=issues, share=share, school=schools[0] if len(schools) == 1 else "")


def is_done(out_dir: Path, path: Path) -> bool:
    """True when the file was processed after it last changed."""
    status_path = out_dir / "status.csv"
    if not status_path.exists():
        return False
    table = pd.read_csv(status_path, dtype=str).fillna("")
    row = table[table["source_file"] == path.name]
    return not row.empty and datetime.fromisoformat(row.iloc[0]["processed_at"]).timestamp() > path.stat().st_mtime
