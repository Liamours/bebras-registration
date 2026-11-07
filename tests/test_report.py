import pandas as pd

from registration import report


def test_statistics_count_schools_students_groups_and_files():
    students = pd.DataFrame(
        [["a", "SMP", "Penggalang", "Kota Bandung", "A"], ["a", "SMP", "Penggalang", "Kota Bandung", "B"], ["b", "SMA", "Penegak", "other", "A"]],
        columns=["school_slug", "Jenjang Sekolah", "Kategori", "Kota/Kabupaten", "Sesi"],
    )
    files = pd.DataFrame({"status": ["ok", "ok", "flagged", "rejected"]})
    part = pd.DataFrame({"state": ["written", "held", "held"]})
    table = report.statistics(students, files, part)
    value = {(r["metric"], r["group"]): r["value"] for _, r in table.iterrows()}
    assert value[("schools", "")] == 2 and value[("students", "")] == 3
    assert value[("students_per_jenjang", "SMP")] == 2 and value[("students_per_kategori", "Penegak")] == 1
    assert value[("students_per_region", "Kota Bandung")] == 2 and value[("students_per_sesi", "A")] == 2
    assert (value[("files_received", "")], value[("files_ok", "")], value[("files_flagged", "")], value[("files_rejected", "")], value[("schools_held", "")]) == (4, 2, 1, 1, 2)
    assert report.summary(table).startswith("2 schools, 3 students.") and "4 received, 1 flagged, 1 rejected; 2 schools held" in report.summary(table)
