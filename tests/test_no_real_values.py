import subprocess
from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parents[3] / "data" / "standardized"
SKIP = ("review.csv", "status.csv", "rejected.csv", "school_status.csv")
COLUMNS = ["Nama Lengkap", "NISN", "Email", "No Kontak Pendamping", "Nama Pendamping"]


def real_values() -> set[str]:
    values = set()
    for path in DATA.glob("*.csv"):
        if not path.name.endswith(SKIP):
            table = pd.read_csv(path, dtype=str)
            for column in COLUMNS:
                values |= {v.strip() for v in table.get(column, []).dropna() if len(v.strip()) >= 9}
    return values


@pytest.mark.skipif(not DATA.exists(), reason="the data folder exists only on the committee's machine")
def test_no_value_from_the_submitted_data_is_tracked():
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    text = "\n".join(Path(f).read_text(encoding="utf-8", errors="ignore") for f in files if f and Path(f).suffix in {".py", ".md", ".yaml", ".toml", ".csv", ".txt"} and Path(f).name != "test_no_real_values.py")
    found = sorted(v for v in real_values() if v in text)
    assert not found, f"{len(found)} real value(s) from the data are in tracked files, replace them with made-up ones"
