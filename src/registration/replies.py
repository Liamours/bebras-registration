"""Draft reply messages for a sender, built from a review report. Nothing is sent from here."""
from collections import defaultdict
from pathlib import Path

import yaml

from registration.review import Issue


def load_replies(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rows(issues: list[Issue], show_values: bool) -> str:
    seen, parts = set(), []
    for i in sorted(issues, key=lambda i: i.source_row or 0):
        if i.source_row in seen:
            continue
        seen.add(i.source_row)
        parts.append(f"{i.source_row} ('{i.value}')" if show_values and i.value else str(i.source_row))
    return "baris " + ", ".join(parts)


def build_reply(replies: dict, issues: list[Issue], school: str = "", rejected: list[tuple[str, str]] | None = None) -> str | None:
    """A message listing every error (or every reason for rejection); None when there is nothing to say.

    `rejected` holds (code, detail) pairs for a rejected file, detail being the missing columns when relevant.
    """
    school_part = f" dari {school}" if school else ""
    lines = []
    if rejected:
        head = replies["rejected_greeting"].format(school=school_part)
        for code, detail in rejected:
            lines.append(replies["codes"][code].format(columns=detail, rows="", column=""))
    else:
        groups: dict[tuple[str, str], list[Issue]] = defaultdict(list)
        for i in issues:
            if i.severity == "error" and i.code in replies["codes"]:
                groups[(i.code, i.column if i.code == "unknown_value" else "")].append(i)
        if not groups:
            return None
        head = replies["greeting"].format(school=school_part)
        for (code, column), items in groups.items():
            lines.append(replies["codes"][code].format(rows=_rows(items, code == "unknown_value"), column=column, columns=""))
    body = "\n".join(f"{n}. {line}" for n, line in enumerate(lines, 1))
    return f"{head}\n\n{body}\n\n{replies['closing']}\n"
