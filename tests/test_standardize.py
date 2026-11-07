import pandas as pd

from registration.cli import ROOT, load_config
from registration.pipeline import process_file
from registration.readers import read_workbook
from registration.standardize import drop_template_examples, normalize_values, rename_headers


def run(make_workbook, cfg, rows):
    df = read_workbook(make_workbook("school.xlsx", rows))
    df, _ = rename_headers(df, cfg)
    return normalize_values(df, cfg)


def errors(issues):
    return [(i.source_row, i.code) for i in issues if i.severity == "error"]


def test_reader_stops_at_instruction_block(make_workbook, row):
    df = read_workbook(make_workbook("a.xlsx", [row(), row()]))
    assert len(df) == 2 and list(df["source_row"]) == [2, 3]


def test_reader_resumes_at_a_header_repeated_below_the_block(make_workbook, row, cfg):
    import openpyxl

    path = make_workbook("two_tables.xlsx", [row()])
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    ws.append([])
    ws.append([c.value for c in ws[1]])
    ws.append([c.value for c in ws[2]])
    wb.save(path)
    df = read_workbook(path)
    assert len(df) == 2 and list(df["source_row"]) == [2, 8]


def test_variants_are_normalized(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row()])
    r = table.iloc[0]
    assert (r["Nama Lengkap"], r["Kategori"], r["Gender"], r["Kelas"]) == ("Andi Test", "Penggalang", "Laki-laki", 7)
    assert (r["Kota/Kabupaten"], r["Nama Biro"], r["Bahasa"], r["Sesi"]) == ("Bandung", "Universitas Telkom", "Indonesia", "B")
    assert r["Nama Pendamping"] == "Budi Test" and r["No Kontak Pendamping"] == "081200000001"
    assert not errors(issues)


def test_nisn_padded_missing_or_malformed(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row(NISN=198765432), row(NISN=None), row(NISN="12345"), row(NISN="abcd_00001"), row(NISN="telkomuniversity_00001"), row(NISN="-")])
    assert list(table["NISN"]) == ["0198765432", "-", "12345", "abcd_00001", "telkomuniversity_00001", "-"]
    assert errors(issues) == [(3, "missing_nisn"), (4, "nisn_format"), (5, "nisn_format"), (7, "missing_nisn")]  # only our bureau code is a key; a typed "-" is a missing NISN
    assert [(i.source_row, i.code) for i in issues if i.severity == "warning" and i.column == "NISN"] == [(2, "nisn_padded")]


def test_empty_bureau_column_is_filled_with_our_bureau(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row(**{"Nama Biro": None})])
    assert table.iloc[0]["Nama Biro"] == "Universitas Telkom" and not errors(issues)
    assert [(i.code, i.severity) for i in issues if i.column == "Nama Biro"] == [("default_filled", "warning")]


def test_nisn_leading_apostrophe_is_removed(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row(NISN="'0100000001")])
    assert list(table["NISN"]) == ["0100000001"] and not errors(issues)
    assert [(i.code, i.severity) for i in issues if i.column == "NISN"] == [("nisn_apostrophe", "warning")]


def test_kategori_checked_against_kelas(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row(Kategori="Siaga"), row(Kategori=None)])
    assert table.iloc[1]["Kategori"] == "Penggalang"
    assert [(i.source_row, i.code, i.severity) for i in issues if i.column == "Kategori"] == [(2, "kategori_mismatch", "error"), (3, "kategori_filled", "warning")]


def test_session_must_fit_the_category(make_workbook, cfg, row):
    rows = [
        row(Kategori="SiKecil", Kelas=2, Sesi="E"),          # Friday has no E
        row(Kategori="SiKecil", Kelas=2, Sesi="D"),
        row(Kategori="Siaga", Kelas=5, Sesi="A1"),           # letters with 1 are Wednesday, Penggalang only
        row(Kategori="Penggalang", Kelas=8, Sesi="A1"),
        row(Kategori="Penegak", Kelas=11, Sesi="E"),
        row(Sesi="Z"),
    ]
    _, issues = run(make_workbook, cfg, rows)
    assert errors(issues) == [(2, "sesi_category"), (4, "sesi_category"), (7, "sesi_invalid")]


def test_unknown_values_and_bad_class_are_errors(make_workbook, cfg, row):
    _, issues = run(make_workbook, cfg, [row(Gender="x"), row(Kelas="abc"), row(Kelas=15)])
    assert errors(issues) == [(2, "unknown_value"), (3, "kelas_invalid"), (4, "kelas_invalid")]


def test_template_example_rows_are_dropped(make_workbook, cfg, row):
    df = read_workbook(make_workbook("s.xlsx", [row(**{"Nama Lengkap": "Ananda Hening"}), row(), row(**{"Nama Lengkap": "Andika Perdana"})]))
    df, _ = rename_headers(df, cfg)
    kept, issues = drop_template_examples(df, cfg)
    assert list(kept["Nama Lengkap"]) == ["ANDI TEST"]
    assert [(i.source_row, i.code, i.severity) for i in issues] == [(2, "template_example", "warning"), (4, "template_example", "warning")]


def test_overrides_fix_and_drop_rows(make_workbook, cfg, row, replies):
    path = make_workbook("school.xlsx", [row(), row(), row()])
    pd.DataFrame([
        ["school.xlsx", 2, "Nama Sekolah", "SMP Benar", "typo"],
        ["school.xlsx", 3, "Nama Lengkap", "__drop__", "duplicate"],
        ["school.xlsx", 99, "Nama Sekolah", "x", "stale"],
    ], columns=["source_file", "row", "column", "new_value", "reason"]).to_csv(cfg["paths"]["overrides"], index=False)
    status = process_file(path, cfg, replies, cfg["paths"]["standardized"])
    table = pd.read_csv(cfg["paths"]["standardized"] / "school.csv", dtype=str)
    assert status["rows"] == 2 and list(table["Nama Sekolah"]) == ["SMP Benar", "SMP Contoh"]
    report = pd.read_csv(cfg["paths"]["standardized"] / "school.review.csv")
    assert "override matches no row" in set(report["reason"])


def test_configuration_is_consistent():
    cfg = load_config(ROOT / "configs" / "default.yaml")
    assert cfg["columns"][0] == "No" and cfg["flag_error_share"] == 0.30
    assert set(cfg["sesi_by_kategori"]) == set(cfg["kategori_by_kelas"])
    assert all(set(v) <= set(cfg["sesi_valid"]) for v in cfg["sesi_by_kategori"].values())


def test_an_override_line_with_a_bad_row_or_column_is_reported_and_does_not_stop_the_run(make_workbook, cfg, replies, row):
    cfg["paths"]["overrides"].write_text("source_file,row,column,new_value,reason\nschool.xlsx,abc,NISN,1,bad row\nschool.xlsx,2,Nope,1,bad column\nschool.xlsx,2,Gender,Perempuan,fine\n", encoding="utf-8")
    result = process_file(make_workbook("school.xlsx", [row()]), cfg, replies, cfg["paths"]["standardized"])
    assert result["status"] == "ok" and result["warnings"] >= 2


def test_a_file_is_redone_after_the_overrides_change_but_not_before(make_workbook, cfg, replies, row):
    import os
    import time

    from registration.pipeline import is_done

    path = make_workbook("school.xlsx", [row()])
    process_file(path, cfg, replies, cfg["paths"]["standardized"])
    overrides = cfg["paths"]["overrides"]
    overrides.write_text("source_file,row,column,new_value,reason\n", encoding="utf-8")
    os.utime(overrides, (time.time() - 100, time.time() - 100))
    assert is_done(cfg["paths"]["standardized"], path, [overrides])
    os.utime(overrides, None)
    assert not is_done(cfg["paths"]["standardized"], path, [overrides])


def test_the_school_name_in_the_bureau_column_is_replaced_by_our_bureau_but_another_bureau_is_an_error(make_workbook, cfg, row):
    table, issues = run(make_workbook, cfg, [row(**{"Nama Biro": "SMP Contoh"}), row(**{"Nama Biro": "Universitas Lain"})])
    assert list(table["Nama Biro"]) == ["Universitas Telkom", "Universitas Lain"]
    assert [(i.source_row, i.code, i.severity) for i in issues if i.column == "Nama Biro"] == [(2, "default_filled", "warning"), (3, "unknown_value", "error")]
