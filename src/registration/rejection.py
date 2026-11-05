"""File-level decisions: reject a workbook that cannot be read reliably, or flag one with many bad rows."""
import pandas as pd

from registration.review import Issue

REJECT_CODES = {
    "reject_unreadable": "the file cannot be opened (not an xlsx file, damaged or password protected)",
    "reject_no_table": "no table with a 'Nama Lengkap' header was found",
    "reject_no_rows": "the table has no student rows",
    "reject_missing_column": "a required column is missing",
    "reject_old_template": "the file uses the old template without the NISN column",
}


def structure_reasons(header_issues: list[Issue], cfg: dict, accept_old_template: bool = False) -> list[tuple[str, str, str]]:
    """Reasons to reject as (code, text, detail); empty when the structure is fine.

    `detail` lists the missing columns for reject_missing_column. `header_issues` come from rename_headers.
    """
    missing = {i.column for i in header_issues if i.code == "missing_column"}
    reasons = []
    if "NISN" in missing and not accept_old_template:
        reasons.append(("reject_old_template", REJECT_CODES["reject_old_template"], ""))
    gone = [c for c in cfg["required_columns"] if c in missing and c != "NISN"]  # a missing NISN is the old-template case above
    gone += [" or ".join(group) for group in cfg["required_any"] if all(c in missing for c in group)]
    if gone:
        detail = ", ".join(gone)
        reasons.append(("reject_missing_column", f"{REJECT_CODES['reject_missing_column']}: {detail}", detail))
    return reasons


def error_share(table: pd.DataFrame, issues: list[Issue]) -> float:
    """Share of student rows that have at least one error."""
    if table.empty:
        return 0.0
    bad = {i.source_row for i in issues if i.severity == "error" and i.source_row is not None}
    return len(bad & set(table["source_row"])) / len(table)
