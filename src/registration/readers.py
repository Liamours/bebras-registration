from pathlib import Path

import openpyxl
import pandas as pd

HEADER_MARKER = "nama lengkap"
BLOCK_MARKER = "keterangan"


def other_sheets(path: Path) -> list[str]:
    """Titles of every worksheet after the first, hidden ones included: only the first is read, the others need a person."""
    return [s.title for s in openpyxl.load_workbook(path, read_only=True).worksheets[1:]]


def read_workbook(path: Path) -> pd.DataFrame:
    """Return the student rows of a registration workbook with their source row numbers.

    The table starts at the header row (the one holding "Nama Lengkap") and stops at the
    instruction block (first cell starts with "Keterangan"). Empty rows are skipped.
    """
    sheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header_at = next(
        (i for i, row in enumerate(rows) if any(str(c or "").strip().lower() == HEADER_MARKER for c in row)), None
    )
    if header_at is None:
        raise ValueError(f"{path.name}: no header row containing 'Nama Lengkap'")
    header = [str(c).strip() if c is not None else "" for c in rows[header_at]]
    records = []
    in_block = False
    for number, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
        if str(row[0] or "").strip().lower().startswith(BLOCK_MARKER):
            in_block = True
        if in_block:  # a sender may paste the students below the block under a repeated header: resume after it
            in_block = not any(str(c or "").strip().lower() == HEADER_MARKER for c in row)
            continue
        if all(c in (None, "") for c in row):
            continue
        record = {h: v for h, v in zip(header, row) if h}
        record["source_file"] = path.name
        record["source_row"] = number
        records.append(record)
    return pd.DataFrame(records)
