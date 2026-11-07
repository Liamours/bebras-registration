import pandas as pd
import openpyxl
import pytest

from registration.dedup import deduplicate
from registration.partition import partition, slugify, upload_header
from registration.pipeline import process_file
from registration.status import mark_uploaded, school_status
from tests.conftest import CANON

STAMP1, STAMP2 = "20261105-1000", "20261105-1100"


def process(make_workbook, cfg, replies, name, rows):
    process_file(make_workbook(name, rows), cfg, replies, cfg["paths"]["standardized"])


def cut(cfg, **kw):
    """The flow of the command line: deduplicate, then cut the upload files."""
    deduplicate(cfg)
    return partition(cfg, **kw)


def state(report, school):
    return report[report["school"] == school].iloc[0]


def read_upload(path):
    ws = openpyxl.load_workbook(path).worksheets[0]
    return [[c.value for c in r] for r in ws.iter_rows()], ws


def test_slug():
    assert slugify("SMP Negeri 1 Bandung") == "smp_negeri_1_bandung" and slugify("   ") == "unknown"


def test_one_file_per_school_in_the_upload_format(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=198765432, **{"Nama Lengkap": "Zed Test"}), row(NISN=3000000002, **{"Nama Lengkap": "Amy Test"})])
    report = cut(cfg, stamp=STAMP1)
    r = state(report, "SMP Contoh")
    assert (r["state"], r["rows"], r["file"]) == ("written", 2, f"smp_contoh-{STAMP1}.xlsx")
    rows, ws = read_upload(cfg["paths"]["submit_ready"] / "smp_contoh" / r["file"])
    assert rows[0] == CANON                                           # no official format file here: the configured columns
    assert [x[CANON.index("Nama Lengkap")] for x in rows[1:]] == ["Amy Test", "Zed Test"]
    assert [x[0] for x in rows[1:]] == [1, 2]                         # numbered again
    nisn_cells = [ws.cell(row=i, column=3) for i in (2, 3)]
    assert [c.value for c in nisn_cells] == ["3000000002", "0198765432"] and all(c.number_format == "@" for c in nisn_cells)
    assert rows[1][CANON.index("Kelas")] == 7 and isinstance(rows[1][CANON.index("Kelas")], int)


def test_a_school_with_errors_is_held_and_gets_no_file(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "b.xlsx", [row(**{"Nama Sekolah": "SMP Dua"}), row(**{"Nama Sekolah": "SMP Dua"}, NISN=3000000009, Kelas=99)])
    report = cut(cfg, stamp=STAMP1)
    r = state(report, "SMP Dua")
    assert r["state"] == "held" and "1 rows with errors" in r["reason"]
    assert not (cfg["paths"]["submit_ready"] / "smp_dua").exists()


def test_later_students_go_into_a_new_file_and_earlier_files_are_untouched(make_workbook, cfg, replies, row):
    first = [row(NISN=3000000001), row(NISN=3000000002)]
    process(make_workbook, cfg, replies, "a.xlsx", first)
    cut(cfg, stamp=STAMP1)
    assert state(cut(cfg, stamp=STAMP2), "SMP Contoh")["state"] == "nothing_new"
    process(make_workbook, cfg, replies, "a.xlsx", first + [row(NISN=3000000003)])
    r = state(cut(cfg, stamp=STAMP2), "SMP Contoh")
    assert (r["state"], r["rows"]) == ("written", 1)
    folder = cfg["paths"]["submit_ready"] / "smp_contoh"
    assert sorted(p.name for p in folder.glob("*.xlsx")) == [f"smp_contoh-{STAMP1}.xlsx", f"smp_contoh-{STAMP2}.xlsx"]
    assert len(read_upload(folder / f"smp_contoh-{STAMP1}.xlsx")[0]) == 3          # header and two students, as before


def test_categories_can_be_uploaded_one_after_another(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [
        row(NISN=3000000001, Kategori="SiKecil", Kelas=2, Sesi="A"),
        row(NISN=3000000002, Kategori="Siaga", Kelas=5, Sesi="A"),
        row(NISN=3000000003, Kategori="Siaga", Kelas=6, Sesi="A"),
    ])
    r = state(cut(cfg, kategori=["SiKecil"], stamp=STAMP1), "SMP Contoh")
    assert r["rows"] == 1
    r = state(cut(cfg, kategori=["Siaga"], stamp=STAMP2), "SMP Contoh")
    assert r["rows"] == 2


def test_the_same_nisn_in_two_schools_holds_both(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001, **{"Nama Sekolah": "SMP A"}), row(NISN=3000000002, **{"Nama Sekolah": "SMP A"})])
    process(make_workbook, cfg, replies, "b.xlsx", [row(NISN=3000000001, **{"Nama Sekolah": "SMP B"})])
    report = cut(cfg, stamp=STAMP1)
    assert state(report, "SMP A")["state"] == "held" and "repeated NISN" in state(report, "SMP A")["reason"]
    assert state(report, "SMP B")["state"] == "held"


def test_header_follows_the_official_format_file(make_workbook, cfg, replies, row):
    official = openpyxl.Workbook()
    official.active.append([c + " " if c == "Nama Biro" else c for c in CANON])      # the site's header has a trailing space
    official.save(cfg["paths"]["upload_format"])
    assert upload_header(cfg)[-1] == "Nama Biro "
    process(make_workbook, cfg, replies, "a.xlsx", [row()])
    cut(cfg, stamp=STAMP1)
    rows, _ = read_upload(cfg["paths"]["submit_ready"] / "smp_contoh" / f"smp_contoh-{STAMP1}.xlsx")
    assert rows[0][-1] == "Nama Biro " and rows[1][-1] == "Universitas Telkom"


def test_a_format_file_with_other_columns_is_refused(cfg):
    wrong = openpyxl.Workbook()
    wrong.active.append(["Foo", "Bar"])
    wrong.save(cfg["paths"]["upload_format"])
    with pytest.raises(ValueError, match="different columns"):
        upload_header(cfg)


def test_school_status_held_ready_uploaded(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001), row(NISN=3000000002)])
    process(make_workbook, cfg, replies, "b.xlsx", [row(NISN=None, **{"Nama Sekolah": "SMP Dua"})])
    status = lambda: dict(zip(*[school_status(cfg["paths"]["standardized"], cfg["paths"]["submit_ready"], slugify)[c] for c in ("school", "state")]))
    assert status() == {"SMP Contoh": "ready", "SMP Dua": "held"}
    cut(cfg, stamp=STAMP1)
    mark_uploaded(cfg["paths"]["submit_ready"], f"smp_contoh-{STAMP1}.xlsx")
    assert status()["SMP Contoh"] == "uploaded"
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001), row(NISN=3000000002), row(NISN=3000000003)])
    assert status()["SMP Contoh"] == "ready"                  # a new student is not on the site yet


def test_a_full_sesi_is_left_out_and_its_students_go_up_later_in_a_file_of_their_own(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001, Sesi="b1", **{"Nama Lengkap": "Ani Satu"}), row(NISN=3000000002, Sesi="a1", **{"Nama Lengkap": "Budi Dua"})])
    first = state(cut(cfg, stamp=STAMP1, exclude_sesi=["B1"]), "SMP Contoh")
    assert first["state"] == "written" and first["rows"] == 1
    rows, _ = read_upload(cfg["paths"]["submit_ready"] / "smp_contoh" / first["file"])
    assert [r[1] for r in rows[1:]] == ["Budi Dua"]
    later = state(cut(cfg, stamp=STAMP2), "SMP Contoh")
    assert later["rows"] == 1 and [r[1] for r in read_upload(cfg["paths"]["submit_ready"] / "smp_contoh" / later["file"])[0][1:]] == ["Ani Satu"]


def test_a_second_run_in_the_same_minute_never_overwrites_the_first_file(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001)])
    assert state(cut(cfg, stamp=STAMP1), "SMP Contoh")["state"] == "written"
    path = next(cfg["paths"]["submit_ready"].glob("smp_contoh/*.xlsx"))
    before = path.read_bytes()
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001), row(NISN=3000000002, **{"Nama Lengkap": "Budi Dua"})])
    again = state(cut(cfg, stamp=STAMP1), "SMP Contoh")
    assert again["state"] == "held" and "next minute" in again["reason"] and path.read_bytes() == before
    assert state(cut(cfg, stamp=STAMP2), "SMP Contoh")["rows"] == 1  # the next minute cuts only the new student


def test_output_names_that_collide_are_found_ignoring_case_and_reserved_names():
    from registration.pipeline import output_clashes

    assert output_clashes(["School.xlsx", "school.XLSX", "Other.xlsx"]) == ["School.xlsx", "school.XLSX"]
    assert output_clashes(["a.xlsx", "a.review.xlsx"]) == ["a.review.xlsx", "a.xlsx"]
    assert output_clashes(["Students.xlsx", "Status.xlsx", "fine.xlsx"]) == ["Status.xlsx", "Students.xlsx"]
    assert output_clashes(["one.xlsx", "two.xlsx"]) == []


def test_a_folder_with_a_similar_name_holds_the_school_until_a_person_decides(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row()])
    (cfg["paths"]["submit_ready"] / "smp_con_toh").mkdir()  # the slug of the school is smp_contoh
    held = state(cut(cfg, stamp=STAMP1), "SMP Contoh")
    assert held["state"] == "held" and "smp_con_toh" in held["reason"] and not list(cfg["paths"]["submit_ready"].glob("smp_contoh*/*.xlsx"))
    (cfg["paths"]["submit_ready"] / "smp_contoh").mkdir()  # the person says it is another school
    assert state(cut(cfg, stamp=STAMP1), "SMP Contoh")["state"] == "written"


def test_school_status_from_the_deduplicated_table_agrees_with_partition(tmp_path):
    students = pd.DataFrame([["smp_a", "SMP A", "3000000001", "False", "a.xlsx"], ["smp_a", "SMP A", "telkomuniversity_00001", "False", "a.xlsx"], ["smp_b", "SMP B", "3000000002", "True", "b.xlsx"]],
                            columns=["school_slug", "Nama Sekolah", "NISN", "has_error", "source_file"])
    table = school_status(tmp_path, tmp_path, slugify, students)
    assert dict(zip(table["school"], table["state"])) == {"SMP A": "ready", "SMP B": "held"}  # a key given to a student without a NISN is no error
