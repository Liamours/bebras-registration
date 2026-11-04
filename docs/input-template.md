# Input template

Schools register with an Excel workbook (sheet `Sheet1`). The table sits in the first rows; an instruction block with an orange background sits below it. The block starts at the row whose first cell is `Keterangan`, and schools are asked to delete it. Some leave it in, so the reader stops the table at that row.

## Columns

No, Nama Lengkap, NISN, Email, Kategori, Gender, Kelas, Jenjang Sekolah, Nama Sekolah, Kota/Kabupaten, Nama Pendamping, No Kontak Pendamping, Status Pendamping, Bahasa, Sesi, Nama Biro.

Header names vary between files (case, spacing, typos, a missing column). Headers are mapped to these names through the table in the configuration, never by position.

## Accepted values

| Column | Values |
|---|---|
| NISN | Unique key. A student without a NISN gets `kode_biro_XXXXX`, where XXXXX is a running number |
| Nama Lengkap | Normal case, as it should print on the certificate |
| Kategori | `SiKecil`, `Siaga`, `Penggalang`, `Penegak` |
| Gender | `Laki-laki`, `Perempuan` |
| Kelas | Integer 0 to 12 |
| Jenjang Sekolah | `Preschool`, `SD`, `MI`, `SMP`, `MTs`, `SMA`, `MA`, `SMK`, `MAK` |
| Status Pendamping | `Guru`, `Orang Tua`, `Wali` |
| Bahasa | `Indonesia`, `Inggris` |
| Sesi | Time slot, see below |
| Nama Biro | Name of the bureau where the school registers |

Kategori follows the class: 1 to 3 SiKecil, 4 to 6 Siaga, 7 to 9 Penggalang, 10 to 12 Penegak. Each category takes the challenge on its own day: SiKecil Friday, Siaga Thursday, Penggalang Tuesday and Wednesday, Penegak Monday.

## Sesi

| Sesi | Monday, Tuesday, Thursday, Friday | Wednesday |
|---|---|---|
| A | 07.00 - 08.15 | A1 |
| B | 08.15 - 09.30 | B1 |
| C | 09.30 - 10.45 | C1 |
| D | 10.45 - 12.00 | D1 |
| E | 12.00 - 13.15 (empty on Friday) | E1 |
| F | 13.15 - 14.30 | F1 |
| G | 14.30 - 15.45 | G1 |
| H | 15.45 - 17.00 | H1 |
| I | 17.00 - 18.15 | I1 |

The Wednesday slots use the same times as the letters without the `1`.

## Known irregularities

- Value variants in case and spelling: `penggalang`, `BANDUNG`, `laki laki`, `L`, `P`, `Sekolah dasar(SD)`.
- Class written as `7A`, `VIII` or `7.0`.
- NISN stored as a number, which drops a leading zero. It is read as text.
- Nama Biro written in several ways for the same bureau.
- Instruction block left in the file.
