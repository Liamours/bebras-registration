"""Deduplicate: one row per student key, keys for students without a NISN, and a report of every repeated key or name."""
import re
from pathlib import Path

import pandas as pd

from registration.partition import load_checked
from registration.schools import canonicalize, load_master, slugify

KEY_COLUMNS = ["source_file", "source_row", "key"]
REPORT_COLUMNS = ["check", "key_or_name", "school", "source_file", "source_row", "kept", "reason"]


def letters(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def fullness(row: pd.Series, null: str) -> int:
    return sum(1 for v in row if isinstance(v, str) and v not in ("", null))


def assign_keys(data: pd.DataFrame, state_path: Path, code: str, null: str) -> pd.DataFrame:
    """A student without a NISN gets `<code>_NNNNN`. The key given to a row is stored, so a rerun gives the same key and a number is never reused."""
    pattern = re.compile(rf"^{re.escape(code)}_(\d{{5}})$")
    state = pd.read_csv(state_path, dtype=str) if state_path.exists() else pd.DataFrame(columns=KEY_COLUMNS)
    used = [int(m.group(1)) for k in [*state["key"], *data["NISN"]] if (m := pattern.match(str(k)))]
    last = max(used, default=0)
    known = {(r["source_file"], r["source_row"]): r["key"] for _, r in state.iterrows()}
    data = data.copy()
    data["note"] = ""
    for i in data[data["NISN"] == null].sort_values(["source_file", "source_row"], key=lambda s: s.astype(str).str.zfill(8)).index:
        ref = (data.at[i, "source_file"], str(data.at[i, "source_row"]))
        if ref not in known:
            last += 1
            known[ref] = f"{code}_{last:05d}"
        data.at[i, "NISN"] = known[ref]
        data.at[i, "note"] = "key assigned, the student has no NISN"
    pd.DataFrame([[f, r, k] for (f, r), k in known.items()], columns=KEY_COLUMNS).to_csv(state_path, index=False, encoding="utf-8")
    return data


def deduplicate(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write `students.csv` and `duplicates.csv` in the deduplicated folder and return them."""
    null = cfg["null_value"]
    out_dir = cfg["paths"]["deduplicated"]
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_checked(cfg["paths"]["standardized"], ignore_codes={"missing_nisn"})
    if data.empty:
        return data, pd.DataFrame(columns=REPORT_COLUMNS)
    data["source_row"] = data["source_row"].astype(str)
    master = load_master(cfg["paths"]["school_master"])
    if master.empty:
        data["school_slug"] = data["Nama Sekolah"].map(slugify)
    else:  # canonical school names, the region of the school as Kota/Kabupaten, and the unmatched schools for review
        data, school_review = canonicalize(data, master, null)
        school_review.to_csv(out_dir / "school_review.csv", index=False, encoding="utf-8")
    data = assign_keys(data, out_dir / "assigned_keys.csv", cfg["bureau_code"], null)
    data["school_key"] = data["Nama Sekolah"].map(letters)
    report, drop = [], []

    def line(check, key, row, kept, reason):
        report.append([check, key, row["Nama Sekolah"], row["source_file"], row["source_row"], kept, reason])

    for key, group in data.groupby("NISN", sort=True):
        if len(group) < 2:
            continue
        if group["school_key"].nunique() > 1:  # no automatic choice: every row stays, is marked and is listed
            for i, row in group.iterrows():
                data.at[i, "has_error"] = True
                data.at[i, "note"] = "the same NISN is under another school"
                line("same_key_two_schools", key, row, "held", "decide with the senders; fix a NISN or drop a row in overrides.csv")
            continue
        order = sorted(group.index, key=lambda i: (-fullness(group.loc[i], null), str(group.at[i, "source_file"]), int(group.at[i, "source_row"])))
        for n, i in enumerate(order):
            keep = n == 0
            line("same_key_in_school", key, group.loc[i], "yes" if keep else "no", "the fuller row is kept" if keep else "dropped, an earlier or fuller row has the same key")
            if not keep:
                drop.append(i)
    data = data.drop(index=drop)
    data["name_key"] = data["Nama Lengkap"].map(letters)
    for (_, _), group in data.groupby(["name_key", "school_key"], sort=True):
        if group["NISN"].nunique() > 1:  # one student entered twice under different keys, or two students with one name
            for _, row in group.iterrows():
                line("same_name_in_school", row["Nama Lengkap"], row, "yes", "same name and school under different keys, check by hand")
    students = data.drop(columns=["school_key", "name_key"]).reset_index(drop=True)
    duplicates = pd.DataFrame(report, columns=REPORT_COLUMNS)
    students.to_csv(out_dir / "students.csv", index=False, encoding="utf-8")
    duplicates.to_csv(out_dir / "duplicates.csv", index=False, encoding="utf-8")
    return students, duplicates
