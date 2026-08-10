#!/usr/bin/env python3
"""Update the publications section of assets/json/resume.json from _bibliography/papers.bib."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_BIB = ROOT / "_bibliography" / "papers.bib"
DEFAULT_RESUME = ROOT / "assets" / "json" / "resume.json"

# Keep journal articles and preprints; skip theses and other non-pub types.
INCLUDE_TYPES = {"article", "misc", "inproceedings", "conference", "incollection"}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

ENTRY_START = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
DOUBLE_BRACE = re.compile(r"\{\{([^{}]+)\}\}")
SINGLE_BRACE = re.compile(r"\{([^{}]+)\}")
MATH_SEGMENT = re.compile(r"\\\((.+?)\\\)")


def strip_case_braces(text: str) -> str:
    """Remove Better BibTeX / BibTeX case-protection braces outside math."""
    parts: list[str] = []
    last = 0
    for match in MATH_SEGMENT.finditer(text):
        parts.append(_strip_braces_outside_math(text[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_strip_braces_outside_math(text[last:]))
    return "".join(parts)


def _strip_braces_outside_math(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = DOUBLE_BRACE.sub(r"\1", text)
    prev = None
    while prev != text:
        prev = text
        text = SINGLE_BRACE.sub(r"\1", text)
    return text


def clean_math(math_body: str) -> str:
    """Normalize LaTeX math body used in titles."""
    # _{1-x} written as _\{1-x\} in BibTeX
    math_body = re.sub(r"_\\\{([^{}]+)\\\}", r"_{\1}", math_body)
    math_body = re.sub(r"\\_\{([^{}]+)\}", r"_{\1}", math_body)
    math_body = math_body.replace(r"\_", "_")
    return math_body


def clean_title(title: str) -> str:
    # Normalize math before stripping braces so \_\{...\} stays intact.
    title = MATH_SEGMENT.sub(lambda m: f"\\({clean_math(m.group(1))}\\)", title)
    title = strip_case_braces(title)
    title = title.replace(r"{\textendash}", "–")
    title = title.replace(r"\textendash", "–")
    title = title.replace(r"\&", "&")
    title = title.replace(r"\ ", " ")
    title = title.replace("---", "—").replace("--", "–")
    title = re.sub(r"\s+", " ", title).strip()
    # Drop trailing period often present in some exports.
    if title.endswith(".") and not title.endswith(".."):
        title = title[:-1]
    return title


def parse_month(month: str | None) -> int:
    if not month:
        return 0
    month = strip_case_braces(month).strip().lower().rstrip(".")
    if month.isdigit():
        return int(month)
    return MONTHS.get(month, 0)


def abbreviate_author(author: str) -> str:
    """Convert 'Last, First Middle' or 'First Middle Last' to 'F. M. Last'."""
    author = strip_case_braces(author).strip()
    if not author:
        return author

    if "," in author:
        last, given = [p.strip() for p in author.split(",", 1)]
    else:
        parts = author.split()
        if len(parts) == 1:
            return parts[0]
        last = parts[-1]
        given = " ".join(parts[:-1])

    initials = []
    for token in re.split(r"[\s\-]+", given):
        token = token.strip(".")
        if not token:
            continue
        initials.append(f"{token[0].upper()}.")
    if initials:
        return f"{' '.join(initials)} {last}"
    return last


def parse_authors(author_field: str) -> list[str]:
    # BibTeX uses " and " between authors.
    return [abbreviate_author(a) for a in re.split(r"\s+and\s+", author_field) if a.strip()]


def coerce_page_number(value: str):
    """Prefer ints, but keep zero-padded article numbers as strings."""
    if value.isdigit() and (value.startswith("0") and len(value) > 1):
        return value
    try:
        return int(value)
    except ValueError:
        return value


def parse_pages(pages: str) -> dict:
    pages = pages.strip().replace("–", "-").replace("--", "-")
    if not pages:
        return {}
    if "-" in pages:
        start, _, end = pages.partition("-")
        start, end = start.strip(), end.strip()
        if start and end and start != end:
            return {"pages": f"{start}-{end}"}
        if start:
            return {"page_start": coerce_page_number(start)}
    return {"page_start": coerce_page_number(pages)}


def parse_fields(body: str) -> dict[str, str]:
    """Parse key = {value} / key = value pairs from an entry body."""
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        key_match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[i:])
        if not key_match:
            break
        key = key_match.group(1).lower()
        i += key_match.end()
        if i >= n:
            break

        if body[i] == "{":
            depth = 0
            j = i
            while j < n:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            value = body[i + 1 : j]
            i = j + 1
        elif body[i] == '"':
            j = i + 1
            while j < n and body[j] != '"':
                if body[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                j += 1
            value = body[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and body[j] not in ",\n":
                j += 1
            value = body[i:j].strip().rstrip(",")
            i = j

        fields[key] = value.strip()
    return fields


def parse_bib(text: str) -> list[dict]:
    entries = []
    for match in ENTRY_START.finditer(text):
        entry_type = match.group(1).lower()
        citekey = match.group(2)
        start = match.end()
        # Find matching closing brace for the entry.
        depth = 1
        j = start
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[start : j - 1]
        fields = parse_fields(body)
        fields["_type"] = entry_type
        fields["_key"] = citekey
        entries.append(fields)
    return entries


def publication_url(fields: dict) -> str | None:
    doi = fields.get("doi")
    if doi:
        doi = doi.strip().removeprefix("https://doi.org/")
        return f"https://doi.org/{doi}"
    website = fields.get("website")
    if website:
        return website.strip()
    url = fields.get("url")
    if url:
        return url.strip()
    return None


def publisher_name(fields: dict) -> str | None:
    if fields.get("journal"):
        return strip_case_braces(fields["journal"]).strip()
    if fields.get("booktitle"):
        return strip_case_braces(fields["booktitle"]).strip()
    # arXiv / misc preprints often set publisher = {arXiv}
    if fields.get("publisher"):
        return strip_case_braces(fields["publisher"]).strip()
    if fields.get("school"):
        return strip_case_braces(fields["school"]).strip()
    return None


def to_resume_publication(fields: dict) -> dict | None:
    if fields["_type"] not in INCLUDE_TYPES:
        return None
    title = fields.get("title")
    if not title:
        return None

    pub: dict = {
        "name": clean_title(title),
        "_sort_month": parse_month(fields.get("month")),
    }

    if fields.get("author"):
        pub["authors"] = parse_authors(fields["author"])

    publisher = publisher_name(fields)
    if publisher:
        pub["publisher"] = publisher

    year = fields.get("year")
    if year:
        year = strip_case_braces(year).strip()
        try:
            pub["releaseDate"] = int(year)
        except ValueError:
            pub["releaseDate"] = year

    volume = fields.get("volume")
    if volume:
        volume = strip_case_braces(volume).strip()
        try:
            pub["volume"] = int(volume)
        except ValueError:
            pub["volume"] = volume

    number = fields.get("number")
    # Skip arXiv identifiers stored in number (e.g. arXiv:2607.25039).
    if number and not strip_case_braces(number).lower().startswith("arxiv:"):
        number = strip_case_braces(number).strip()
        try:
            pub["issue"] = int(number)
        except ValueError:
            pub["issue"] = number

    if fields.get("pages"):
        # Ignore DOI-like placeholder pages (e.g. acs.chemmater.5c01505).
        pages = strip_case_braces(fields["pages"]).strip()
        if re.search(r"\d", pages) and not re.search(r"[A-Za-z]", pages):
            pub.update(parse_pages(pages))

    url = publication_url(fields)
    if url:
        pub["url"] = url

    return pub


def update_resume(bib_path: Path, resume_path: Path, dry_run: bool = False) -> list[dict]:
    entries = parse_bib(bib_path.read_text(encoding="utf-8"))
    publications = []
    skipped = []
    for entry in entries:
        pub = to_resume_publication(entry)
        if pub is None:
            skipped.append(entry["_key"])
            continue
        publications.append(pub)

    publications.sort(
        key=lambda p: (p.get("releaseDate") or 0, p.get("_sort_month") or 0, p.get("name") or ""),
        reverse=True,
    )
    for pub in publications:
        pub.pop("_sort_month", None)

    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    resume["publications"] = publications

    if not dry_run:
        resume_path.write_text(
            json.dumps(resume, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(publications)} publications to {resume_path}")
    else:
        print(f"Parsed {len(publications)} publications (dry run)")
    if skipped:
        print(f"Skipped {len(skipped)} entries: {', '.join(skipped)}")
    return publications


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bib", type=Path, default=DEFAULT_BIB, help="Path to papers.bib")
    parser.add_argument("--resume", type=Path, default=DEFAULT_RESUME, help="Path to resume.json")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without writing")
    args = parser.parse_args()

    pubs = update_resume(args.bib, args.resume, dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(pubs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
