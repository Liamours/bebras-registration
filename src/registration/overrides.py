from pathlib import Path

import pandas as pd

from registration.review import Issue

DROP = "__drop__"


def apply_overrides(df: pd.DataFrame, path: Path, source_file: str) -> tuple[pd.DataFrame, list[Issue]]:
    """Apply one-off fixes (source_file,row,column,new_value,reason) to the raw values of one file."""
    if not path.exists():
        return df, []
    table = pd.read_csv(path, dtype=str, encoding="utf-8").fillna("")
    table = table[table["source_file"] == source_file]
    issues, df = [], df.copy()
    for _, o in table.iterrows():
        mask = df["source_row"] == int(o["row"])
        if not mask.any():
            issues.append(Issue(source_file, int(o["row"]), o["column"], o["new_value"], "override matches no row", "warning"))
        elif o["new_value"] == DROP:
            df = df[~mask]
        else:
            df.loc[mask, o["column"]] = o["new_value"]
    return df, issues
