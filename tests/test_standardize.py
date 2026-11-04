from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from registration.cli import ROOT, load_config, standardize_file
from registration.readers import read_workbook
from registration.standardize import normalize_values, rename_headers

HEADER = ["No", "Nama Lengkap ", "NISN", "Email", "Gategori", "Gender", "Kelas", "Jenjang Sekolah", "Nama Sekolah",
          "Kot/kabupaten", "Nama Pendamping", "No Kontak Pendamping", "Status Pendamping", "Bahasa", "Sesi", "Nama Biro"]


def make_workbook(path: Path, rows: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    ws.append([])
    ws.append(["Keterangan", None, "catatan: instruction block"])
    ws.append(["No:", "No Urut"])
    wb.save(path)
    return path


GOOD = [1, "ANDI TEST", 3000000001, "andi@example.com", "penggalang", "laki laki", "7A", "SMP", "SMP Contoh", "BANDUNG",
        "BUDI TEST", "+62 812-0000-0001", "Guru", "B. Indonesia", "b", "Universitas Telkom"]


@pytest.fixture
def cfg():
    return load_config(ROOT / "configs" / "default.yaml")


def run(tmp_path, cfg, rows):
    df = read_workbook(make_workbook(tmp_path / "school.xlsx", rows))
    df, _ = rename_headers(df, cfg)
    return normalize_values(df, cfg)


def test_reader_stops_at_instruction_block(tmp_path):
    df = read_workbook(make_workbook(tmp_path / "a.xlsx", [GOOD, GOOD]))
    assert len(df) == 2 and list(df["source_row"]) == [2, 3]


def test_variants_are_normalized(tmp_path, cfg):
    table, issues = run(tmp_path, cfg, [GOOD])
    row = table.iloc[0]
    assert (row["Nama Lengkap"], row["Kategori"], row["Gender"], row["Kelas"]) == ("Andi Test", "Penggalang", "Laki-laki", 7)
    assert (row["Kota/Kabupaten"], row["Nama Biro"], row["Bahasa"], row["Sesi"]) == ("Bandung", "Telkom University", "Indonesia", "B")
    assert row["No Kontak Pendamping"] == "0812000000" + "01"
    assert not [i for i in issues if i.severity == "error"]


def test_nisn_padded_or_missing(tmp_path, cfg):
    nine, missing = list(GOOD), list(GOOD)
    nine[2], missing[2] = 128384139, None
    table, issues = run(tmp_path, cfg, [nine, missing])
    assert table.iloc[0]["NISN"] == "0128384139" and table.iloc[1]["NISN"] == "-"
    assert [i.reason for i in issues if i.severity == "error"] == ["missing NISN (needs kode_biro)"]


def test_kategori_checked_against_kelas(tmp_path, cfg):
    wrong, blank = list(GOOD), list(GOOD)
    wrong[4], blank[4] = "Siaga", None
    table, issues = run(tmp_path, cfg, [wrong, blank])
    assert table.iloc[1]["Kategori"] == "Penggalang"
    assert [(i.source_row, i.severity) for i in issues if i.column == "Kategori"] == [(2, "error"), (3, "warning")]


def test_overrides_fix_and_drop_rows(tmp_path, cfg):
    path = make_workbook(tmp_path / "school.xlsx", [GOOD, GOOD, GOOD])
    over = tmp_path / "overrides.csv"
    pd.DataFrame([
        ["school.xlsx", 2, "Nama Sekolah", "SMP Benar", "typo"],
        ["school.xlsx", 3, "Nama Lengkap", "__drop__", "duplicate"],
        ["school.xlsx", 99, "Nama Sekolah", "x", "stale"],
    ], columns=["source_file", "row", "column", "new_value", "reason"]).to_csv(over, index=False)
    cfg["paths"]["overrides"] = over
    rows, errors, warnings = standardize_file(path, cfg, tmp_path)
    table = pd.read_csv(tmp_path / "school.csv", dtype=str)
    assert rows == 2 and list(table["Nama Sekolah"]) == ["SMP Benar", "SMP Contoh"]
    report = pd.read_csv(tmp_path / "school.review.csv")
    assert "override matches no row" in set(report["reason"])
