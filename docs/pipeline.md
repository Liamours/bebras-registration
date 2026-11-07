# Pipeline

## Stages

| # | Stage | Command | Reads | Writes |
|---|---|---|---|---|
| 0 | Intake | `intake` | The submission form's response sheet | New workbooks in the raw directory, a state file, a routing table |
| 1 | Standardize | `standardize` | Workbooks in the raw directory | `standardized/`: tables, review reports, reply drafts, status tables |
| S | School list | `school-source`, `school-master` | The ministry's reference pages, earlier workbooks, `standardized/` | `reference/schools_kemendikdasmen.csv`, `reference/school_master.csv` |
| 2 | Deduplicate | `dedup` | `standardized/` | `deduplicated/`: `students.csv`, `duplicates.csv`, `school_review.csv` |
| 3 | Partition | `partition` (runs `dedup` first) | `deduplicated/` | `submit_ready/<school>/` and `partition_report.csv` |
| 5 | Report | `report` | `deduplicated/students.csv`, `standardized/status.csv` | `deduplicated/statistics.csv` |
| 4 | Status | `status`, `mark-uploaded` | Standardized tables, upload files | `school_status.csv`, `uploaded.csv` |

The directories are set in `configs/default.yaml`. Each stage reads the output of the one before and never changes it. Day-to-day use is described in [operations.md](operations.md).

## 0. Intake

- `intake --sheet-url <link>` lists the rows of the response sheet whose file has not been fetched yet. It downloads nothing.
- `intake --sheet-url <link> --fetch` downloads them into the raw directory under the name they arrived with. An existing file is never overwritten (a short id is added to the new name).
- A download that returns something other than an xlsx file (for example a sign-in page, because the file is not shared) is reported and retried on the next run. A file counts as fetched only after it is saved; the state file is written before moving on, so a crash repeats at most one file.
- The sender (name, phone, role) and the source file are added to the routing table. Roles come from the form's status answer: teacher, parent, guardian, school_staff or unknown.
- The sheet link is given on the command line or in `REGISTRATION_SHEET_URL`; it is not stored in the repository.

## 1. Standardize

For every workbook:

1. **Open.** A file that cannot be opened is rejected.
2. **Find the table.** The header row is the row that holds `Nama Lengkap`; the table stops at the instruction block (`Keterangan`). Empty rows are skipped. No header means rejection.
3. **Check the structure.** A file is rejected when a required column is missing (`Nama Lengkap`, `Nama Sekolah`, and `Kategori` or `Kelas`), when it has no `NISN` column (the previous template), or when it has no student rows.
4. **Apply overrides** (see below) and drop the template's two example students.
5. **Normalize** every value and run the checks in [standardization.md](standardization.md).
6. **Write** `<name>.csv`, `<name>.review.csv` and, when there is something to tell the sender, `replies/<name>.txt`.

Row-level problems never reject a file. A file where more than 30 percent of the rows have an error (`flag_error_share`) gets the status `flagged` so that someone looks at it first; it is still written.

`status.csv` holds one line per file (status `ok`, `flagged` or `rejected`, rows, errors, warnings, reasons, time). `rejected.csv` lists the rejected files and their reasons. A rejected file leaves nothing else behind: an older table of the same file is removed. A file is skipped on later runs until it changes; `--force` redoes it after a change of overrides or configuration.

Rejection is for structure only, because a file with many bad rows usually has one repeating cause that a rule or an override fixes for every row.

## 2. Deduplicate

`dedup` reads every processed table of `standardized/` and writes `students.csv` (one row per student, with `has_error` and a `note`), `duplicates.csv` (the report) and `school_review.csv`; the keys it gives are kept in `reference/assigned_keys.csv`. `partition` runs it first, so the upload files are always cut from a fresh table.

- **Key.** NISN, kept as text with leading zeros. A student without a NISN gets `<bureau_code>_NNNNN` (`bureau_code` in the configuration: `telkomuniversity`). The number goes on from the highest one already in the stored keys or in the data. The key given to a row (source file and row) is stored in `reference/assigned_keys.csv`, which is not regenerated, so a rerun gives the same key and a number is never used twice; do not delete that file.
- **The same key twice in one school.** The row with more filled fields is kept (on a tie the earlier file and row). Both rows are listed in the report, the dropped one marked `no`.
- **The same key under two schools.** No automatic choice. Every row stays in `students.csv` with `has_error` set, so `partition` holds both schools, and the rows are listed in the report as `same_key_two_schools`. The decision is made with the senders, through the CP, and recorded in `overrides.csv`: a corrected NISN (`row,NISN,<right NISN>,reason`) or `__drop__` for a row that should not exist. After `standardize --force` and `dedup` the rerun gives the same result, because the override is applied again each time.
- **The same name and school under different keys.** Listed as `same_name_in_school` and kept: it is one student entered twice or two students with one name, and only a person can tell.
- **Traceability.** Every report line carries the source file and row number.

## School list

- `school-source` downloads the schools of Kota Bandung, Kabupaten Bandung, Kabupaten Bandung Barat and Kota Cimahi (SD, SMP, MI, MTs, SMA, SMK, MA, MAK) from the public reference pages of the ministry (`referensi.data.kemendikdasmen.go.id`, Pusdatin Kemendikdasmen) into `reference/schools_kemendikdasmen.csv`: NPSN, name, address, kelurahan, status, jenjang, region, kecamatan and the date of the download. The pages state no license, only the copyright line of Pusdatin; the list is kept in the data folder and not published. A rerun skips the pages already done.
- `school-master` builds `reference/school_master.csv` (school_slug, canonical_name, npsn, jenjang, region, aliases) from that list, `reference/schools_2025.csv` (the schools of the earlier cycle) and the schools of this year's files. A school that is in a file but not in the ministry list is added with the region `other`; the added names are written to `reference/school_master_added.csv` for a look. Spellings seen in files become aliases. `reference/school_aliases.csv` (alias, npsn) holds the aliases decided by hand and is applied on every build. A school that already has an upload folder keeps that folder's slug.
- Canonical names (`schools.py`): `SMPN 1` becomes `SMP Negeri 1`, a digit is split from a letter, acronyms are capitals, other words start with a capital. Two spellings are the same school when their letters and digits agree, so punctuation and case do not matter.
- `dedup` applies the master to every student: the canonical school name, the `school_slug`, and Kota/Kabupaten taken from the region of the school when the region is one of the four above. A school that matches nothing keeps its canonical spelling, and `deduplicated/school_review.csv` lists it with up to three close names. A close name is a suggestion and is never picked. A name shared by several schools (the ministry list leaves the place out of names such as `SD Negeri 1`) is matched only when the typed city or the city at the end of the name leaves one school. For an unknown school a city that names one region is written in full (`Kab. Bandung` becomes `Kabupaten Bandung`), a bare `Bandung` is listed with both candidates, and for a matched school a typed city that contradicts its region is listed as `region_conflict` while the region of the school is written.

## Report

`report` writes `deduplicated/statistics.csv` (metric, group, value) and `statistics.txt` and prints the summary: schools and students, students per jenjang, kategori, region and Sesi, files received, flagged, rejected and held, and schools held. A school is held when one of its students has an error, a file is held when it has such a student.

## 3. Partition

- One file per school, `submit_ready/<school>/<school>-<YYYYMMDD-HHMM>.xlsx`, in the website's upload format: header in row 1 (taken from the official format file when `paths.upload_format` exists, otherwise from the configured columns), students from row 2, `No` numbered again, NISN and phone stored as text, a missing value left empty.
- A school is held, and gets no file, when any of its rows has an error, when a row has a NISN that repeats in the batch, or when its name is missing. The reason is in `partition_report.csv`.
- A school that sends more students later gets a new file with only the students that are in no earlier file of that school. Earlier files are not edited. To rebuild a file, delete it first.
- `--kategori SiKecil,Siaga` writes only those categories, so that categories whose challenge comes first can be uploaded first. The rest follow in a later run as a new file.

## 4. Status

- `status` writes `school_status.csv`: per school the files, students, rows in error and a state. `held`: a row has an error. `ready`: no error and students that are in no uploaded file. `uploaded`: every student is in a file marked as uploaded.
- `mark-uploaded <file>...` records upload files that went to the website (`submit_ready/uploaded.csv`).

## Review report and overrides

The code never guesses on an unclear value. Each file gets `<name>.review.csv` with one line per issue: source file, source row, column, value, code, reason and severity.

- `error`: the school's output is held until the row is resolved.
- `warning`: the output is written and the line is listed (a spelling variant fixed automatically, a padded NISN).

A row is resolved in one of three ways. A pattern that repeats across files becomes a rule in `configs/default.yaml`. A single case becomes one line in the overrides file: `source_file,row,column,new_value,reason`, where the new value `__drop__` removes the row. A case that needs the sender is clarified with them first, then recorded as an override.

Overrides apply to the raw cell values before normalization, so an override value is normalized and checked like any other. Overrides that match no row are reported.

## Reply drafts

Every error code has a message in `configs/replies.yaml` (listed in [reply-templates.md](reply-templates.md)). The draft for a file groups the errors by problem with the row numbers as the sender sees them. Nothing is sent by the code.

## Module layout

| Module | Responsibility |
|---|---|
| `readers` | Open a workbook, find the table, return raw rows |
| `fields` | Names, phone numbers and email addresses |
| `standardize` | Header mapping, value normalization and checks |
| `overrides` | One-off fixes applied before normalization |
| `rejection` | Structural reasons to reject a file, share of rows in error |
| `review` | Issue records and the review report |
| `replies` | Reply drafts from a review report |
| `pipeline` | One workbook from reading to the written outputs |
| `status` | File and school status tables |
| `partition` | Split per school and write upload files |
| `intake` | New submissions from the response sheet |
| `cli` | Command line entry point |
| `schools`, `school_source`, `dedup`, `report` | Canonical school names and regions, the ministry list, keys and duplicates, statistics |

Each stage works on tables, so modules can be written and tested separately.
