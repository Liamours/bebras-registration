import pandas as pd
import pytest

from registration.audit import audit
from registration.dedup import deduplicate
from registration.pipeline import process_file

SITE_HEADER = ["", "Username", "Nama Lengkap", "Gender", "Email", "Password", "Sekolah", "Kota/ Kabupaten", "Pendamping", "Jenjang", "Kelas", "Bahasa", "Kategori", "Sesi", "No Kontak Pendamping"]


def prepare(make_workbook, cfg, replies, row, rows=None, name="a.xlsx"):
    cfg["paths"]["raw"] = cfg["paths"]["standardized"].parent
    process_file(make_workbook(name, rows or [row(**{"Nama Lengkap": "Ani Satu", "NISN": 3000000001}), row(**{"Nama Lengkap": "Budi Dua", "NISN": 3000000002, "Gender": "perempuan"})]), cfg, replies, cfg["paths"]["standardized"])
    return deduplicate(cfg)[0]


def export(cfg, std, change=None, drop=None, extra=None):
    """A site table made from the standardized students, as the site would hold them; `change` edits one cell, `drop` removes a row."""
    rows = []
    for i, s in std.iterrows():
        rows.append(["", f"usr{i:07d}", s["Nama Lengkap"], {"Laki-laki": "L", "Perempuan": "P"}[s["Gender"]], s["Email"], "12345678", s["Nama Sekolah"], s["Kota/Kabupaten"],
                     s["Nama Pendamping"], s["Jenjang Sekolah"], s["Kelas"], s["Bahasa"], s["Kategori"], s["Sesi"], s["No Kontak Pendamping"]])
    table = pd.DataFrame(rows, columns=["c0", "Username", "Nama Lengkap", "Gender", "Email", "Password", "Sekolah", "Kota/ Kabupaten", "Pendamping", "Jenjang", "Kelas", "Bahasa", "Kategori", "Sesi", "No Kontak Pendamping"])
    if change:
        i, col, value = change
        table.loc[i, col] = value
    if drop is not None:
        table = table.drop(index=drop)
    if extra:
        table.loc[len(table)] = ["", "usr9999999", extra, "L", "x@example.com", "1", "SMP Contoh", "Bandung", "Budi", "SMP", "7", "Indonesia", "Penggalang", "B", "081200000001"]
    path = cfg["paths"]["standardized"].parent / "site.csv"
    lines = ['"Manajemen Siswa"', ",".join(f'"{c}"' for c in SITE_HEADER)] + [",".join(f'"{v}"' for v in r) for r in table.itertuples(index=False)]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def checks(issues):
    return sorted(set(issues["check"])) if len(issues) else []


def test_a_site_that_holds_what_the_senders_wrote_passes(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row)
    issues = audit(cfg, export(cfg, std))
    assert checks(issues) == [], issues.to_string()


@pytest.mark.parametrize("change, expected", [
    ((0, "Nama Lengkap", "Ani Sartu"), ["count", "missing_on_site", "site_extra"]),  # a changed spelling is another student to the match by name
    ((0, "Email", "other@example.com"), ["site_differs_from_files", "unexplained_change"]),
    ((0, "Kelas", "9"), ["unexplained_change"]),
    ((1, "Gender", "L"), ["unexplained_change"]),
    ((0, "Sesi", "Z"), ["absurd", "site_differs_from_files", "unexplained_change"]),
    ((0, "Jenjang", "MI"), ["absurd", "site_differs_from_files", "unexplained_change"]),
    ((0, "Nama Lengkap", "ani satu"), ["absurd", "site_differs_from_files"]),  # lower case only: the same student, but it prints wrong
    ((0, "Nama Lengkap", "Ani 2 Satu"), ["absurd", "count", "missing_on_site", "site_extra"]),
])
def test_each_kind_of_mistake_is_named(make_workbook, cfg, replies, row, change, expected):
    std = prepare(make_workbook, cfg, replies, row)
    assert checks(audit(cfg, export(cfg, std, change=change))) == sorted(expected)


def test_a_missing_and_an_extra_student_are_found(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row)
    assert "missing_on_site" in checks(audit(cfg, export(cfg, std, drop=1)))
    assert "site_extra" in checks(audit(cfg, export(cfg, std, extra="Cici Tiga")))


def test_a_raw_row_that_vanished_is_found_but_a_listed_drop_is_not(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row)
    kept = std[std["source_row"] != "3"]
    (cfg["paths"]["deduplicated"] / "students.csv").write_text(kept.drop(columns=["_key"], errors="ignore").to_csv(index=False), encoding="utf-8")
    site = export(cfg, kept)
    assert "raw_row_lost" in checks(audit(cfg, site))
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason,student\na.xlsx,3,Nama Lengkap,__drop__,duplicate,Budi Dua\n", encoding="utf-8")
    assert "raw_row_lost" not in checks(audit(cfg, site))


def test_an_override_must_be_on_the_site_and_carry_a_reason_and_a_student(make_workbook, cfg, replies, row):
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason,student\na.xlsx,2,Email,fixed@example.com,typo in the domain,Ani Satu\na.xlsx,3,Email,b@example.com,,\n", encoding="utf-8")
    std = prepare(make_workbook, cfg, replies, row)
    issues = audit(cfg, export(cfg, std, change=(0, "Email", "andi@example.com")))
    assert {"override_not_on_site", "record"} <= set(issues["check"])
    assert checks(audit(cfg, export(cfg, std))) == ["record"]  # the site is right, the line without a reason is not


def test_a_file_marked_uploaded_needs_a_verified_line_in_the_log(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row)
    cfg["paths"]["submit_ready"].joinpath("uploaded.csv").write_text("file,uploaded_at\nsome-file.xlsx,2026-11-08T08:00:00\n", encoding="utf-8")
    cfg["paths"]["audit"].mkdir()
    cfg["paths"]["audit"].joinpath("uploads.csv").write_text("uploaded_at,uploaded_by,school,file,students,issues,result,report\n", encoding="utf-8")
    assert "record" in checks(audit(cfg, export(cfg, std)))


def test_the_site_must_match_our_own_files_in_case_where_the_sender_comparison_cannot_tell(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row)
    issues = audit(cfg, export(cfg, std, change=(0, "Sekolah", "SMP CONTOH")))
    assert checks(issues) == ["site_differs_from_files"] and list(issues["field"]) == ["Nama Sekolah"]


def test_an_email_is_exact_and_a_listed_domain_typo_is_the_only_fix_that_passes(make_workbook, cfg, replies, row):
    std = prepare(make_workbook, cfg, replies, row, rows=[row(Email="ani.satu@gmail.con", **{"Nama Lengkap": "Ani Satu", "NISN": 3000000001})])
    assert std.iloc[0]["Email"] == "ani.satu@gmail.com"
    assert checks(audit(cfg, export(cfg, std))) == []
    assert "unexplained_change" in checks(audit(cfg, export(cfg, std, change=(0, "Email", "anisatu@gmail.com"))))


def test_two_students_with_one_name_and_school_are_a_warning_and_not_an_error(make_workbook, cfg, replies, row):
    rows = [row(NISN=3000000001, Kelas=7, Email="a@example.com", **{"Nama Lengkap": "Ani Satu"}), row(NISN=3000000002, Kelas=8, Email="b@example.com", **{"Nama Lengkap": "Ani Satu"})]
    std = prepare(make_workbook, cfg, replies, row, rows=rows)
    issues = audit(cfg, export(cfg, std))
    assert set(issues["check"]) == {"homonym"} and set(issues["severity"]) == {"warning"}


def test_an_uploaded_file_that_disagrees_with_the_site_is_found_and_a_later_file_replaces_it(make_workbook, cfg, replies, row):
    import shutil

    import openpyxl

    from registration.partition import partition
    from registration.status import mark_uploaded

    std = prepare(make_workbook, cfg, replies, row)
    first = partition(cfg, stamp="20261105-1000").iloc[0]["file"]
    folder = cfg["paths"]["submit_ready"] / "smp_contoh"
    mark_uploaded(cfg["paths"]["submit_ready"], first)
    assert "upload_file_not_on_site" not in checks(audit(cfg, export(cfg, std)))
    site = export(cfg, std, change=(0, "Sesi", "C"))
    assert "upload_file_not_on_site" in checks(audit(cfg, site))
    later = folder / first.replace("1000", "1100")
    shutil.copy(folder / first, later)
    wb = openpyxl.load_workbook(later)
    header = [c.value for c in wb.active[1]]
    for r in wb.active.iter_rows(min_row=2):
        if r[header.index("Nama Lengkap")].value == "Ani Satu":
            r[header.index("Sesi")].value = "C"
    wb.save(later)
    mark_uploaded(cfg["paths"]["submit_ready"], later.name)
    assert "upload_file_not_on_site" not in checks(audit(cfg, site))


def test_companion_phones_counting_up_by_one_on_the_site_are_absurd(make_workbook, cfg, replies, row):
    rows = [row(NISN=3000000001 + i, **{"Nama Lengkap": f"Siswa {n}", "No Kontak Pendamping": 81200000000 + i}) for i, n in enumerate(["Satu", "Dua", "Tiga"])]
    std = prepare(make_workbook, cfg, replies, row, rows=rows)
    issues = audit(cfg, export(cfg, std))
    assert list(issues["check"]) == ["absurd"] * 3 and set(issues["why"]) == {"the companion phones of several students count up by one"}


def test_a_row_that_dedup_dropped_for_a_fuller_row_with_the_same_key_is_covered(make_workbook, cfg, replies, row):
    prepare(make_workbook, cfg, replies, row)
    process_file(make_workbook("b.xlsx", [row(**{"Nama Lengkap": "Ani Satu", "NISN": 3000000001})]), cfg, replies, cfg["paths"]["standardized"])
    std = deduplicate(cfg)[0]
    assert "raw_row_lost" not in checks(audit(cfg, export(cfg, std)))


def test_a_school_name_may_lose_the_place_that_the_region_column_holds():
    from registration.audit import explain
    assert explain("Nama Sekolah", "SMPN 99 CONTOH BANDUNG", "SMP Negeri 99 Contoh") == "school name rule"
    assert explain("Nama Sekolah", "SMPN 98 CONTOH BANDUNG", "SMP Negeri 99 Contoh") is None


def test_a_hyphen_or_apostrophe_lost_in_any_name_is_one_warning_per_school_and_field(make_workbook, cfg, replies, row):
    rows = [row(**{"Nama Lengkap": "Ani Satu", "NISN": 3000000001, "Nama Pendamping": "Budi O'Contoh"}),
            row(**{"Nama Lengkap": "Budi Dua", "NISN": 3000000002, "Nama Pendamping": "Budi O'Contoh", "Gender": "perempuan"})]
    std = prepare(make_workbook, cfg, replies, row, rows=rows)
    path = export(cfg, std)
    assert checks(audit(cfg, path)) == []
    path.write_text(path.read_text(encoding="utf-8").replace("O'Contoh", "OContoh"), encoding="utf-8")
    issues = audit(cfg, path)
    assert checks(issues) == ["punctuation_lost"] and len(issues) == 1 and issues.iloc[0]["field"] == "Nama Pendamping" and "2 " in issues.iloc[0]["why"], issues.to_string()
