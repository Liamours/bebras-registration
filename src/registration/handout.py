"""Account handouts: one Excel file and one PDF per companion (teacher or parent) with the usernames and passwords of the students that person handles.

A companion is the person the list is sent to, so students are grouped by the companion's phone number (the number the files go to) and,
when a student has no phone number, by the companion's name. The input is the newest export of the site, because older exports hold
usernames and passwords that no longer exist.
"""
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from fpdf import FPDF
from tqdm import tqdm

from registration.audit import first_phone, read_site

ACCOUNT_COLUMNS = ["Sekolah", "Nama Lengkap", "Kelas", "Kategori", "Sesi", "Username", "Password"]
CATEGORY_ORDER = {"SiKecil": 0, "Siaga": 1, "Penggalang": 2, "Penegak": 3}
QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def companion_key(row: pd.Series) -> str:
    phone = first_phone(row["No Kontak Pendamping"])
    return phone if len(phone) >= 9 else "name_" + letters(row["Pendamping"])


def groups(site: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """One table per companion key, students sorted by school, category, class and name."""
    table = site.assign(key=site.apply(companion_key, axis=1), order=site["Kategori"].map(CATEGORY_ORDER).fillna(9), grade=pd.to_numeric(site["Kelas"], errors="coerce").fillna(0))
    table = table.sort_values(["Sekolah", "order", "grade", "Nama Lengkap"])
    return {key: part[ACCOUNT_COLUMNS + ["Pendamping", "No Kontak Pendamping"]].reset_index(drop=True) for key, part in table.groupby("key", sort=True)}


def companion_names(part: pd.DataFrame) -> list[str]:
    """The names written for the companion, most frequent first."""
    return list(part["Pendamping"].str.strip().value_counts().index)


def file_stem(key: str, part: pd.DataFrame) -> str:
    return f"{slug(companion_names(part)[0])}-{key}" if not key.startswith("name_") else slug(companion_names(part)[0])


def write_excel(path: Path, part: pd.DataFrame, header: dict) -> None:
    """Sheet Akun holds the accounts (text cells, so a password with a leading zero keeps it); sheet Info names the companion and the schools."""
    info = pd.DataFrame({"Keterangan": ["Pendamping", "No kontak", "Sekolah", "Jumlah peserta", "Situs"],
                         "Isi": [" / ".join(companion_names(part)), header["phone"], " / ".join(part["Sekolah"].drop_duplicates()), len(part), header["site_url"]]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        part[ACCOUNT_COLUMNS].astype(str).to_excel(writer, sheet_name="Akun", index=False)
        info.astype(str).to_excel(writer, sheet_name="Info", index=False)
        for sheet in writer.book.worksheets:
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(max(len(str(c.value or "")) for c in column) + 2, 60)
                for cell in column:
                    cell.number_format = "@"


def pdf_text(text) -> str:
    """The core PDF fonts are Latin-1: curly quotes and dashes become plain ones, anything else is shown as ?."""
    return str(text).translate(QUOTES).encode("latin-1", "replace").decode("latin-1")


def write_pdf(path: Path, part: pd.DataFrame, header: dict) -> None:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 7, pdf_text(header["title"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)
    pdf.multi_cell(0, 5, pdf_text(f"Pendamping: {' / '.join(companion_names(part))}   No kontak: {header['phone']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, pdf_text(f"Jumlah peserta: {len(part)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 5, pdf_text(header["intro"].format(site_url=header["site_url"])), align="L", new_x="LMARGIN", new_y="NEXT")
    for school, students in part.groupby("Sekolah", sort=False):
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 6, pdf_text(f"{school} ({len(students)} peserta)"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        with pdf.table(col_widths=(8, 52, 12, 24, 10, 28, 24), text_align=("RIGHT", "LEFT", "CENTER", "LEFT", "CENTER", "LEFT", "LEFT")) as table:
            heading = table.row()
            for name in ("No", "Nama Lengkap", "Kelas", "Kategori", "Sesi", "Username", "Password"):
                heading.cell(name)
            for number, (_, s) in enumerate(students.iterrows(), 1):
                row = table.row()
                for value in (number, s["Nama Lengkap"], s["Kelas"], s["Kategori"], s["Sesi"], s["Username"], s["Password"]):
                    row.cell(pdf_text(value))
    pdf.output(str(path))


def make_handouts(cfg: dict, export: Path, now: datetime | None = None) -> tuple[Path, int, int]:
    """Write the two files of every companion into a new folder `<accounts>/<handout folder>/<YYYYMMDD-HHMM>/`; returns the folder, the companions and the students."""
    settings = cfg["handout"]
    site = read_site(export)
    needed = [c for c in ACCOUNT_COLUMNS + ["Pendamping", "No Kontak Pendamping"] if c not in site.columns]
    if needed:
        raise SystemExit(f"{export.name} has no column {', '.join(needed)}")
    out = cfg["paths"]["accounts"] / settings["folder"] / f"{now or datetime.now():%Y%m%d-%H%M}"
    out.mkdir(parents=True, exist_ok=False)
    parts = groups(site)
    stems = {}
    for key, part in tqdm(parts.items(), desc="companions", unit="companion"):
        stem = file_stem(key, part)
        if stem in stems:  # two companions with one name and different numbers keep apart
            stem = f"{stem}-{key}"
        stems[stem] = key
        header = {"phone": key if not key.startswith("name_") else "-", "title": settings["title"], "intro": settings["intro"], "site_url": settings["site_url"]}
        write_excel(out / f"{stem}.xlsx", part, header)
        write_pdf(out / f"{stem}.pdf", part, header)
    return out, len(parts), len(site)
