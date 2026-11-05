import os
import time

import openpyxl
import pandas as pd

from registration.pipeline import is_done, process_file
from registration.standardize import rename_headers
from tests.conftest import CANON, VARIANT_HEADER


def run(path, cfg, replies, **kw):
    return process_file(path, cfg, replies, cfg["paths"]["standardized"], **kw)


def without(*names):
    return [c for c in VARIANT_HEADER if c.strip() not in names]


def test_unreadable_file_is_rejected(tmp_path, cfg, replies):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"this is not a workbook")
    row = run(bad, cfg, replies)
    assert row["status"] == "rejected" and "cannot be opened" in row["reasons"]
    assert "tidak dapat dibuka" in (cfg["paths"]["standardized"] / "replies" / "bad.txt").read_text(encoding="utf-8")


def test_workbook_without_the_table_is_rejected(tmp_path, cfg, replies):
    wb = openpyxl.Workbook()
    wb.active.append(["foo", "bar"])
    path = tmp_path / "other.xlsx"
    wb.save(path)
    assert "no table" in run(path, cfg, replies)["reasons"]


def test_header_only_workbook_has_no_rows(make_workbook, cfg, replies):
    assert "no student rows" in run(make_workbook("empty.xlsx", []), cfg, replies)["reasons"]


def test_old_template_without_nisn_is_rejected_with_a_helpful_reply(make_workbook, cfg, replies, row):
    header = without("NISN", "Nama Biro")
    rows = [[v for c, v in zip(CANON, row()) if c not in ("NISN", "Nama Biro")]]
    result = run(make_workbook("old.xlsx", rows, header=header), cfg, replies)
    assert result["status"] == "rejected" and "old template" in result["reasons"]
    reply = (cfg["paths"]["standardized"] / "replies" / "old.txt").read_text(encoding="utf-8")
    assert "templat tahun sebelumnya" in reply and "bit.ly/TantanganBebras2026" in reply


def test_old_template_can_be_accepted_for_testing(make_workbook, cfg, replies, row):
    header = without("NISN", "Nama Biro")
    rows = [[v for c, v in zip(CANON, row()) if c not in ("NISN", "Nama Biro")]]
    result = run(make_workbook("old.xlsx", rows, header=header), cfg, replies, accept_old_template=True)
    assert result["status"] != "rejected" and result["rows"] == 1


def test_missing_required_columns_are_named(make_workbook, cfg, replies, row):
    header = without("Nama Sekolah", "Gategori", "Kelas")
    rows = [[v for c, v in zip(CANON, row()) if c not in ("Nama Sekolah", "Kategori", "Kelas")]]
    result = run(make_workbook("cols.xlsx", rows, header=header), cfg, replies)
    assert "Nama Sekolah, Kategori or Kelas" in result["reasons"]
    assert "Nama Sekolah, Kategori or Kelas" in (cfg["paths"]["standardized"] / "replies" / "cols.txt").read_text(encoding="utf-8")


def test_one_of_kategori_or_kelas_is_enough(make_workbook, cfg, replies, row):
    header = without("Gategori")
    rows = [[v for c, v in zip(CANON, row()) if c != "Kategori"]]
    assert run(make_workbook("k.xlsx", rows, header=header), cfg, replies)["status"] == "ok"


def test_many_rows_in_error_flag_the_file_but_do_not_reject_it(make_workbook, cfg, replies, row):
    rows = [row(NISN=3000000000 + i) for i in range(6)] + [row(NISN=None) for _ in range(4)]   # 40 percent in error
    result = run(make_workbook("flag.xlsx", rows), cfg, replies)
    assert result["status"] == "flagged" and result["error_share"] == 0.4
    assert (cfg["paths"]["standardized"] / "flag.csv").exists()


def test_a_few_rows_in_error_stay_ok(make_workbook, cfg, replies, row):
    rows = [row(NISN=3000000000 + i) for i in range(9)] + [row(NISN=None)]   # 10 percent
    result = run(make_workbook("few.xlsx", rows), cfg, replies)
    assert result["status"] == "ok" and result["errors"] == 1
    assert "NISN belum diisi, baris 11" in (cfg["paths"]["standardized"] / "replies" / "few.txt").read_text(encoding="utf-8")


def test_status_tables_follow_the_latest_run(tmp_path, make_workbook, cfg, replies, row):
    out = cfg["paths"]["standardized"]
    good = make_workbook("same.xlsx", [row()])
    assert run(good, cfg, replies)["status"] == "ok" and (out / "same.csv").exists()
    good.write_bytes(b"damaged")                                  # the sender replaces it with a broken file
    assert run(good, cfg, replies)["status"] == "rejected"
    assert not (out / "same.csv").exists() and not (out / "same.review.csv").exists()
    status = pd.read_csv(out / "status.csv", dtype=str)
    assert list(status["source_file"]) == ["same.xlsx"] and list(status["status"]) == ["rejected"]
    assert list(pd.read_csv(out / "rejected.csv")["source_file"]) == ["same.xlsx"]


def test_a_file_is_skipped_until_it_changes(make_workbook, cfg, replies, row):
    path = make_workbook("s.xlsx", [row()])
    assert not is_done(cfg["paths"]["standardized"], path)
    run(path, cfg, replies)
    assert is_done(cfg["paths"]["standardized"], path)
    later = time.time() + 60
    os.utime(path, (later, later))
    assert not is_done(cfg["paths"]["standardized"], path)


def test_rename_headers_reports_missing_columns_with_a_code(make_workbook, cfg):
    from registration.readers import read_workbook
    df, issues = rename_headers(read_workbook(make_workbook("h.xlsx", [[1] * 16], header=without("Sesi"))), cfg)
    assert [(i.column, i.code) for i in issues] == [("Sesi", "missing_column")]
