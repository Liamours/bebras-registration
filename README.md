# registration

Turns the Excel registration files that schools send for Bebras Indonesia Challenge 2026 into clean, deduplicated files ready to upload, one per school.

## What it does

| Stage | Input | Output |
|---|---|---|
| Standardize | Registration workbooks as received | One table with fixed column names, fixed value lists, normal-case names and canonical school names |
| Deduplicate | Standardized table | One row per student (key: NISN) and a report of every duplicate found |
| Format and partition | Deduplicated table | One upload file per school in the website's template format |

Details of each stage are in [docs/pipeline.md](docs/pipeline.md). The columns and accepted values of the input template are in [docs/input-template.md](docs/input-template.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Run everything through the project environment with `uv run`. Packages are added with `uv add <package>`.

## Usage

```bash
uv run python -m registration <workbook or folder>
uv run python -m pytest
```

For each workbook the command writes a standardized table (`<name>.csv`) and a review report (`<name>.review.csv`) to the standardized directory set in `configs/default.yaml`. Finished files are skipped; add `--force` after changing the overrides or the configuration.

## Status

Standardize stage done (reader, header and value normalization, checks, overrides, review report). Next: school names, deduplication, partition.

## Layout

```
configs/default.yaml     paths, column mapping, accepted values
src/registration/        the package
tests/                   tests on invented rows
docs/                    input template and pipeline notes
```

All paths, thresholds and value lists live in `configs/default.yaml`. Nothing is hardcoded in the code.

## Data

Registration files contain personal data (student names, NISN, phone numbers). They are kept outside version control; `.gitignore` excludes them. Never commit a real registration file, a screenshot of one, or an example row copied from one. Use invented rows in tests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
