"""Deduplicate: one row per student key, keys for students without a NISN, and a report of every repeated key or name."""
import re
from pathlib import Path

import pandas as pd

from registration.partition import load_checked
from registration.schools import canonicalize, load_master, slugify

REPORT_COLUMNS = ["check", "key_or_name", "school", "source_file", "source_row", "kept", "reason"]


def letters(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def fullness(row: pd.Series, null: str) -> int:
    return sum(1 for v in row if isinstance(v, str) and v not in ("", null))


KEY_COLUMNS = ["source_file", "source_row", "key", "name_key", "school_key"]


def assign_keys(data: pd.DataFrame, state_path: Path, code: str, null: str) -> pd.DataFrame:
    """A student without a NISN gets `<code>_NNNNN`. The key is stored with the file and row and with the name and school, so a rerun, a resent file with
    shifted rows or a renamed file gives the same student the same key, and a number is never used twice."""
    pattern = re.compile(rf"^{re.escape(code)}_(\d{{5}})$")
    has_state = state_path.exists() and state_path.stat().st_size > 2  # an empty file is read as no state: the keys are then built from the data alone
    state = pd.read_csv(state_path, dtype=str).reindex(columns=KEY_COLUMNS).fillna("") if has_state else pd.DataFrame(columns=KEY_COLUMNS)
    used = [int(m.group(1)) for k in [*state["key"], *data["NISN"]] if (m := pattern.match(str(k)))]
    last = max(used, default=0)
    lines = [(r["source_file"], r["source_row"], r["key"], r["name_key"], r["school_key"]) for _, r in state.iterrows()]
    by_ref = {(f, r): (k, n, s) for f, r, k, n, s in lines}
    by_student = {(n, s): k for _, _, k, n, s in lines if n}
    data = data.copy()
    data["note"] = ""
    data["old_key"] = ""
    order = list(data[data["NISN"] == null].sort_values(["source_file", "source_row"], key=lambda s: s.astype(str).str.zfill(8)).index)
    # the same student is the same name, school (its slug, which a change of the master does not alter), class and email; two students that look alike
    # are told apart by the check on name and school instead of being merged
    refs = {i: (data.at[i, "source_file"], str(data.at[i, "source_row"])) for i in order}
    whos = {i: (letters(data.at[i, "Nama Lengkap"]), f"{data.at[i, 'school_slug']}|{data.at[i, 'Kelas']}|{letters(data.at[i, 'Email'])}") for i in order}
    keys: dict = {}
    for i in order:  # pass 1: the row of an earlier run that is still the same student, or the student found at another row
        stored, who = by_ref.get(refs[i]), whos[i]
        if stored and (not stored[1] or (stored[1], stored[2]) == who):
            keys[i] = stored[0]
        elif who[0] and who in by_student:
            keys[i] = by_student[who]
    claimed = set(keys.values())
    for i in order:  # pass 2: same row, same name and school, only the class or the email changed (a correction): the student keeps the key if no other row holds it
        stored, who = by_ref.get(refs[i]), whos[i]
        if i not in keys and stored and who[0] and stored[1] == who[0] and stored[2].split("|")[0] == who[1].split("|")[0] and stored[0] not in claimed:
            keys[i] = stored[0]
            claimed.add(stored[0])
    for i in order:  # pass 3: a student not seen before gets the next number; a row that held another student in an earlier run is reported
        who = whos[i]
        if i not in keys:
            keys[i] = by_student.get(who) if who[0] else None
            if keys[i] is None:
                last += 1
                keys[i] = f"{code}_{last:05d}"
                if refs[i] in by_ref and by_ref[refs[i]][1]:
                    data.at[i, "old_key"] = by_ref[refs[i]][0]
        key = keys[i]
        if (*refs[i], key, *who) not in lines:
            lines.append((*refs[i], key, *who))
        by_ref[refs[i]] = (key, *who)
        if who[0]:
            by_student.setdefault(who, key)
        data.at[i, "NISN"] = key
        data.at[i, "note"] = "key assigned, the student has no NISN"
    data.loc[data["old_key"].isin(set(data["NISN"])), "old_key"] = ""  # the old student is still in the data at another row: only the rows moved, nothing to report
    temp = state_path.with_suffix(".tmp")  # written whole, then put in place, so an interrupted write cannot leave an empty keys file
    pd.DataFrame(lines, columns=KEY_COLUMNS).to_csv(temp, index=False, encoding="utf-8")
    temp.replace(state_path)
    return data


def deduplicate(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write `students.csv` and `duplicates.csv` in the deduplicated folder and return them."""
    null = cfg["null_value"]
    out_dir = cfg["paths"]["deduplicated"]
    out_dir.mkdir(parents=True, exist_ok=True)
    data = load_checked(cfg["paths"]["standardized"], ignore_codes={"missing_nisn"})
    if data.empty:  # an old table must not stay for the partition to read
        for name in ("students.csv", "duplicates.csv"):
            (out_dir / name).unlink(missing_ok=True)
        return data, pd.DataFrame(columns=REPORT_COLUMNS)
    data["source_row"] = data["source_row"].astype(str)
    master = load_master(cfg["paths"]["school_master"])
    review_path = out_dir / "school_review.csv"
    if master.empty:
        review_path.unlink(missing_ok=True)  # an old review must not outlive the master it came from
        data["school_slug"] = data["Nama Sekolah"].map(slugify)
        data["school_ambiguous"] = False
    else:  # canonical school names, the region of the school as Kota/Kabupaten, and the unmatched schools for review
        data, school_review = canonicalize(data, master, null)
        school_review.to_csv(review_path, index=False, encoding="utf-8")
    data = assign_keys(data, cfg["paths"]["assigned_keys"], cfg["bureau_code"], null)
    data.loc[data["school_ambiguous"], ["has_error", "note"]] = [True, "the school name matches several schools, decide which one"]
    data["school_key"] = data["Nama Sekolah"].map(letters)
    data["name_key"] = data["Nama Lengkap"].map(letters)
    report, drop = [], []

    def line(check, key, row, kept, reason):
        report.append([check, key, row["Nama Sekolah"], row["source_file"], row["source_row"], kept, reason])

    for _, row in data[data["old_key"] != ""].iterrows():  # the same file and row held another student before: a new student, or the same one corrected in more than one field
        line("key_new_for_changed_row", row["NISN"], row, "yes", f"this row held another student under {row['old_key']}; if it is the same student (a correction), set NISN to {row['old_key']} in overrides.csv so no second account is made")
    for key, group in data.groupby("NISN", sort=True):
        if len(group) < 2:
            continue
        if group["school_key"].nunique() > 1:  # no automatic choice: every row stays, is marked and is listed
            for i, row in group.iterrows():
                data.at[i, "has_error"] = True
                data.at[i, "note"] = "the same NISN is under another school"
                line("same_key_two_schools", key, row, "held", "decide with the senders; fix a NISN or drop a row in overrides.csv")
            continue
        if group["name_key"].nunique() > 1:  # a NISN belongs to one student: one of the NISN values is wrong, only the sender knows which
            for i, row in group.iterrows():
                data.at[i, "has_error"] = True
                data.at[i, "note"] = "the same NISN is under different names"
                line("same_key_different_names", key, row, "held", "a NISN belongs to one student: ask the sender which NISN is right, then fix it in overrides.csv")
            continue
        order = sorted(group.index, key=lambda i: (bool(group.at[i, "has_error"]), -fullness(group.loc[i], null), str(group.at[i, "source_file"]), int(group.at[i, "source_row"])))
        for n, i in enumerate(order):
            keep = n == 0
            line("same_key_in_school", key, group.loc[i], "yes" if keep else "no", "the fuller row is kept" if keep else "dropped, an earlier or fuller row has the same key")
            if not keep:
                drop.append(i)
    data = data.drop(index=drop)
    for (name_key, _), group in data.groupby(["name_key", "school_key"], sort=True):
        if name_key and group["NISN"].nunique() > 1:  # a row without a name is already an error of its own  # one student entered twice under different keys, or two students with one name
            for _, row in group.iterrows():
                line("same_name_in_school", row["Nama Lengkap"], row, "yes", "same name and school under different keys, check by hand")
    students = data.drop(columns=["school_key", "name_key", "school_ambiguous", "old_key"]).reset_index(drop=True)
    duplicates = pd.DataFrame(report, columns=REPORT_COLUMNS)
    students.to_csv(out_dir / "students.csv", index=False, encoding="utf-8")
    duplicates.to_csv(out_dir / "duplicates.csv", index=False, encoding="utf-8")
    return students, duplicates
