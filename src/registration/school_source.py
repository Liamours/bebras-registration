"""Download the school list of the Bandung area from the reference data pages of the ministry (Pusdatin Kemendikdasmen)."""
import csv
import html
import re
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from tqdm import tqdm

COLUMNS = ["npsn", "name", "address", "kelurahan", "status", "jenjang", "region", "kecamatan", "fetched"]
ROW = re.compile(r'<td class="link1">.*?npsn/(\d+)">.*?</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>', re.S)


def get(url: str, tries: int = 4) -> str:
    for n in range(tries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "registration-school-list"}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except OSError:
            if n == tries - 1:
                raise
            time.sleep(2 ** (n + 1))


def sub_regions(base: str, level: str, code: str) -> list[tuple[str, str]]:
    """The kecamatan (code, name) of a regency or city."""
    page = get(f"{base}/{level}/{code}/2")
    return [(c, html.unescape(n).strip()) for c, n in re.findall(rf'/{level}/(\d{{6}})/3">\s*([^<]+)', page)]


def parse_rows(page: str) -> list[list[str]]:
    return [[html.unescape(re.sub(r"\s+", " ", v)).strip() for v in m] for m in ROW.findall(page)]


def build(cfg: dict, out: Path, state: Path, log) -> int:
    """Write the schools of every configured region and school form; a rerun skips the pages already done."""
    src = cfg["school_source"]
    base, delay = src["base"], src["delay_seconds"]
    done = set(state.read_text(encoding="utf-8").splitlines()) if state.exists() else set()
    new = not out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    jobs = []
    for region, code in src["regions"].items():
        for level, forms in src["forms"].items():
            for kec_code, kec in sub_regions(base, level, code):
                jobs += [(region, level, form, form_code, kec_code, kec) for form, form_code in forms.items()]
    log(f"{len(jobs)} pages, {len(done)} done, delay {delay} s, about {round(len(jobs) * (delay + 0.4) / 60)} min in total")
    count = 0
    with out.open("a", newline="", encoding="utf-8") as f, state.open("a", encoding="utf-8") as s:
        writer = csv.writer(f)
        if new:
            writer.writerow(COLUMNS)
        for region, level, form, form_code, kec_code, kec in tqdm(jobs, desc="pages", unit="page"):
            key = f"{kec_code}/{level}/{form}"
            if key in done:
                continue
            rows = parse_rows(get(f"{base}/{level}/{kec_code}/3/jf/{form_code}"))
            for npsn, name, address, kelurahan, status in rows:
                writer.writerow([npsn, name, address, kelurahan, status, form, region, kec, date.today().isoformat()])
            f.flush()  # the rows are on disk before the page counts as done
            s.write(key + "\n")
            s.flush()
            count += len(rows)
            time.sleep(delay)
    return count
