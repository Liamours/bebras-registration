import argparse
import os
from pathlib import Path

import yaml
from tqdm import tqdm

import pandas as pd

from registration import dedup, intake, partition as partition_mod, report as report_mod, schools, school_source, status
from registration.pipeline import is_done, process_file
from registration.replies import load_replies

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["paths"] = {k: (ROOT / v).resolve() for k, v in cfg["paths"].items()}
    for key in ("target_dir", "state_file"):
        cfg["intake"][key] = (ROOT / cfg["intake"][key]).resolve()
    return cfg


def cmd_standardize(args, cfg):
    out_dir = cfg["paths"]["standardized"]
    out_dir.mkdir(parents=True, exist_ok=True)
    replies = load_replies(args.replies)
    files = sorted(args.input.rglob("*.xlsx")) if args.input.is_dir() else [args.input]
    files = [f for f in files if not f.name.startswith("~$")]
    counts: dict[str, int] = {}
    for path in tqdm(files, desc="files", unit="file"):
        if is_done(out_dir, path) and not args.force:
            continue
        row = process_file(path, cfg, replies, out_dir, args.accept_old_template)
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        tqdm.write(f"{row['source_file']}: {row['status']}, {row['rows']} rows, {row['errors']} errors, {row['warnings']} warnings"
                   + (f" ({row['reasons']})" if row["reasons"] else ""))
    print("processed:", counts or "nothing new")


def cmd_school_source(args, cfg):
    rows = school_source.build(cfg, cfg["paths"]["school_source"], cfg["paths"]["school_source_state"], print)
    print(f"{rows} school rows written to {cfg['paths']['school_source']}")


def cmd_school_master(args, cfg):
    ref = cfg["paths"]["school_master"].parent
    portal = pd.read_csv(cfg["paths"]["school_source"], dtype=str).fillna("")
    seen = pd.read_csv(ref / "schools_2025.csv", dtype=str).fillna("")
    current = partition_mod.load_checked(cfg["paths"]["standardized"])
    if not current.empty:  # the schools of this year's files, with the jenjang and city their senders wrote
        now = current.groupby("Nama Sekolah").agg(jenjang=("Jenjang Sekolah", "first"), city=("Kota/Kabupaten", "first")).reset_index().rename(columns={"Nama Sekolah": "name"})
        seen = pd.concat([seen, now], ignore_index=True)
    aliases_path = ref / "school_aliases.csv"
    hand = pd.read_csv(aliases_path, dtype=str).fillna("") if aliases_path.exists() else pd.DataFrame(columns=["alias", "npsn"])
    folders = cfg["paths"]["submit_ready"]
    existing = {p.name.replace("_", ""): p.name for p in folders.iterdir() if p.is_dir()} if folders.exists() else {}
    master, added = schools.build_master(portal, seen, hand, existing)
    master.to_csv(cfg["paths"]["school_master"], index=False, encoding="utf-8")
    added.to_csv(ref / "school_master_added.csv", index=False, encoding="utf-8")
    print(f"{len(master)} schools in the master; {len(added)} seen in registration files but not in the ministry list (region other):")
    print(added.to_string(index=False) if len(added) else "none")


def cmd_report(args, cfg):
    out = cfg["paths"]["deduplicated"]
    status_path = cfg["paths"]["standardized"] / "status.csv"
    if not (out / "students.csv").exists() or not status_path.exists():
        raise SystemExit("nothing to report yet: run standardize and dedup first")
    students = pd.read_csv(out / "students.csv", dtype=str).fillna("")
    table = report_mod.statistics(students, pd.read_csv(status_path, dtype=str))
    table.to_csv(out / "statistics.csv", index=False, encoding="utf-8")
    text = report_mod.summary(table)
    (out / "statistics.txt").write_text(text + chr(10), encoding="utf-8")
    print(text)


def cmd_dedup(args, cfg):
    students, duplicates = dedup.deduplicate(cfg)
    print(f"{len(students)} students kept")
    if not duplicates.empty:
        print(duplicates.groupby(["check", "kept"]).size().to_string())


def cmd_partition(args, cfg):
    dedup.deduplicate(cfg)  # the upload files are always cut from a fresh deduplicated table
    report = partition_mod.partition(cfg, args.kategori.split(",") if args.kategori else None)
    print(report["state"].value_counts().to_string() if not report.empty else "no checked files")
    held = report[report["state"] == "held"]
    for _, r in held.iterrows():
        print(f"held: {r['school']} ({r['reason']})")


def cmd_status(args, cfg):
    table = status.school_status(cfg["paths"]["standardized"], cfg["paths"]["submit_ready"], partition_mod.slugify)
    table.to_csv(cfg["paths"]["standardized"] / "school_status.csv", index=False, encoding="utf-8")
    print(table["state"].value_counts().to_string() if not table.empty else "no schools yet")


def cmd_mark_uploaded(args, cfg):
    for name in args.files:
        status.mark_uploaded(cfg["paths"]["submit_ready"], name)
    print("marked:", ", ".join(args.files))


def cmd_intake(args, cfg):
    url = args.sheet_url or os.environ.get("REGISTRATION_SHEET_URL")
    if not url:
        raise SystemExit("give --sheet-url or set REGISTRATION_SHEET_URL")
    data, _ = intake.http_fetch(intake.sheet_csv_url(url))
    results = intake.run(cfg, data.decode("utf-8"), fetch=args.fetch)
    for r in results:
        print(f"{r['outcome']}: {r['school']} ({r['timestamp']})" + (f" -> {r['saved_as']}" if "saved_as" in r else "") + (f" [{r['error']}]" if "error" in r else ""))
    if not results:
        print("nothing new")
    elif not args.fetch:
        print("listing only; add --fetch to download")


def main() -> None:
    parser = argparse.ArgumentParser(prog="registration", description="Registration workbooks: standardize, partition, status, intake.")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "default.yaml")
    parser.add_argument("--replies", type=Path, default=ROOT / "configs" / "replies.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("standardize", help="check workbooks, write standardized tables, review reports and reply drafts")
    p.add_argument("input", type=Path, help="a workbook or a folder of workbooks")
    p.add_argument("--force", action="store_true", help="redo files already done (after changing overrides or configuration)")
    p.add_argument("--accept-old-template", action="store_true", help="process files without a NISN column (testing on earlier data)")
    p.set_defaults(func=cmd_standardize)

    p = sub.add_parser("school-source", help="download the schools of the Bandung area from the ministry's reference pages (resumable)")
    p.set_defaults(func=cmd_school_source)

    p = sub.add_parser("school-master", help="build the school master from the ministry list, the 2025 files and this year's files")
    p.set_defaults(func=cmd_school_master)

    p = sub.add_parser("report", help="registration statistics from the deduplicated table, written as statistics.csv")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("dedup", help="one row per student key, keys for students without a NISN, report of repeated keys and names")
    p.set_defaults(func=cmd_dedup)

    p = sub.add_parser("partition", help="write one upload file per school from the checked tables")
    p.add_argument("--kategori", help="only these categories, comma separated (for example SiKecil,Siaga)")
    p.set_defaults(func=cmd_partition)

    p = sub.add_parser("status", help="write the per-school status table")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("mark-uploaded", help="record that upload files went to the website")
    p.add_argument("files", nargs="+", help="upload file names, for example school-20261105-1200.xlsx")
    p.set_defaults(func=cmd_mark_uploaded)

    p = sub.add_parser("intake", help="list new submissions from the response sheet; --fetch downloads them")
    p.add_argument("--sheet-url", help="link of the response sheet (or set REGISTRATION_SHEET_URL)")
    p.add_argument("--fetch", action="store_true", help="download the new files (default: list only)")
    p.set_defaults(func=cmd_intake)

    args = parser.parse_args()
    args.func(args, load_config(args.config))
