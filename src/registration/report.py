"""Registration statistics from the deduplicated table and the status tables."""
import pandas as pd

COLUMNS = ["metric", "group", "value"]
BREAKDOWNS = [("students_per_jenjang", "Jenjang Sekolah"), ("students_per_kategori", "Kategori"), ("students_per_region", "Kota/Kabupaten"), ("students_per_sesi", "Sesi")]


def statistics(students: pd.DataFrame, files: pd.DataFrame, partition_report: pd.DataFrame) -> pd.DataFrame:
    """One line per figure: schools and students, students per jenjang, kategori, region and Sesi, files received, flagged and rejected, schools held."""
    rows = [["schools", "", students["school_slug"].nunique()], ["students", "", len(students)]]
    for metric, column in BREAKDOWNS:
        rows += [[metric, group, n] for group, n in students[column].value_counts().sort_index().items()]
    rows.append(["files_received", "", len(files)])
    rows += [[f"files_{state}", "", n] for state, n in files["status"].value_counts().sort_index().items()]
    held = int((partition_report["state"] == "held").sum()) if len(partition_report) else 0
    rows.append(["schools_held", "", held])
    return pd.DataFrame(rows, columns=COLUMNS)


def summary(table: pd.DataFrame) -> str:
    def one(metric):
        return int(table.loc[(table["metric"] == metric) & (table["group"] == ""), "value"].sum())

    def split(metric):
        part = table[table["metric"] == metric]
        return ", ".join(f"{g} {v}" for g, v in zip(part["group"], part["value"]))

    return (f"{one('schools')} schools, {one('students')} students. Jenjang: {split('students_per_jenjang')}. Kategori: {split('students_per_kategori')}. "
            f"Region: {split('students_per_region')}. Sesi: {split('students_per_sesi')}. Files: {one('files_received')} received, "
            f"{one('files_flagged')} flagged, {one('files_rejected')} rejected; {one('schools_held')} schools held.")
