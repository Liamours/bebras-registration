"""School names: the canonical form, lookup by name or alias, suggestions for a name that matches nothing, and the region of a school."""
import re
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

MASTER_COLUMNS = ["school_slug", "canonical_name", "npsn", "jenjang", "region", "aliases"]
REVIEW_COLUMNS = ["check", "school", "value", "suggestions", "rows"]
REGIONS = ("Kota Bandung", "Kabupaten Bandung", "Kabupaten Bandung Barat", "Kota Cimahi")
STATE_PREFIX = {"smpn": "SMP Negeri", "smpn.": "SMP Negeri", "sman": "SMA Negeri", "smkn": "SMK Negeri", "sdn": "SD Negeri", "min": "MI Negeri",
                "mtsn": "MTs Negeri", "man": "MA Negeri"}
ACRONYMS = {"sd", "smp", "sma", "smk", "mi", "ma", "mak", "sdit", "smpit", "smait", "smkit", "sdii", "smpii", "smaii", "sdk", "smpk", "smak", "bpk", "bpi",
            "tk", "it", "ii", "iii", "iv", "pgri", "ypi", "ypk", "nu", "uptd", "ikip", "pkbm", "kb"}
SPECIAL = {"mts": "MTs", "mis": "MIS", "mts.": "MTs"}
MIN_SUGGESTION = 0.85
SHARED_MARK = "NPSN"  # a suggestion that carries an NPSN names a candidate of a shared name, not a close spelling
# the ministry's list leaves the city out of a school's name, senders add it at the end: key ending -> the regions it can mean
CITY_ENDING = {"kotabandung": ("Kota Bandung",), "kabupatenbandungbarat": ("Kabupaten Bandung Barat",), "kabbandungbarat": ("Kabupaten Bandung Barat",),
               "kabupatenbandung": ("Kabupaten Bandung",), "kabbandung": ("Kabupaten Bandung",), "bandungbarat": ("Kabupaten Bandung Barat",),
               "bandung": ("Kota Bandung", "Kabupaten Bandung"), "kotacimahi": ("Kota Cimahi",), "cimahi": ("Kota Cimahi",)}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unknown"


def canonical(name: str) -> str:
    """Canonical spelling: SMPN 1 becomes SMP Negeri 1, a digit is split from a letter, acronyms are capitals, other words start with a capital."""
    s = re.sub(r"\s+", " ", str(name)).strip()
    s = re.sub(r"(?i)^(smp|sma|smk|sd|mts|mi|ma)\s+n\.?(?=\s|\d)", lambda m: m.group(1) + "n", s)  # SMP N 1 is SMPN 1
    s = re.sub(r"(?i)^(smpn|sman|smkn|sdn|mtsn|min|man)[\.-]", lambda m: m.group(1) + " ", s)  # SMPN.1 is SMPN 1
    s = re.sub(r"(?<=\d)(?=[A-Za-z])|(?<=[A-Za-z])(?=\d)", " ", s)
    s = re.sub(r"\b0+(?=\d)", "", s)  # 01 is 1
    words = s.split(" ")
    if words and words[0].lower() in STATE_PREFIX:
        words[0] = STATE_PREFIX[words[0].lower()]
        words = " ".join(words).split(" ")
    out = []
    for w in words:
        low = w.lower()
        if low in SPECIAL:
            out.append(SPECIAL[low])
        elif low in ACRONYMS:
            out.append(w.upper())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in w.split("-")))
    return " ".join(out)


def key(name: str) -> str:
    """What two spellings of one school have in common: letters and digits of the canonical form, lower case."""
    return re.sub(r"[^a-z0-9]", "", canonical(name).lower())


def load_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=MASTER_COLUMNS)
    return pd.read_csv(path, dtype=str).fillna("")


def index(master: pd.DataFrame) -> dict[str, list[int]]:
    """key -> every master row with that name or alias (a name without its place, such as `SD Negeri 1`, belongs to many schools)."""
    found: dict[str, list[int]] = {}
    for i, r in master.iterrows():
        for name in [r["canonical_name"], *[a for a in r["aliases"].split("|") if a]]:
            rows = found.setdefault(key(name), [])
            if i not in rows:
                rows.append(i)
    return found


def regions_of(city: str) -> tuple[str, ...]:
    """The regions a typed Kota/Kabupaten value can mean; empty when it says nothing usable. Read by words: KBB, Bdg and Kab. are understood."""
    words = re.findall(r"[a-z]+", str(city).lower())
    words = [{"bdg": "bandung", "kab": "kabupaten", "kbb": "kbb"}.get(w, w) for w in words]
    if "kbb" in words or any(a == "bandung" and b == "barat" for a, b in zip(words, words[1:])):  # `Bandung, Jawa Barat` is not Bandung Barat
        return ("Kabupaten Bandung Barat",)
    if "cimahi" in words:
        return ("Kota Cimahi",)
    if "bandung" in words:
        return ("Kota Bandung",) if "kota" in words else (("Kabupaten Bandung",) if "kabupaten" in words else ("Kota Bandung", "Kabupaten Bandung"))
    return ()


def lookup(name: str, master: pd.DataFrame, idx: dict[str, list[int]] | None = None, city: str = "") -> tuple[pd.Series | None, list[str]]:
    """The master row of a name, or None with up to three suggestions. Only a single candidate is a match.

    A name shared by several schools is narrowed by the region that the typed city or the end of the name points to. A suggestion is never picked.
    """
    idx = index(master) if idx is None else idx
    k = key(name)
    candidates = list(idx.get(k, []))
    ending_regions: tuple[str, ...] = ()
    if not candidates:  # senders add the city that the ministry list leaves out: SMPN 19 BANDUNG is the list's SMP NEGERI 19
        for ending, regions in CITY_ENDING.items():
            if k.endswith(ending) and idx.get(k[: -len(ending)]):
                candidates, ending_regions = list(idx[k[: -len(ending)]]), regions
                break
    if ending_regions:  # a school whose list name lacks the city must lie in the city the sender wrote
        candidates = [i for i in candidates if master.at[i, "region"] in ending_regions]
    if len(candidates) > 1:
        narrowed = [i for i in candidates if master.at[i, "region"] in regions_of(city)]
        candidates = narrowed or candidates
    if len(candidates) == 1:
        return master.loc[candidates[0]], []
    if candidates:
        return None, [f"{master.at[i, 'canonical_name']} ({master.at[i, 'region']}, {SHARED_MARK} {master.at[i, 'npsn']})" for i in candidates[:3]]
    close = get_close_matches(k, list(idx), n=3, cutoff=MIN_SUGGESTION)
    return None, [master.at[idx[c][0], "canonical_name"] for c in close if len(idx[c]) == 1]


def canonicalize(table: pd.DataFrame, master: pd.DataFrame, null: str = "-") -> tuple[pd.DataFrame, pd.DataFrame]:
    """The table with canonical school names, a school_slug, and Kota/Kabupaten as the region of the school.

    The region comes from the matched school (a typed city that contradicts it is reported as `region_conflict`), or from the typed city when
    that names one region. A bare `Bandung` of an unknown school is `region_ambiguous` with both candidates; a school that matches nothing or
    several schools is `school_unmatched` with its suggestions.
    """
    table = table.copy()
    idx = index(master)
    counts: dict[tuple, int] = {}
    slugs, suggested, cache, ambiguous = [], {}, {}, []
    for i, row in table.iterrows():
        raw, city = row["Nama Sekolah"], row["Kota/Kabupaten"]
        typed = regions_of(city)
        if (raw, city) not in cache:
            cache[(raw, city)] = lookup(raw, master, idx, city)
        found, suggestions = cache[(raw, city)]
        if found is not None:
            table.at[i, "Nama Sekolah"] = found["canonical_name"]
            slugs.append(found["school_slug"])
            ambiguous.append(False)
            if found["region"] in REGIONS:
                table.at[i, "Kota/Kabupaten"] = found["region"]
                if typed and found["region"] not in typed:
                    k = ("region_conflict", found["canonical_name"], f"{city} -> {found['region']}", "-")
                    counts[k] = counts.get(k, 0) + 1
            elif len(typed) == 1:  # a school outside the four regions: the typed city is read as for an unknown school
                table.at[i, "Kota/Kabupaten"] = typed[0]
            elif len(typed) > 1:
                k = ("region_ambiguous", found["canonical_name"], city, " | ".join(typed))
                counts[k] = counts.get(k, 0) + 1
            continue
        table.at[i, "Nama Sekolah"] = canonical(raw) if raw != null else raw
        suggested[table.at[i, "Nama Sekolah"]] = suggestions
        shared = bool(suggestions) and SHARED_MARK in suggestions[0]  # several schools carry this name
        ambiguous.append(shared)
        slugs.append(slugify(table.at[i, "Nama Sekolah"]) + ("_ambiguous" if shared else ""))
        if len(typed) == 1:
            table.at[i, "Kota/Kabupaten"] = typed[0]
        elif len(typed) > 1:
            k = ("region_ambiguous", raw, city, " | ".join(typed))
            counts[k] = counts.get(k, 0) + 1
    table["school_slug"] = slugs
    table["school_ambiguous"] = ambiguous
    for school, group in table[table["school_ambiguous"]].groupby("Nama Sekolah"):
        counts[("school_ambiguous", school, school, " | ".join(suggested.get(school, [])))] = len(group)
    for school, group in table[~table["school_slug"].isin(set(master["school_slug"])) & ~table["school_ambiguous"]].groupby("Nama Sekolah"):
        counts[("school_unmatched", school, school, " | ".join(suggested.get(school, [])) or "-")] = len(group)
    review = [[check, school, value, suggestions, n] for (check, school, value, suggestions), n in counts.items()]
    return table, pd.DataFrame(review, columns=REVIEW_COLUMNS)


def build_master(portal: pd.DataFrame, seen: pd.DataFrame, hand_aliases: pd.DataFrame, existing_slugs: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The school master from the ministry list plus every school seen in registration files (region `other` when it is not in the list).

    `seen` has the columns name, jenjang, city. `hand_aliases` has alias, npsn. `existing_slugs` maps the key of a school that already has an
    upload folder to that folder's slug, so a folder is never renamed. Returns the master and the seen names that were added as `other`.
    """
    rows, taken = [], set()
    for _, r in portal.iterrows():
        name = canonical(r["name"])
        slug = existing_slugs.get(key(name)) or slugify(name)
        if slug in taken:
            slug = f"{slug}_{r['npsn']}"
        taken.add(slug)
        rows.append({"school_slug": slug, "canonical_name": name, "npsn": r["npsn"], "jenjang": r["jenjang"], "region": r["region"], "aliases": set()})
    by_npsn = {r["npsn"]: i for i, r in enumerate(rows)}
    for _, a in hand_aliases.iterrows():
        if a["npsn"] in by_npsn:
            rows[by_npsn[a["npsn"]]]["aliases"].add(a["alias"])

    def frame():
        return pd.DataFrame([{**r, "aliases": "|".join(sorted(r["aliases"]))} for r in rows], columns=MASTER_COLUMNS)

    current = frame()
    idx = index(current)
    added = []
    for _, s in seen.drop_duplicates("name").iterrows():
        found, _ = lookup(s["name"], current, idx, s["city"])
        if found is not None:
            i = int(found.name)
            if s["name"] != rows[i]["canonical_name"]:
                rows[i]["aliases"].add(s["name"])
                current.at[i, "aliases"] = "|".join(sorted(rows[i]["aliases"]))
                if i not in idx.setdefault(key(s["name"]), []):
                    idx[key(s["name"])].append(i)
            continue
        name = canonical(s["name"])
        if re.fullmatch(r"(SD|SMP|SMA|SMK|MI|MTs|MA) Negeri \d+", name):  # no place in the name: it would match every school of that number
            added.append([s["name"], name, s["jenjang"], s["city"], "not added, the name has no place"])
            continue
        slug = existing_slugs.get(key(name)) or slugify(name)
        slug = f"{slug}_other" if slug in taken else slug
        taken.add(slug)
        rows.append({"school_slug": slug, "canonical_name": name, "npsn": "", "jenjang": s["jenjang"], "region": "other", "aliases": {s["name"]} - {name}})
        current = frame()
        idx.setdefault(key(name), []).append(len(rows) - 1)
        added.append([s["name"], name, s["jenjang"], s["city"], "added with region other"])
    master = frame().sort_values(["region", "canonical_name"]).reset_index(drop=True)
    return master, pd.DataFrame(added, columns=["seen_name", "canonical_name", "jenjang", "city", "result"])
