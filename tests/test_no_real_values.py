import re
import subprocess
from pathlib import Path

import openpyxl
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
SKIP = ("review.csv", "status.csv", "rejected.csv", "school_status.csv")
COLUMNS = ["Nama Lengkap", "NISN", "Email", "No Kontak Pendamping", "Nama Pendamping"]
MIN_LENGTH = 9


def normal(value) -> str:
    return re.sub(r"[^a-z0-9@.]", "", str(value).lower())


def table_values(path: Path) -> set[str]:
    table = pd.read_csv(path, dtype=str)
    return {normal(v) for column in COLUMNS for v in table.get(column, []).dropna()}


def workbook_values(path: Path) -> set[str]:
    """Every cell under the columns of COLUMNS, on every sheet, below the row that holds the header."""
    values = set()
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for sheet in book.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        header = next((i for i, row in enumerate(rows) if any(str(c).strip() == "Nama Lengkap" for c in row if c is not None)), None)
        if header is None:
            continue
        keep = [j for j, c in enumerate(rows[header]) if c is not None and str(c).strip() in COLUMNS]
        body = rows[header + 1:]
        end = next((i for i, row in enumerate(body) if row and str(row[0]).strip() == "Keterangan"), len(body))  # the template's explanation block is public text
        values |= {normal(row[j]) for row in body[:end] for j in keep if j < len(row) and row[j] is not None}
    return values


def real_values(data: Path = DATA) -> set[str]:
    """Values of the submitted data, from the standardized tables and from the senders' own workbooks."""
    values = set()
    for path in (data / "standardized").glob("*.csv"):
        if not path.name.endswith(SKIP):
            values |= table_values(path)
    for path in (data / "raw").rglob("*.xlsx"):
        if not path.name.startswith("~$"):
            values |= workbook_values(path)
    return {v for v in values if len(v) >= MIN_LENGTH and (re.search("[a-z]", v) or len(re.sub(r"\D", "", v)) >= 10)}  # not the time slots of the template block


def values_found_in(text: str, values: set[str]) -> list[str]:
    haystack = normal(text)
    return sorted(v for v in values if v in haystack)


def test_a_value_that_differs_only_in_case_or_punctuation_is_found(tmp_path):
    raw = tmp_path / "raw" / "cp_team" / "x"
    raw.mkdir(parents=True)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["No", "Nama Lengkap", "Email"])
    sheet.append([1, "Sari Fiktif (Dewi)", "sarifiktif2025@sekolah.example"])
    sheet.append(["Keterangan", "Pengisian Nama Lengkap Sekolah", None])  # the template's block, not a student
    book.save(raw / "a.xlsx")
    found = values_found_in('clean_name("SARI FIKTIF  (dewi)") and "SariFiktif2025@Sekolah.example"', real_values(tmp_path))
    assert found == ["sarifiktif2025@sekolah.example", "sarifiktifdewi"]
    assert values_found_in("Budi Contoh Pengisian Nama Lengkap Sekolah", real_values(tmp_path)) == []


@pytest.mark.skipif(not (DATA / "raw").exists(), reason="the data folder exists only on the committee's machine")
def test_no_value_from_the_submitted_data_is_tracked():
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    text = "\n".join(Path(f).read_text(encoding="utf-8", errors="ignore") for f in files if f and Path(f).suffix in {".py", ".md", ".yaml", ".toml", ".csv", ".txt"} and Path(f).name != "test_no_real_values.py")
    config = yaml.safe_load(Path("configs/default.yaml").read_text(encoding="utf-8"))
    template = {normal(n) for n in config["template_example_names"]}  # the two invented students of the school template are public
    found = [v for v in values_found_in(text, real_values()) if v not in template]
    assert not found, f"{len(found)} real value(s) from the data are in tracked files, replace them with made-up ones"
