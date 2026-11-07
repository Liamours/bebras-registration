import re
from pathlib import Path

import pandas as pd

from registration.review import Issue

DROP = "__drop__"
NO_NAME = "(no name)"


def letters(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value if pd.notna(value) else "").casefold())


def _apply(df: pd.DataFrame, mask: pd.Series, o: pd.Series) -> pd.DataFrame:
    if o["new_value"] == DROP:
        return df[~mask]
    df[o["column"]] = df[o["column"]].astype(object)  # a column read as numbers must accept text such as a NISN with a leading zero
    df.loc[mask, o["column"]] = o["new_value"]
    return df


def apply_overrides(df: pd.DataFrame, path: Path, source_file: str) -> tuple[pd.DataFrame, list[Issue]]:
    """Apply one-off fixes (source_file,row,column,new_value,reason,student) to the raw values of one file.

    `student` is the name in that row when the line was written. A row that holds another name now (the file was resent)
    gets no override and an error, so a fix never lands on the wrong student.
    """
    if not path.exists():
        return df, []
    table = pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")
    table = table[table["source_file"] == source_file]
    issues, df = [], df.copy()
    names = {int(r): letters(n) for r, n in zip(df["source_row"], df["Nama Lengkap"])}  # the student of each row as sent, before any override
    for _, o in table.iterrows():
        if not o["row"].isdigit() or o["column"] not in df.columns:
            issues.append(Issue(source_file, 0, o["column"], o["new_value"], f"override line ignored: row {o['row']!r} or column {o['column']!r} is not valid", "warning"))
            continue
        mask = df["source_row"] == int(o["row"])
        given = o.get("student", "").strip()
        student = "" if given == NO_NAME else letters(given)  # a row sent without a name is written as (no name)
        if int(o["row"]) not in names:
            issues.append(Issue(source_file, int(o["row"]), o["column"], o["new_value"], "override matches no row", "warning"))
        elif given and student != names[int(o["row"])]:
            issues.append(Issue(source_file, int(o["row"]), o["column"], o["new_value"], f"override not applied: the row no longer holds the student {o['student']!r}, move the override to the right row", "error", "override_wrong_student"))
        else:
            if not given:
                issues.append(Issue(source_file, int(o["row"]), o["column"], o["new_value"], "override names no student, so it applies to whoever is in the row: add the student's name to the line", "warning", "override_no_student"))
            if mask.any():  # a row dropped by an earlier line of this file is gone
                df = _apply(df, mask, o)
    return df, issues
