# Operations guide

The routine while registration is open. Every command runs from the repository folder with `uv run python -m registration ...`. The data directories are set in `configs/default.yaml`; none of them is part of the repository.

## The routine

1. **Collect.** Put new workbooks in the raw directory. Files from the submission form are fetched with `intake` (below). Files that arrive by other channels are copied in by hand and keep the name they arrived with; a sub-folder per source is fine. Raw files are never edited.
2. **Standardize.** `standardize <raw directory>` checks every workbook that is new or changed. Each file prints one line: status, rows, errors, warnings.
3. **Read the reports.** See "Reading the output".
4. **Resolve.** For each problem choose one of three ways (below), then run `standardize` again.
5. **Deduplicate and partition.** `dedup` writes the report of repeated keys and gives a key to a student without a NISN; read `duplicates.csv` and settle each `same_key_two_schools` and `same_key_different_names` line with the senders (a NISN belongs to one student, so one of the values is wrong), and read `school_review.csv`: a school that matches nothing gets a line (with close names, never applied), and a typed city that contradicts the school's region is reported. When a school has no error left, `partition` (which runs `dedup` first) writes its upload file.
6. **Upload.** Upload the files of `submit_ready/<school>/` to the registration website, then record them with `mark-uploaded`.
7. **Status.** `status` writes `school_status.csv` so that it is clear which school is held, ready or uploaded.

## Intake

```bash
uv run python -m registration intake --sheet-url "<link of the response sheet>"
uv run python -m registration intake --sheet-url "<link of the response sheet>" --fetch
```

The first command only lists new submissions. The second downloads them into the raw directory, records them in `intake_state.csv` and adds the sender to the routing table. The link can be set once in `REGISTRATION_SHEET_URL`.

A line marked `failed` was not downloaded; the usual reason is that the link is not shared with the account that runs the command ("not an xlsx file (the link may need a sign-in ...)"). Download that file by hand into the raw directory. A failed file is retried on the next run.

## Rules of the files

- The tables of `standardized/` are named after the workbook. `standardize` stops when two workbooks have the same name, or a name that collides with a status table, and tells you to rename one of them. Files that are not `.xlsx` (`.xls`, `.xlsm`, `.ods`) are listed as not read; ask the sender for an `.xlsx`.
- A file is redone when it changed, and also when the overrides file or the configuration is newer than its last run.
- `reference/overrides.csv` and `reference/assigned_keys.csv` are the memory of the project (the one-off fixes and the keys given to students without a NISN). They are not regenerated and not part of the repository: keep a copy, because deleting `assigned_keys.csv` renumbers the students without a NISN.
- `partition` leaves out every NISN that is in an earlier upload file of the school, whether or not the file was uploaded. To cut a student again, move the earlier file out of the school's folder.

## Reading the output

All files go to the standardized directory.

| File | Meaning |
|---|---|
| `status.csv` | One line per workbook: `ok`, `flagged` (more than 30 percent of rows have an error, look first) or `rejected` |
| `rejected.csv` | The rejected workbooks and why |
| `<name>.csv` | The standardized table of one workbook |
| `<name>.review.csv` | One line per issue: row, column, value, code, reason, severity |
| `replies/<name>.txt` | A draft message to the sender (Indonesian) for the errors of that file |
| `school_status.csv` | One line per school, from `status` |

A line of a review report:

| source_file | source_row | column | value | code | reason | severity |
|---|---|---|---|---|---|---|
| school.xlsx | 7 | Kategori | Siaga | kategori_mismatch | does not match Kelas 8 (expected Penggalang) | error |

`source_row` is the row number in the sender's Excel file. An `error` holds the school's output until it is resolved; a `warning` is listed only. The codes are explained in [standardization.md](standardization.md).

Always open `rejected.csv` and the `flagged` files first: a rejected file produces no table, and a flagged file usually has one repeating cause.

## Resolving a problem

| Kind | Example | What to do |
|---|---|---|
| Repeats across files | A new spelling of a value, a header typo | Add it to `configs/default.yaml` (`value_maps`, `header_aliases`) and add a test, then `standardize <raw directory> --force` |
| One case | One wrong NISN that the sender confirmed, one row to drop | Add one line to the overrides file, then `standardize <that file> --force` |
| Needs the sender | Missing NISN, a student entered under the wrong category | Send the draft from `replies/`, wait for the corrected file. Nothing is sent by the code |

The overrides file has the columns `source_file,row,column,new_value,reason`. The new value `__drop__` removes the row. An override value goes through the normal checks. Overrides that match no row are reported as a warning, which also catches an override that outlived a corrected file.

```csv
source_file,row,column,new_value,reason
school.xlsx,7,Kategori,Penggalang,confirmed by the sender
school.xlsx,9,Nama Lengkap,__drop__,duplicate of row 4
```

### When to use `--force`

A file is skipped while it has not changed since its last run. A changed file is processed again without any flag. Use `--force` only after changing the overrides or the configuration, which the skip rule cannot see.

## Partition and upload

```bash
uv run python -m registration partition
uv run python -m registration partition --kategori SiKecil,Siaga
uv run python -m registration mark-uploaded school-20261105-1000.xlsx
uv run python -m registration status
```

Read `partition_report.csv` after every run. `written` is a new upload file; `held` is a school with errors or a repeated NISN (the reason is in the report); `nothing_new` is a school whose students are all in earlier files.

- Files are named `<school>-<YYYYMMDD-HHMM>.xlsx`. A school that sends more students later gets a new file with only those students.
- To rebuild a file, delete it, fix the cause, and run `partition` again. Students already in another file of that school are left out, so a rebuilt file must be the only one that holds them.
- Check an upload file once in Excel before the first upload: header in row 1, NISN and phone as text, no example or instruction rows.

## Common situations

| Situation | Reason | What to do |
|---|---|---|
| A workbook has no `.csv` in the standardized directory | It was rejected | Open `rejected.csv` |
| Every row of a file has `missing_nisn` | The previous template | The file is rejected unless `--accept-old-template` is set (for tests on earlier data only) |
| `partition` holds a school with "repeated NISN" | The same NISN is in two rows of the batch | Decide which row is right, then add an override or wait for the corrected file |
| `partition` says `nothing_new` for a school that has new students | The new students are in an earlier file | Check the earlier file's name and date |
| `intake` lists a row but fetches nothing | The file is not shared | Download it by hand |
| A configuration change has no effect | The file was skipped | Add `--force` |
