import pandas as pd
import pytest

from registration import intake

SHEET = """Timestamp,Email Address,Nama Pembina,Status Pembina,Nomor WA Pembina,Nama Sekolah,Upload Formulir Pendaftaran
01/11/2026 10:00:00,a@example.com,Sender One,Guru,081200000001,SMP Contoh,https://drive.google.com/open?id=AAA111
01/11/2026 11:00:00,b@example.com,Sender Two,Orangtua,081200000002,SD Contoh,https://drive.google.com/open?id=BBB222
01/11/2026 12:00:00,c@example.com,Sender Three,Guru,081200000003,SMA Contoh,
"""
XLSX = b"PK\x03\x04 fake workbook bytes"
HEADERS = {"Content-Disposition": "attachment; filename=\"School A.xlsx\"; filename*=UTF-8''School%20A.xlsx"}


def fake_fetch(url):
    if "AAA111" in url:
        return XLSX, HEADERS
    return b"<html>please sign in</html>", {}                       # a file that is not shared


def test_sheet_links_become_csv_links():
    csv = "https://docs.google.com/spreadsheets/d/SHEETID/export?format=csv&gid=7"
    assert intake.sheet_csv_url("https://docs.google.com/spreadsheets/d/SHEETID/edit?gid=7#gid=7") == csv
    assert intake.sheet_csv_url(csv) == csv
    assert intake.sheet_csv_url("https://docs.google.com/spreadsheets/d/SHEETID/edit").endswith("export?format=csv")
    with pytest.raises(ValueError):
        intake.sheet_csv_url("https://example.com")


def test_file_ids_and_names():
    assert intake.file_id("https://drive.google.com/open?id=AAA-1_b") == "AAA-1_b"
    assert intake.file_id("https://drive.google.com/file/d/XYZ789/view") == "XYZ789"
    assert intake.file_id("no link") is None
    assert intake.file_name(HEADERS, "AAA111") == "School A.xlsx"
    assert intake.file_name({}, "AAA111") == "AAA111.xlsx"
    assert "/" not in intake.file_name({"Content-Disposition": 'attachment; filename="a/b.xlsx"'}, "x")


def test_first_column_header_may_be_edited(cfg):
    results = intake.run(cfg, SHEET.replace("Timestamp,", "ddd,", 1), fetch=False)
    assert [r["timestamp"] for r in results] == ["01/11/2026 10:00:00", "01/11/2026 11:00:00"]


def test_listing_downloads_nothing(cfg):
    results = intake.run(cfg, SHEET, fetch=False, fetcher=lambda url: pytest.fail("must not download"))
    assert [(r["outcome"], r["school"]) for r in results] == [("new", "SMP Contoh"), ("new", "SD Contoh")]    # the row without a link is skipped
    assert not cfg["intake"]["target_dir"].exists()


def test_fetch_saves_files_records_state_and_sender_and_retries_failures(cfg):
    results = intake.run(cfg, SHEET, fetch=True, fetcher=fake_fetch)
    assert [(r["outcome"], r.get("saved_as")) for r in results] == [("fetched", "School A.xlsx"), ("failed", None)]
    assert "sign-in" in results[1]["error"]
    assert (cfg["intake"]["target_dir"] / "School A.xlsx").read_bytes() == XLSX
    state = pd.read_csv(cfg["intake"]["state_file"], dtype=str)
    assert list(state["file_id"]) == ["AAA111"]                                  # the failed file is not marked done
    routing = pd.read_csv(cfg["paths"]["routing"], dtype=str)
    assert list(routing["submitter_role"]) == ["teacher"] and list(routing["school_slug"]) == ["smp_contoh"]
    assert list(routing["source_file"]) == ["School A.xlsx"] and routing.iloc[0]["cp_name"] == "-"

    again = intake.run(cfg, SHEET, fetch=True, fetcher=fake_fetch)               # a rerun only retries what failed
    assert [r["file_id"] for r in again] == ["BBB222"]


def test_parent_role_and_unknown_role(cfg):
    sheet = SHEET.replace("Orangtua", "Tetangga")
    intake.run(cfg, sheet, fetch=True, fetcher=lambda url: (XLSX, {"Content-Disposition": 'attachment; filename="x.xlsx"'}))
    roles = list(pd.read_csv(cfg["paths"]["routing"], dtype=str)["submitter_role"])
    assert roles == ["teacher", "unknown"]


def test_an_existing_file_is_never_overwritten(cfg):
    cfg["intake"]["target_dir"].mkdir(parents=True)
    (cfg["intake"]["target_dir"] / "School A.xlsx").write_bytes(b"older file")
    intake.run(cfg, SHEET, fetch=True, fetcher=fake_fetch)
    assert (cfg["intake"]["target_dir"] / "School A.xlsx").read_bytes() == b"older file"
    assert (cfg["intake"]["target_dir"] / "School A-AAA111.xlsx").read_bytes() == XLSX


def test_a_google_sheet_is_exported_when_it_cannot_be_downloaded(cfg):
    calls = []

    def fetch(url):
        calls.append(url)
        if "export?format=xlsx" in url:
            return XLSX, {}
        raise OSError("HTTP Error 404: Not Found")  # a native Google Sheet has no file to download

    results = intake.run(cfg, SHEET, fetch=True, fetcher=fetch)
    assert [r["outcome"] for r in results] == ["fetched", "fetched"] and any("export?format=xlsx" in c for c in calls)
