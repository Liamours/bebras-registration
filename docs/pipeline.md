# Pipeline

## Stages

| # | Stage | Reads | Writes |
|---|---|---|---|
| 1 | Standardize | Registration workbooks | `standardized/` |
| 2 | Deduplicate | `standardized/` | `deduplicated/` and a duplicate report |
| 3 | Format and partition | `deduplicated/` | `submit_ready/<school>/` |

The directories are set in `configs/default.yaml`. Each stage reads the output of the one before and never changes it.

## 1. Standardize

- Read every sheet row that has a Kategori, and stop at the instruction block.
- Map headers to the canonical column names.
- Normalize values to the lists in [input-template.md](input-template.md): case, spacing, spelling variants.
- Names in normal case with single spaces; academic titles are not part of a student name.
- Phone numbers as digits only, in the `08...` form.
- Map each school name to one canonical name through a reference table of names and aliases. A name that matches nothing is reported, not guessed.
- Missing or unknown values are written as `-`.
- Keep the source file name and row number on every row.

## 2. Deduplicate

- Key: NISN, kept as text with leading zeros. A student without a NISN carries `kode_biro_XXXXX` as the key.
- The same key twice within one school: keep the more complete row and list the other in the report.
- The same key under two schools: no automatic choice; both rows go to the report for a decision.
- A second check on normalized name plus school catches one student entered twice under different keys.
- Every dropped row stays traceable to its source file and row number.

## 3. Format and partition

- One file per school, named `<school>-<YYYYMMDD>.xlsx`, in the website's upload format.
- A school that sends more students later gets a new dated file with only the new students. Earlier files are not edited.
- One school with several senders stays one school.

## Review report and overrides

The code never guesses on an unclear value. Each stage writes `<name>.review.csv` with one line per issue: source file, source row, column, value, reason and severity.

- `error`: the school's output is held until the row is resolved (unknown value, missing NISN, Kategori that does not match Kelas).
- `warning`: the output is written and the line is listed (a spelling variant fixed automatically, a padded NISN).

A row is resolved in one of three ways. A pattern that repeats across files becomes a rule in `configs/default.yaml`. A single case becomes one line in the overrides file: `source_file,row,column,new_value,reason`, where the new value `__drop__` removes the row. A case that needs the sender is clarified with them first, then recorded as an override.

Overrides apply to the raw cell values before normalization, so an override value is normalized and checked like any other. Overrides that match no row are reported.

## Module layout

| Module | Responsibility |
|---|---|
| `readers` | Open a workbook, find the table, return raw rows |
| `standardize` | Header mapping, value normalization and checks |
| `overrides` | One-off fixes applied before normalization |
| `review` | Issue records and the review report |
| `schools` | Canonical school names and aliases |
| `dedup` | Keys, duplicate detection, report |
| `partition` | Split per school and write upload files |
| `cli` | Command line entry point, progress and logging |

Each module takes a table and returns a table, so modules can be written and tested separately.

## Runs

Each stage logs rows in and rows out, writes a log file, and records finished files as it goes so that a rerun continues where it stopped.
