from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

REVIEW_COLUMNS = ["source_file", "source_row", "column", "value", "code", "reason", "severity"]


@dataclass
class Issue:
    source_file: str
    source_row: int | None
    column: str
    value: str
    reason: str
    severity: str  # "error" holds the school's output, "warning" is listed only
    code: str = ""  # stable name of the problem, used to pick a reply message


def write_report(issues: list[Issue], path: Path) -> None:
    frame = pd.DataFrame([asdict(i) for i in issues], columns=REVIEW_COLUMNS)
    frame["source_row"] = frame["source_row"].astype("Int64")  # whole numbers, blank for file-level issues
    frame.to_csv(path, index=False, encoding="utf-8")
