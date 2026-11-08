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


def test_the_same_nisn_under_different_names_in_one_school_is_not_decided_and_holds_both(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(**{"Nama Lengkap": "Ani Satu"}), row(**{"Nama Lengkap": "Budi Dua"})])
    students, report = deduplicate(cfg)
    assert len(students) == 2 and students["has_error"].all()
    assert list(report["check"]) == ["same_key_different_names"] * 2 and set(report["kept"]) == {"held"}


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


def test_a_resent_file_with_shifted_rows_or_a_new_name_keeps_the_key_of_the_student(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"})])
    first = deduplicate(cfg)[0].iloc[0]["NISN"]
    process(make_workbook, cfg, replies, "b.xlsx", [row(NISN=3000000005, **{"Nama Lengkap": "Budi Dua"}), row(NISN=None, **{"Nama Lengkap": "ANI SATU"})])  # another name, another row
    again, report = deduplicate(cfg)
    assert first == "telkomuniversity_00001"
    assert list(report["check"]) == ["same_key_in_school"] * 2 and set(report["key_or_name"]) == {first}  # the resent student got the old key, so it is found as the same student
    assert sorted(again["Nama Lengkap"]) == ["Ani Satu", "Budi Dua"]


def test_a_row_without_errors_wins_over_a_fuller_row_with_an_error(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(Kelas=99, **{"Nama Lengkap": "Ani Satu"}), row(Email=None, **{"Nama Lengkap": "Ani Satu"})])
    students, _ = deduplicate(cfg)
    assert len(students) == 1 and not students.iloc[0]["has_error"]


def test_a_school_name_shared_by_several_schools_is_held_and_never_cut_into_one_of_them(make_workbook, cfg, replies, row):
    pd.DataFrame([["sd_negeri_1", "SD Negeri 1", "1", "SD", "Kota Bandung", ""], ["sd_negeri_1_2", "SD Negeri 1", "2", "SD", "Kabupaten Bandung", ""]],
                 columns=["school_slug", "canonical_name", "npsn", "jenjang", "region", "aliases"]).to_csv(cfg["paths"]["school_master"], index=False)
    process(make_workbook, cfg, replies, "a.xlsx", [row(**{"Nama Sekolah": "SDN 1", "Kota/Kabupaten": "Bandung"})])
    students, _ = deduplicate(cfg)
    assert students.iloc[0]["school_slug"] == "sd_negeri_1_ambiguous" and students.iloc[0]["has_error"]
    review = pd.read_csv(cfg["paths"]["deduplicated"] / "school_review.csv", dtype=str)
    assert "school_ambiguous" in set(review["check"])


def test_nothing_to_process_removes_the_old_deduplicated_table(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row()])
    deduplicate(cfg)
    assert (cfg["paths"]["deduplicated"] / "students.csv").exists()
    (cfg["paths"]["standardized"] / "status.csv").unlink()
    deduplicate(cfg)
    assert not (cfg["paths"]["deduplicated"] / "students.csv").exists()


def test_a_resent_file_with_an_inserted_row_never_gives_two_students_one_key(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"})])
    deduplicate(cfg)
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Baru Dua"}), row(NISN=None, **{"Nama Lengkap": "Ani Satu"})])  # a row inserted above, same file name
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason\n", encoding="utf-8")
    process_file(cfg["paths"]["standardized"].parent / "a.xlsx", cfg, replies, cfg["paths"]["standardized"])
    students, report = deduplicate(cfg)
    keys = dict(zip(students["Nama Lengkap"], students["NISN"]))
    assert len(students) == 2 and len(set(keys.values())) == 2 and keys["Ani Satu"] == "telkomuniversity_00001"  # Ani keeps her key, the new student gets the next one
    assert report.empty


def test_a_corrected_email_or_class_keeps_the_key_of_a_student_without_a_nisn(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"})])
    first = deduplicate(cfg)[0].iloc[0]["NISN"]
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason\na.xlsx,2,Email,baru@example.com,corrected\na.xlsx,2,Kelas,8,corrected\n", encoding="utf-8")
    process_file(cfg["paths"]["standardized"].parent / "a.xlsx", cfg, replies, cfg["paths"]["standardized"])
    students, report = deduplicate(cfg)
    assert list(students["NISN"]) == [first] and students.iloc[0]["Email"] == "baru@example.com" and report.empty


def test_a_corrected_name_of_a_student_without_a_nisn_is_reported_with_the_old_key(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"})])
    first = deduplicate(cfg)[0].iloc[0]["NISN"]
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason\na.xlsx,2,Nama Lengkap,Ani Dua,corrected\n", encoding="utf-8")
    process_file(cfg["paths"]["standardized"].parent / "a.xlsx", cfg, replies, cfg["paths"]["standardized"])
    students, report = deduplicate(cfg)
    assert list(students["NISN"]) == ["telkomuniversity_00002"]  # a new student until a person says otherwise
    assert list(report["check"]) == ["key_new_for_changed_row"] and first in report.iloc[0]["reason"]


def test_two_students_with_one_name_in_one_school_get_two_keys_and_neither_is_dropped(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, Kelas=7, Email="a@example.com", **{"Nama Lengkap": "Ani Satu"}), row(NISN=None, Kelas=8, Email="b@example.com", **{"Nama Lengkap": "Ani Satu"})])
    students, report = deduplicate(cfg)
    assert len(students) == 2 and students["NISN"].nunique() == 2
    assert set(report["check"]) == {"same_name_in_school"}  # listed for a person, not merged


def test_an_empty_keys_file_is_read_as_no_state_and_is_written_whole(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None)])
    cfg["paths"]["assigned_keys"].parent.mkdir(parents=True, exist_ok=True)
    cfg["paths"]["assigned_keys"].write_bytes(b"")
    students, _ = deduplicate(cfg)
    assert list(students["NISN"]) == ["telkomuniversity_00001"]
    assert not cfg["paths"]["assigned_keys"].with_suffix(".tmp").exists() and cfg["paths"]["assigned_keys"].stat().st_size > 0


def test_the_same_student_twice_with_different_values_is_held_not_decided_by_file_order(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(Email="old@example.com", **{"Nama Lengkap": "Ani Satu"})])
    process(make_workbook, cfg, replies, "b.xlsx", [row(Email="new@example.com", **{"Nama Lengkap": "Ani Satu"})])
    students, report = deduplicate(cfg)
    assert len(students) == 2 and students["has_error"].all()
    assert list(report["check"]) == ["same_key_conflicting_values"] * 2 and "Email" in report.iloc[0]["reason"]


def test_a_row_without_a_name_gets_no_bureau_key(make_workbook, cfg, replies, row):
    process(make_workbook, cfg, replies, "a.xlsx", [row(NISN=None, **{"Nama Lengkap": "Ani Satu"}), row(NISN=None, **{"Nama Lengkap": None})])
    students, _ = deduplicate(cfg)
    keys = dict(zip(students["Nama Lengkap"], students["NISN"]))
    assert keys["Ani Satu"] == "telkomuniversity_00001" and "telkomuniversity_00002" not in set(students["NISN"])
