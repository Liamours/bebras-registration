"""Intake: find submissions in the form's response sheet that were not fetched yet, fetch them, record the sender.

Nothing is downloaded unless `fetch` is true; a plain run only lists what is new.
"""
import io
import re
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import unquote
from urllib.request import Request, urlopen

import pandas as pd

from registration.partition import slugify

DOWNLOAD_URL = "https://drive.usercontent.google.com/download?id={id}&export=download"
EXPORT_URL = "https://docs.google.com/spreadsheets/d/{id}/export?format=xlsx"
STATE_COLUMNS = ["file_id", "timestamp", "saved_as", "fetched_at"]
ROUTING_COLUMNS = ["cp_name", "cp_phone", "submitter_name", "submitter_phone", "submitter_role", "school_slug", "received_date", "source_file", "notes"]
MAX_BYTES = 25 * 1024 * 1024

Fetcher = Callable[[str], tuple[bytes, dict]]


def sheet_csv_url(url: str) -> str:
    """Accept a sheet link (edit or export) and return its CSV export link."""
    if "export?format=csv" in url:
        return url
    sheet = re.search(r"/d/([\w-]+)", url)
    gid = re.search(r"gid=(\d+)", url)
    if not sheet:
        raise ValueError("not a Google Sheets link")
    return f"https://docs.google.com/spreadsheets/d/{sheet.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


def file_id(link: str) -> str | None:
    m = re.search(r"[?&]id=([\w-]+)", link) or re.search(r"/d/([\w-]+)", link)
    return m.group(1) if m else None


def http_fetch(url: str) -> tuple[bytes, dict]:
    with urlopen(Request(url, headers={"User-Agent": "registration-intake"}), timeout=60) as r:
        return r.read(MAX_BYTES), dict(r.headers)


def file_name(headers: dict, fid: str) -> str:
    disposition = headers.get("Content-Disposition", "") or headers.get("content-disposition", "")
    star = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
    plain = re.search(r'filename="([^"]+)"', disposition)
    name = unquote(star.group(1)) if star else (plain.group(1) if plain else f"{fid}.xlsx")
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def read_state(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=STATE_COLUMNS)


def list_new(sheet: pd.DataFrame, cfg: dict, state: pd.DataFrame) -> pd.DataFrame:
    """Rows of the response sheet whose file has not been fetched yet."""
    c = cfg["intake"]["columns"]
    rows = sheet.copy()
    rows.columns = [c["timestamp"], *rows.columns[1:]]  # the first column of a form response sheet is the timestamp, whatever its header says
    rows["file_id"] = rows[c["file_link"]].map(lambda v: file_id(str(v)) if isinstance(v, str) else None)
    rows = rows[rows["file_id"].notna() & ~rows["file_id"].isin(set(state["file_id"]))]
    return rows.reset_index(drop=True)


def unique_path(folder: Path, name: str, fid: str) -> Path:
    path = folder / name
    return path if not path.exists() else folder / f"{path.stem}-{fid[:6]}{path.suffix}"


def add_routing(path: Path, row: dict) -> None:
    table = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame(columns=ROUTING_COLUMNS)
    if row["source_file"] not in set(table["source_file"]):
        table = pd.concat([table, pd.DataFrame([row], columns=ROUTING_COLUMNS)], ignore_index=True)
    table.to_csv(path, index=False, encoding="utf-8")


def run(cfg: dict, sheet_csv: str, *, fetch: bool = False, fetcher: Fetcher = http_fetch) -> list[dict]:
    """List the new submissions and, with `fetch`, download them. Returns one result line per submission."""
    ic = cfg["intake"]
    c = ic["columns"]
    target = Path(ic["target_dir"])
    state_path = Path(ic["state_file"])
    state = read_state(state_path)
    fresh = list_new(pd.read_csv(io.StringIO(sheet_csv), dtype=str).fillna(""), cfg, state)
    results = []
    for _, r in fresh.iterrows():
        result = {"file_id": r["file_id"], "school": r[c["school"]], "timestamp": r[c["timestamp"]], "outcome": "new"}
        if fetch:
            try:
                try:
                    data, headers = fetcher(DOWNLOAD_URL.format(id=r["file_id"]))
                except Exception:  # a sheet made in Google Sheets is no file to download: it is exported as xlsx
                    data, headers = fetcher(EXPORT_URL.format(id=r["file_id"]))
                if data[:2] != b"PK":
                    data, headers = fetcher(EXPORT_URL.format(id=r["file_id"]))
                if len(data) >= MAX_BYTES:
                    raise ValueError("file larger than the size limit")
                if data[:2] != b"PK":
                    raise ValueError("not an xlsx file (the link may need a sign-in or is not shared)")
                target.mkdir(parents=True, exist_ok=True)
                path = unique_path(target, file_name(headers, r["file_id"]), r["file_id"])
                path.write_bytes(data)
                state.loc[len(state)] = [r["file_id"], r[c["timestamp"]], path.name, date.today().isoformat()]
                state.to_csv(state_path, index=False, encoding="utf-8")  # written before moving on, so a crash repeats at most one file
                add_routing(Path(cfg["paths"]["routing"]), {
                    "cp_name": "-", "cp_phone": "-", "submitter_name": r[c["sender_name"]], "submitter_phone": r[c["sender_phone"]],
                    "submitter_role": ic["role_map"].get(re.sub(r"\s+", " ", r[c["sender_role"]].strip().lower()), "unknown"),
                    "school_slug": slugify(r[c["school"]]), "received_date": date.today().isoformat(), "source_file": path.name,
                    "notes": "via submission form (no CP)",
                })
                result.update(outcome="fetched", saved_as=path.name)
            except Exception as e:  # one failing file must not stop the others; it stays "new" and is retried on the next run
                result.update(outcome="failed", error=str(e))
        results.append(result)
    return results
