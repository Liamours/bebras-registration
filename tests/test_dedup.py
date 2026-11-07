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


def test_a_nisn_with_a_leading_zero_stays_text_through_the_deduplicated_table(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN="0123456789")])
    students, _ = deduplicate(cfg)
    assert list(students["NISN"]) == ["0123456789"]
    assert pd.read_csv(cfg["paths"]["deduplicated"] / "students.csv", dtype=str).iloc[0]["NISN"] == "0123456789"


def test_two_students_without_a_name_are_not_reported_as_one_student(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=3000000001, **{"Nama Lengkap": None}), row(NISN=3000000002, **{"Nama Lengkap": None})])
    _, report = deduplicate(cfg)
    assert report.empty  # both rows are errors already, a shared empty name says nothing


def test_the_school_review_follows_the_master_and_an_old_one_is_removed(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(**{"Nama Sekolah": "SMP Tidak Dikenal", "Kota/Kabupaten": "Bandung"})])
    pd.DataFrame([["smp_negeri_1_pacet", "SMP Negeri 1 Pacet", "20200001", "SMP", "Kabupaten Bandung", ""]],
                 columns=["school_slug", "canonical_name", "npsn", "jenjang", "region", "aliases"]).to_csv(cfg["paths"]["school_master"], index=False)
    deduplicate(cfg)
    review = pd.read_csv(cfg["paths"]["deduplicated"] / "school_review.csv", dtype=str)
    assert {"school_unmatched", "region_ambiguous"} == set(review["check"])
    cfg["paths"]["school_master"].unlink()
    deduplicate(cfg)
    assert not (cfg["paths"]["deduplicated"] / "school_review.csv").exists()


def test_assigned_keys_live_in_the_reference_state_file(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None)])
    deduplicate(cfg)
    assert cfg["paths"]["assigned_keys"].exists() and "telkomuniversity_00001" in cfg["paths"]["assigned_keys"].read_text(encoding="utf-8")
