import pandas as pd

from registration.dedup import deduplicate
from registration.pipeline import process_file


def process(make_workbook, cfg, replies, name, rows):
    process_file(make_workbook(name, rows), cfg, replies, cfg["paths"]["standardized"])


def two(school_a="SMP Satu", school_b="SMP Dua"):
    return {"Nama Sekolah": school_a}, {"Nama Sekolah": school_b}


def test_students_without_a_nisn_get_a_bureau_key_that_is_never_reused(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"}), row(NISN=3000000002, **{"Nama Lengkap": "Budi Dua"}), row(NISN="telkomuniversity_00007", **{"Nama Lengkap": "Cici Tiga"})])
    students, _ = deduplicate(cfg)
    keys = dict(zip(students["Nama Lengkap"], students["NISN"]))
    assert keys["Ani Satu"] == "telkomuniversity_00008" and keys["Budi Dua"] == "3000000002"  # after the highest number already in the data
    assert not students["has_error"].any()
    process(make_workbook, cfg, replies, "b.xlsx", [row(NISN=None, **{"Nama Lengkap": "Dedi Empat"})])
    again, _ = deduplicate(cfg)
    keys = dict(zip(again["Nama Lengkap"], again["NISN"]))
    assert keys["Ani Satu"] == "telkomuniversity_00008" and keys["Dedi Empat"] == "telkomuniversity_00009"  # a rerun keeps keys, a new student gets the next number


def test_the_same_key_twice_in_one_school_keeps_the_fuller_row_and_lists_both(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(Email=None, **{"Nama Lengkap": "Ani Satu"}), row(**{"Nama Lengkap": "Ani Satu"})])
    students, report = deduplicate(cfg)
    assert len(students) == 1 and students.iloc[0]["Email"] == "andi@example.com"
    assert list(report["check"]) == ["same_key_in_school"] * 2 and sorted(report["kept"]) == ["no", "yes"]
    assert set(report["source_file"]) == {"a.xlsx"} and sorted(report["source_row"]) == ["2", "3"]  # every row stays traceable


def test_the_same_key_under_two_schools_is_not_decided_and_holds_both(make_workbook, cfg, replies, row):
    a, b = two()
    process(make_workbook, cfg, replies, "a.xlsx", [row(**a)])
    process(make_workbook, cfg, replies, "b.xlsx", [row(**b)])
    students, report = deduplicate(cfg)
    assert len(students) == 2 and students["has_error"].all()
    assert list(report["check"]) == ["same_key_two_schools"] * 2 and set(report["kept"]) == {"held"}


def test_an_override_decides_the_two_school_case_and_a_rerun_gives_the_same_result(make_workbook, cfg, replies, row):
    a, b = two()
    process(make_workbook, cfg, replies, "a.xlsx", [row(**a)])
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason\nb.xlsx,2,NISN,3000000099,sender confirmed\n", encoding="utf-8")
    process(make_workbook, cfg, replies, "b.xlsx", [row(**b)])
    first = deduplicate(cfg)[0]
    second = deduplicate(cfg)[0]
    assert not first["has_error"].any() and sorted(first["NISN"]) == ["3000000001", "3000000099"]
    pd.testing.assert_frame_equal(first, second)


def test_the_same_name_and_school_under_different_keys_is_listed_but_kept(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001, **{"Nama Lengkap": "Ani Satu"}), row(NISN=3000000002, **{"Nama Lengkap": "ANI SATU"})])
    students, report = deduplicate(cfg)
    assert len(students) == 2 and not students["has_error"].any()
    assert list(report["check"]) == ["same_name_in_school"] * 2
