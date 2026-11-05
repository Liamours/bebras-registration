# Contributing

## Workflow

1. Pick one small piece of work, for example one pipeline stage or one cleaning rule.
2. Work on **one branch at a time**, created from the latest `main` and named `feature/<short-name>` or `fix/<short-name>`. Finish it (merged or dropped) before starting another.
3. Commit in small steps. Write each message as a short statement of what changed, for example `Map header variants to canonical column names`.
4. Run the checks (below) before opening a pull request.
5. Open one pull request for the branch and ask the other contributor to review. Merge after one approval, keeping the history linear (squash or rebase).
6. The branch is deleted at the merge (the repository does it automatically). Pull `main` and delete your local copy of the branch.

Two people should not edit the same module at the same time. Agree on who owns which module in the pull request or issue before starting.

## Keeping the repository tidy

These rules apply to every contributor, always.

- **One branch.** At most one working branch besides `main` per contributor.
- **No pull request open for long.** A pull request is reviewed and merged, or closed, within two days. If it needs longer, it is too big: split it.
- **No branch open for long.** A branch is merged or deleted within three days of its last commit. A merged branch is deleted at once.
- **Tidy files.**
  - Only source, tests, configuration and documentation are committed. No scratch files, exports, logs, caches, data or screenshots of data.
  - Each folder holds one kind of thing: code in `src/`, tests in `tests/`, notes in `docs/`, settings in `configs/`.
  - Delete what is no longer used (file, function, option) instead of commenting it out or keeping a copy under a new name.
  - Change the documentation in the same pull request as the code it describes.
- **Before opening a pull request:** `git status` is clean and `git branch -a` shows only `main` and the branch you are on.

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
