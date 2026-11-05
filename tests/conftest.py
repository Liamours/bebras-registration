from pathlib import Path

import openpyxl
import pytest

from registration.cli import ROOT, load_config
from registration.replies import load_replies

CANON = ["No", "Nama Lengkap", "NISN", "Email", "Kategori", "Gender", "Kelas", "Jenjang Sekolah", "Nama Sekolah", "Kota/Kabupaten",
         "Nama Pendamping", "No Kontak Pendamping", "Status Pendamping", "Bahasa", "Sesi", "Nama Biro"]
# header spellings as schools type them: trailing space, typos
VARIANT_HEADER = [{"Nama Lengkap": "Nama Lengkap ", "Kategori": "Gategori", "Kota/Kabupaten": "Kot/kabupaten"}.get(c, c) for c in CANON]
DEFAULTS = {
    "No": 1, "Nama Lengkap": "ANDI TEST", "NISN": 3000000001, "Email": "andi@example.com", "Kategori": "penggalang",
    "Gender": "laki laki", "Kelas": "7A", "Jenjang Sekolah": "SMP", "Nama Sekolah": "SMP Contoh", "Kota/Kabupaten": "BANDUNG",
    "Nama Pendamping": "BUDI TEST", "No Kontak Pendamping": "+62 812-0000-0001", "Status Pendamping": "Guru",
    "Bahasa": "B. Indonesia", "Sesi": "b", "Nama Biro": "Universitas Telkom",
}


def make_row(**changes) -> list:
    values = DEFAULTS | {k.replace("_", " ") if k not in DEFAULTS else k: v for k, v in changes.items()}
    return [values[c] for c in CANON]


@pytest.fixture
def row():
    """row(**{"Nama Lengkap": ...}) returns one student row in template column order."""
    def build(**changes):
        return make_row(**changes)
    return build


@pytest.fixture
def cfg(tmp_path):
    """The real configuration with every path moved into a temporary folder."""
    cfg = load_config(ROOT / "configs" / "default.yaml")
    for key in cfg["paths"]:
        cfg["paths"][key] = tmp_path / key
    cfg["paths"]["overrides"] = tmp_path / "overrides.csv"
    cfg["paths"]["routing"] = tmp_path / "routing.csv"
    cfg["paths"]["upload_format"] = tmp_path / "format.xlsx"      # absent unless a test creates it
    for key in ("standardized", "submit_ready"):
        cfg["paths"][key].mkdir()
    cfg["intake"]["target_dir"] = tmp_path / "raw"
    cfg["intake"]["state_file"] = tmp_path / "raw" / "intake_state.csv"
    return cfg


@pytest.fixture
def replies():
    return load_replies(ROOT / "configs" / "replies.yaml")


@pytest.fixture
def make_workbook(tmp_path):
    def make(name: str, rows: list[list], header: list[str] | None = None, block: bool = True) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(header or VARIANT_HEADER)
        for r in rows:
            ws.append(r)
        if block:
            ws.append([])
            ws.append(["Keterangan", None, "catatan: instruction block"])
            ws.append(["No:", "No Urut"])
        path = tmp_path / name
        wb.save(path)
        return path
    return make
