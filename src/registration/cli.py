import argparse
from pathlib import Path

import pandas as pd
import yaml
from tqdm import tqdm

from registration.overrides import apply_overrides
from registration.readers import read_workbook
from registration.review import write_report
from registration.standardize import normalize_values, rename_headers

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["paths"] = {k: (ROOT / v).resolve() for k, v in cfg["paths"].items()}
    return cfg


def standardize_file(path: Path, cfg: dict, out_dir: Path) -> tuple[int, int, int]:
    df = read_workbook(path)
    df, issues = rename_headers(df, cfg)
    df, override_issues = apply_overrides(df, cfg["paths"]["overrides"], path.name)
    table, value_issues = normalize_values(df, cfg)
    issues = issues + override_issues + value_issues
    table.to_csv(out_dir / f"{path.stem}.csv", index=False, encoding="utf-8")
    write_report(issues, out_dir / f"{path.stem}.review.csv")
    errors = sum(i.severity == "error" for i in issues)
    return len(table), errors, len(issues) - errors


def main() -> None:
    parser = argparse.ArgumentParser(prog="registration", description="Standardize registration workbooks.")
    parser.add_argument("input", type=Path, help="a workbook or a folder of workbooks")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default.yaml")
    parser.add_argument("--force", action="store_true", help="redo files already done (use after changing overrides or config)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    out_dir = cfg["paths"]["standardized"]
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(args.input.rglob("*.xlsx")) if args.input.is_dir() else [args.input]
    files = [f for f in files if not f.name.startswith("~$")]

    for path in tqdm(files, desc="files", unit="file"):
        done = out_dir / f"{path.stem}.csv"
        if done.exists() and done.stat().st_mtime > path.stat().st_mtime and not args.force:
            continue
        try:
            rows, errors, warnings = standardize_file(path, cfg, out_dir)
        except ValueError as e:
            tqdm.write(f"FAILED {e}")
            continue
        tqdm.write(f"{path.name}: {rows} rows, {errors} errors, {warnings} warnings")
