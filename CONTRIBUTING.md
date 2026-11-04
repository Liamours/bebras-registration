# Contributing

## Workflow

1. Pick one small piece of work, for example one pipeline stage or one cleaning rule.
2. Create a branch from `main`: `feature/<short-name>` or `fix/<short-name>`.
3. Commit in small steps. Write each message as a short statement of what changed, for example `Map header variants to canonical column names`.
4. Run the checks (below) before opening a pull request.
5. Ask the other contributor to review. Merge after one approval.

Two people should not edit the same module at the same time. Agree on who owns which module in the pull request or issue before starting.

## Checks

```bash
uv run python -m pytest
```

Every non-trivial rule (a mapping, a key, a parser) has at least one test that fails when the rule breaks. Tests use invented rows only.

## Code style

- Python 3.12, `pathlib.Path` for every path, UTF-8 stated explicitly when reading or writing text files.
- One responsibility per function and per module. Reuse existing functions before writing new ones.
- Paths, column names, accepted values and thresholds come from `configs/default.yaml`.
- Loops over files or rows show progress with `tqdm`. Print only progress, results and errors.
- Comments explain why, only where the reason is not obvious.
- Names say what a thing does. Avoid `new`, `final`, `v2`, `tmp`.
- No emoji in code, comments or messages.

## Data and privacy

- Never commit registration files, exports, or anything copied from them.
- Keep input files untouched. Every stage writes a new file and leaves its input as it was.
- Each stage logs the number of rows read and written, and each dropped row stays traceable to its source file and row number.

## Long runs

A run that processes many files has an estimated time, a log file, and can resume: finished files are recorded as they complete, so a second run continues where the first stopped.
