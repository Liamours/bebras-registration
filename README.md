# registration

Turns the Excel registration files that schools send for Bebras Indonesia Challenge 2026 into clean, deduplicated files ready to upload, one per school.

## What it does

| Stage | Input | Output |
|---|---|---|
| Intake | The form's response sheet | New workbooks, a record of the sender |
| Standardize | Registration workbooks as received | A table with fixed column names and value lists, a review report, a status line, a reply draft for the sender; a workbook that cannot be read reliably is rejected |
| School list | The ministry's public school list, earlier workbooks, this year's workbooks | A school master: canonical name, NPSN, jenjang, region and aliases |
| Deduplicate | Standardized tables, school master | One row per student (key: NISN, or a bureau key for a student without one), canonical school names and regions, a report of every repeated key or name |
| Partition | Checked tables | One upload file per school in the website's format; schools with open errors are held |
| Status | Tables and upload files | Per school: held, ready or uploaded |
| Report | Deduplicated table, status tables | Registration statistics as a table and a summary |

Reading order: [docs/operations.md](docs/operations.md) for the daily routine, [docs/pipeline.md](docs/pipeline.md) for what each stage does, [docs/standardization.md](docs/standardization.md) for the rules per field, [docs/input-template.md](docs/input-template.md) for the template, [docs/reply-templates.md](docs/reply-templates.md) for the sender messages.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Run everything through the project environment with `uv run`. Packages are added with `uv add <package>`.

## Usage

```bash
uv run python -m registration standardize <workbook or folder>
uv run python -m registration partition [--kategori SiKecil,Siaga]
uv run python -m registration status
uv run python -m registration mark-uploaded <upload file>...
uv run python -m registration intake --sheet-url <link> [--fetch]
uv run python -m pytest
```

`standardize` writes, per workbook, a table (`<name>.csv`), a review report (`<name>.review.csv`) and, when something needs the sender's attention, a reply draft, plus `status.csv` and `rejected.csv`, all in the standardized directory set in `configs/default.yaml`. Finished files are skipped; add `--force` after changing the overrides or the configuration. `intake` only lists new submissions unless `--fetch` is given.

## Status

Done: intake, standardize (checks, rejection, overrides, review report, reply drafts), school list and canonical names with regions, deduplication, partition, status, statistics report.

## Layout

```
configs/default.yaml     paths, column mapping, accepted values, thresholds
configs/replies.yaml     reply texts (Indonesian)
src/registration/        the package
tests/                   tests on invented rows
docs/                    routine, pipeline, rules per field, template, reply texts
```

All paths, thresholds and value lists live in `configs/default.yaml`. Nothing is hardcoded in the code.

## Data

Registration files contain personal data (student names, NISN, phone numbers). They are kept outside version control; `.gitignore` excludes them. Never commit a real registration file, a screenshot of one, or an example row copied from one. Use invented rows in tests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
