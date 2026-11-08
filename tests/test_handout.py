import csv
from datetime import datetime

import openpyxl
import pytest

from registration import handout

HEADER = ["", "Username", "Nama Lengkap", "Gender", "Email", "Password", "Sekolah", "Kota/ Kabupaten", "Pendamping", "Jenjang", "Kelas", "Bahasa", "Kategori", "Sesi", "No Kontak Pendamping"]


def student(username, name, school, companion, phone, grade="7", category="Penggalang", password="01234567"):
    return ["", username, name, "L", "x@example.com", password, school, "Kabupaten Bandung", companion, "SMP", grade, "Indonesia", category, "A", phone]


@pytest.fixture
def export(tmp_path):
    rows = [
        student("ani1000001", "Ani Contoh", "SMP Contoh", "Dewi Contoh, S.Pd", "0812-0000-0001", "9"),
        student("bud1000002", "Budi Contoh", "SMP Contoh", "Dewi Contoh S.Pd", "+62 812 0000 0001", "7"),
        student("cit1000003", "Citra Contoh", "SD Contoh", "Dewi Contoh, S.Pd", "081200000001", "2", "SiKecil"),
        student("dan1000004", "Dani O'Contoh", "SMP Contoh", "Ibu Fiktif", "081200000002"),
        student("eka1000005", "Eka ’Contoh", "SMP Contoh", "Pak Fiktif", ""),
        student("fit1000006", "Fita Contoh", "SMP Contoh", "pak  fiktif", "-"),
    ]
    path = tmp_path / "manajemen_siswa_bebrasweb-20261108-2300.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Manajemen Siswa"])
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def test_students_are_grouped_by_phone_and_by_name_when_there_is_no_phone(export):
    parts = handout.groups(handout.read_site(export))
    assert sorted(parts) == ["081200000001", "081200000002", "name_pakfiktif"]
    assert list(parts["081200000001"]["Username"]) == ["cit1000003", "bud1000002", "ani1000001"]  # SD first, then SMP by class
    assert handout.companion_names(parts["081200000001"])[0] == "Dewi Contoh, S.Pd"  # the most frequent spelling


def test_a_run_writes_an_excel_file_and_a_pdf_per_companion_and_keeps_leading_zeros(cfg, export):
    cfg["paths"]["accounts"].mkdir(exist_ok=True)
    out, companions, students = handout.make_handouts(cfg, export, datetime(2026, 11, 8, 23, 30))
    assert (companions, students) == (3, 6) and out.name == "20261108-2330"
    assert sorted(p.name for p in out.iterdir()) == ["dewi_contoh_s_pd-081200000001.pdf", "dewi_contoh_s_pd-081200000001.xlsx", "ibu_fiktif-081200000002.pdf",
                                                    "ibu_fiktif-081200000002.xlsx", "pak_fiktif.pdf", "pak_fiktif.xlsx"]
    sheet = openpyxl.load_workbook(out / "dewi_contoh_s_pd-081200000001.xlsx")["Akun"]
    assert [c.value for c in sheet[2]] == ["SD Contoh", "Citra Contoh", "2", "SiKecil", "A", "cit1000003", "01234567"]
    assert (out / "pak_fiktif.pdf").read_bytes().startswith(b"%PDF")


def test_text_the_core_pdf_font_cannot_show_is_replaced_instead_of_failing():
    assert handout.pdf_text("Eka ’Contoh – 中") == "Eka 'Contoh - ?"


def test_a_run_never_writes_into_an_earlier_folder(cfg, export):
    cfg["paths"]["accounts"].mkdir(exist_ok=True)
    handout.make_handouts(cfg, export, datetime(2026, 11, 8, 23, 30))
    with pytest.raises(FileExistsError):
        handout.make_handouts(cfg, export, datetime(2026, 11, 8, 23, 30))
