import pandas as pd
import pytest

from registration import report
from registration.cli import cmd_report

STUDENTS = pd.DataFrame(
    [["a", "SMP", "Penggalang", "Kota Bandung", "A", "False", "a.xlsx"], ["a", "SMP", "Penggalang", "Kota Bandung", "B", "False", "a.xlsx"],
     ["b", "SMA", "Penegak", "other", "A", "True", "b.xlsx"], ["c", "SMA", "Penegak", "other", "A", "False", "c.xlsx"]],
    columns=["school_slug", "Jenjang Sekolah", "Kategori", "Kota/Kabupaten", "Sesi", "has_error", "source_file"],
)
FILES = pd.DataFrame({"status": ["ok", "ok", "flagged", "rejected"]})


def test_statistics_count_schools_students_groups_files_and_held():
    table = report.statistics(STUDENTS, FILES)
    value = {(r["metric"], r["group"]): r["value"] for _, r in table.iterrows()}
    assert value[("schools", "")] == 3 and value[("students", "")] == 4
    assert value[("students_per_jenjang", "SMP")] == 2 and value[("students_per_kategori", "Penegak")] == 2
    assert value[("students_per_region", "Kota Bandung")] == 2 and value[("students_per_sesi", "A")] == 3
    assert (value[("files_received", "")], value[("files_ok", "")], value[("files_flagged", "")], value[("files_rejected", "")]) == (4, 2, 1, 1)
    assert (value[("files_held", "")], value[("schools_held", "")]) == (1, 1)  # one student with an error holds its file and its school
    assert report.summary(table).startswith("3 schools, 4 students.") and "4 received, 1 flagged, 1 rejected, 1 held; 1 schools held" in report.summary(table)


def test_report_command_writes_the_csv_and_the_summary_and_says_what_is_missing(cfg):
    with pytest.raises(SystemExit):
        cmd_report(None, cfg)  # dedup has not run
    cfg["paths"]["deduplicated"].mkdir()
    STUDENTS.to_csv(cfg["paths"]["deduplicated"] / "students.csv", index=False)
    FILES.assign(source_file=["a", "b", "c", "d"]).to_csv(cfg["paths"]["standardized"] / "status.csv", index=False)
    cmd_report(None, cfg)
    assert (cfg["paths"]["deduplicated"] / "statistics.csv").exists()
    assert (cfg["paths"]["deduplicated"] / "statistics.txt").read_text(encoding="utf-8").startswith("3 schools, 4 students.")
