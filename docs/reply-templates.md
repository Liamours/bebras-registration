# Reply templates

Draft messages in Indonesian for the problems the review report raises. They are written to `replies/<file name>.txt` next to the standardized tables by the `standardize` command and are never sent by the code: a person reads each draft and sends it.

The texts live in `configs/replies.yaml`; this page lists them. A test checks that every code in the file appears here.

Row numbers in a message are the row numbers the sender sees in Excel. Only errors are mentioned; warnings stay in the review report.

## Frame

- Opening (file with errors): Yth. Bapak/Ibu, terima kasih telah mengirimkan file pendaftaran Bebras Indonesia Challenge 2026{school}. Setelah kami periksa, ada hal yang perlu diperbaiki:
- Opening (rejected file): Yth. Bapak/Ibu, terima kasih telah mengirimkan file pendaftaran Bebras Indonesia Challenge 2026{school}. File ini belum dapat kami proses karena:
- Closing: Mohon kirim ulang file yang sudah diperbaiki. Terima kasih.

`{school}` becomes ` dari <school name>` when the file has exactly one school, otherwise it is empty.

## Messages

| Code | When | Message |
|---|---|---|
| `reject_unreadable` | File cannot be opened (not xlsx, damaged, password protected). Whole file rejected. | File tidak dapat dibuka. Mohon simpan ulang dalam format Excel (.xlsx) tanpa kata sandi. |
| `reject_no_table` | No header row with `Nama Lengkap`. Whole file rejected. | Tabel siswa tidak ditemukan. Mohon gunakan templat Excel terbaru, isi data di bawah judul kolom, dan jangan mengubah judul kolom (kolom Nama Lengkap harus ada). |
| `reject_no_rows` | Header found, no student rows. Whole file rejected. | Tidak ada data siswa di dalam file. Mohon isi data siswa pada templat. |
| `reject_missing_column` | A required column is missing (`Nama Lengkap`, `Nama Sekolah`, and `Kategori` or `Kelas`). Whole file rejected. `{columns}` lists them. | Kolom berikut tidak ada pada file: {columns}. Mohon gunakan templat terbaru dan jangan mengubah atau menghapus judul kolom. |
| `reject_old_template` | No `NISN` column: the previous year's template. Whole file rejected. | File menggunakan templat tahun sebelumnya (tanpa kolom NISN). Mohon unduh templat 2026 di https://bit.ly/TantanganBebras2026 dan pindahkan datanya ke templat tersebut. |
| `missing_name` | A student row has no name. | Nama lengkap siswa belum diisi, {rows}. |
| `missing_school` | A student row has no school name. | Nama sekolah belum diisi, {rows}. |
| `missing_nisn` | A student row has no NISN. | NISN belum diisi, {rows}. Isi dengan 10 digit angka. Jika siswa belum memiliki NISN, mohon hubungi kami. |
| `nisn_format` | NISN is not 10 digits and not a bureau code. | NISN harus 10 digit angka dan diformat sebagai teks agar angka 0 di depan tidak hilang, {rows}. |
| `unknown_value` | A value is not in the accepted list of its column (gender, jenjang, bahasa, status, bureau). `{column}` names the column. | Isian pada kolom {column} tidak sesuai pilihan yang tersedia, {rows}. |
| `kelas_invalid` | Kelas is empty, not a number, or outside 0 to 12. | Kelas belum diisi atau bukan angka 0 sampai 12, {rows}. |
| `kategori_mismatch` | Kategori does not match Kelas. | Kategori tidak sesuai dengan kelas, {rows} (SiKecil kelas 1-3, Siaga kelas 4-6, Penggalang kelas 7-9, Penegak kelas 10-12). |
| `sesi_invalid` | Sesi is not a session letter. | Sesi harus berupa huruf A sampai I (atau A1 sampai I1 untuk hari Rabu), {rows}. |
| `sesi_category` | Sesi is not available for the student's category. | Sesi tidak tersedia untuk kategorinya, {rows} (sesi E tidak tersedia untuk SiKecil; sesi A1 sampai I1 hanya untuk Penggalang). |
| `duplicate_nisn` | The same NISN appears more than once (used by the deduplication stage). | NISN sama dengan siswa lain, {rows}. Setiap siswa harus memiliki NISN yang berbeda. |
