"""Build catalogue subjects from the La Trobe handbook (IOLG-113).

    cd python
    python -m lja.data.handbook --year 2026 --prefix CSE PHY CHE MAT BIO ENG \
        --out ../data-fixtures/handbook/catalogue_raw.yaml

Why the handbook. Scott's workbook SILOs are abbreviations of the published
La Trobe SILOs (compare CSE1OOF SILO1 in both), and the product's whole job
is to reason over La Trobe subjects. handbook.latrobe.edu.au permits
crawling (robots.txt: Allow: /), publishes a sitemap listing every subject
page per year, and each page embeds the subject as JSON (Next.js
__NEXT_DATA__), including an ordered `unit_learning_outcomes` list carrying
the SILO codes. So real SILOs for hundreds of subjects are one polite crawl
away, with no HTML scraping and no LLM invention.

What the handbook does NOT give us server-side: the assessment map (weights,
hurdles, assessment-to-SILO links) is loaded per teaching period by
client-side JavaScript, and that endpoint is not in the page bundles. So
assessments here are SYNTHETIC, drawn from a small library of realistic
patterns keyed by discipline and year level and seeded by subject code, and
every subject is marked `source: handbook` with `assessments_synthetic: true`.
Swap them for real ones if Scott can export the assessment maps.

Competency tags are NOT assigned here. This module only produces subjects
with SILOs; competency_tagger.py groups the SILOs into competencies with
embeddings, because an LLM clustering call already fails at 52 SILOs (see
python/README.md) and hundreds is out of the question.

Politeness: one request per second, a descriptive User-Agent, and a disk
cache so re-runs never re-fetch. The crawled content is La Trobe's; keep the
output under data-fixtures/handbook/ (gitignored) unless the project owner
says it may be committed.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import yaml

HANDBOOK = "https://handbook.latrobe.edu.au"
SITEMAP_INDEX = f"{HANDBOOK}/sitemap.xml"
USER_AGENT = "LJA-catalogue-builder/1.0 (La Trobe CSE5IDP student project; learning-analytics test data)"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass(frozen=True)
class HandbookSubject:
    code: str
    title: str
    year_level: int
    credit_points: int | None
    academic_org: str
    school: str
    description: str
    silos: list[tuple[str, str]]  # (SILO code, text)


# -- listing --------------------------------------------------------------------


def _get(session: requests.Session, url: str, *, delay: float) -> requests.Response:
    time.sleep(delay)
    return session.get(url, timeout=60)


def list_subject_codes(session: requests.Session, year: int, prefixes: list[str], *, delay: float = 1.0) -> list[str]:
    """Every subject code the sitemap lists for `year` whose prefix is wanted."""
    index = _get(session, SITEMAP_INDEX, delay=delay).text
    codes: set[str] = set()
    wanted = tuple(p.upper() for p in prefixes)
    for sitemap_url in re.findall(r"<loc>([^<]+)</loc>", index):
        body = _get(session, sitemap_url, delay=delay).text
        for url in re.findall(r"<loc>([^<]+)</loc>", body):
            m = re.search(rf"/subjects/{year}/([A-Z]+[0-9][A-Z0-9]*)$", url)
            if m and m.group(1).startswith(wanted):
                codes.add(m.group(1))
    return sorted(codes)


# -- fetching + parsing ---------------------------------------------------------


def _clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalise_silo_text(raw: str) -> str:
    """Handbook SILOs are capitalised sentences, sometimes with semicolons.
    The workbook loader splits SILO cells on ';' and the feedback templates
    read '...command of {silos}', so: drop tags, swap ';' for ',', strip the
    trailing full stop, and lower-case the leading verb."""
    text = _clean_text(raw).replace(";", ",").rstrip(". ")
    return text[:1].lower() + text[1:] if text else text


def parse_subject_page(html: str) -> HandbookSubject | None:
    m = _NEXT_DATA.search(html)
    if not m:
        return None
    data = json.loads(m.group(1))
    pc = data.get("props", {}).get("pageProps", {}).get("pageContent") or {}
    if not pc.get("code"):
        return None
    silos: list[tuple[str, str]] = []
    for lo in sorted(pc.get("unit_learning_outcomes") or [], key=lambda x: int(x.get("order") or 0)):
        text = lo.get("description") or lo.get("learning_outcome") or ""
        code = lo.get("code") or f"SILO{lo.get('order')}"
        if text.strip():
            silos.append((code, normalise_silo_text(text)))
    level = pc.get("level") or {}
    try:
        year_level = int(level.get("value") or 0)
    except (TypeError, ValueError):
        year_level = 0
    if not 1 <= year_level <= 6:
        year_level = max(1, min(6, int(pc["code"][3]) if pc["code"][3:4].isdigit() else 1))
    cp = pc.get("credit_points")
    return HandbookSubject(
        code=pc["code"],
        title=_clean_text(pc.get("title") or "").title(),
        year_level=year_level,
        credit_points=int(cp) if str(cp).isdigit() else None,
        academic_org=(pc.get("academic_org") or {}).get("value", ""),
        school=(pc.get("school") or {}).get("value", ""),
        description=_clean_text(pc.get("description") or "")[:600],
        silos=silos,
    )


def fetch_subject(session: requests.Session, year: int, code: str, cache_dir: Path, *, delay: float = 1.0) -> HandbookSubject | None:
    cache = cache_dir / str(year) / f"{code}.html"
    if cache.exists():
        html = cache.read_text(encoding="utf-8")
    else:
        resp = _get(session, f"{HANDBOOK}/subjects/{year}/{code}", delay=delay)
        if resp.status_code != 200:
            return None
        html = resp.text
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    return parse_subject_page(html)


# -- synthetic assessment maps --------------------------------------------------

# (name, weight, contribution, early) patterns by discipline group. Weights in
# each pattern sum to 1. Every pattern's LAST entry is the broad one that gets
# any SILO the others missed.
_PATTERNS: dict[str, list[list[tuple[str, float, str, bool]]]] = {
    "computing": [
        [("Assignment 1", 0.2, "Individual", True), ("Assignment 2", 0.3, "Individual", False), ("Examination", 0.5, "Individual", False)],
        [("Weekly quizzes", 0.1, "Individual", True), ("Assignment", 0.3, "Individual", False), ("Practical demonstration", 0.2, "Individual", False), ("Examination", 0.4, "Individual", False)],
        [("Project stage 1", 0.3, "Group", True), ("Project stage 2", 0.4, "Combined", False), ("Report", 0.3, "Individual", False)],
    ],
    "laboratory": [
        [("Laboratory reports", 0.3, "Individual", True), ("Mid-semester test", 0.2, "Individual", False), ("Examination", 0.5, "Individual", False)],
        [("Practical portfolio", 0.25, "Individual", True), ("Research report", 0.25, "Group", False), ("Examination", 0.5, "Individual", False)],
        [("Laboratory notebook", 0.2, "Individual", True), ("Assignment", 0.2, "Individual", False), ("Practical examination", 0.2, "Individual", False), ("Examination", 0.4, "Individual", False)],
    ],
    "quantitative": [
        [("Weekly problem sets", 0.2, "Individual", True), ("Mid-semester test", 0.2, "Individual", False), ("Examination", 0.6, "Individual", False)],
        [("Assignment 1", 0.15, "Individual", True), ("Assignment 2", 0.15, "Individual", False), ("Test", 0.2, "Individual", False), ("Examination", 0.5, "Individual", False)],
    ],
    "engineering": [
        [("Laboratory work", 0.2, "Individual", True), ("Design project", 0.3, "Group", False), ("Examination", 0.5, "Individual", False)],
        [("Tutorial problems", 0.1, "Individual", True), ("Design assignment", 0.3, "Individual", False), ("Project report", 0.2, "Group", False), ("Examination", 0.4, "Individual", False)],
    ],
    "project": [
        [("Project proposal", 0.15, "Individual", True), ("Progress presentation", 0.15, "Group", False), ("Final report", 0.45, "Individual", False), ("Final presentation", 0.25, "Group", False)],
    ],
}

_GROUP_BY_PREFIX = {
    "CSE": "computing", "MAT": "quantitative", "STA": "quantitative", "PHY": "laboratory", "AST": "quantitative",
    "CHE": "laboratory", "BIO": "laboratory", "BCH": "laboratory", "MIC": "laboratory", "GEN": "laboratory",
    "ZOO": "laboratory", "BOT": "laboratory", "ANA": "laboratory", "HBS": "laboratory", "ENV": "laboratory",
    "AGR": "laboratory", "SCI": "laboratory", "ENG": "engineering", "ELE": "engineering", "CIV": "engineering",
    "EEE": "engineering", "MEC": "engineering",
}


def discipline_group(code: str, title: str = "") -> str:
    t = title.lower()
    if any(w in t for w in ("capstone", "project", "thesis", "research project", "industry")):
        return "project"
    return _GROUP_BY_PREFIX.get(code[:3], "laboratory")


def synthetic_assessments(subject: HandbookSubject, *, seed: int = 0) -> list[dict]:
    """Deterministic per subject code: the same code always gets the same map."""
    rng = random.Random(f"{seed}:{subject.code}")
    pattern = rng.choice(_PATTERNS[discipline_group(subject.code, subject.title)])
    silo_ids = [sid for sid, _ in subject.silos]
    n = len(silo_ids)
    out = []
    covered: set[str] = set()
    for i, (name, weight, contribution, early) in enumerate(pattern):
        is_last = i == len(pattern) - 1
        if is_last:
            # The broad one: everything not yet covered, plus a majority slice.
            chosen = sorted(set(silo_ids) - covered) or silo_ids[: max(1, n // 2)]
            extra = [s for s in silo_ids if s not in chosen]
            chosen = chosen + rng.sample(extra, k=min(len(extra), max(0, (n * 2) // 3 - len(chosen))))
        else:
            k = max(1, min(n, rng.randint(1, max(1, n // 2 + 1))))
            chosen = rng.sample(silo_ids, k=k)
        chosen = [s for s in silo_ids if s in chosen]  # keep catalogue order
        covered.update(chosen)
        out.append({"name": name, "weight": weight, "contribution": contribution, "early_assessment": early, "silos": chosen})
    return out


# -- catalogue output -----------------------------------------------------------


def to_catalogue_subject(subject: HandbookSubject, *, seed: int = 0) -> dict:
    return {
        "code": subject.code,
        "title": subject.title,
        "year_level": subject.year_level,
        "source": "handbook",
        "discipline": subject.code[:3],
        "credit_points": subject.credit_points,
        "assessments_synthetic": True,
        "silos": [{"id": sid, "text": text, "competency": "untagged"} for sid, text in subject.silos],
        "assessments": synthetic_assessments(subject, seed=seed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build catalogue subjects from the La Trobe handbook (IOLG-113)")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--prefix", nargs="+", required=True, help="Subject code prefixes, e.g. CSE PHY CHE")
    parser.add_argument("--codes-file", default=None, help="Skip the sitemap and use these codes (one per line)")
    parser.add_argument("--cache-dir", default="../data-fixtures/handbook/cache")
    parser.add_argument("--out", required=True, help="Raw catalogue YAML (SILOs tagged 'untagged'; run competency_tagger next)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument("--seed", type=int, default=0, help="Seed for the synthetic assessment maps")
    parser.add_argument("--limit", type=int, default=None, help="Stop after this many subjects (for a dry run)")
    args = parser.parse_args(argv)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    cache_dir = Path(args.cache_dir)

    if args.codes_file:
        codes = [c.strip() for c in Path(args.codes_file).read_text().splitlines() if c.strip() and not c.startswith("#")]
        codes = [c for c in codes if c.startswith(tuple(p.upper() for p in args.prefix))]
    else:
        print("Listing subject codes from the sitemap...", flush=True)
        codes = list_subject_codes(session, args.year, args.prefix, delay=args.delay)
    if args.limit:
        codes = codes[: args.limit]
    print(f"{len(codes)} subject codes for {args.year} with prefixes {args.prefix}", flush=True)

    subjects: list[dict] = []
    skipped: list[str] = []
    for i, code in enumerate(codes, 1):
        subject = fetch_subject(session, args.year, code, cache_dir, delay=args.delay)
        if subject is None or len(subject.silos) < 2:
            skipped.append(code)
        else:
            subjects.append(to_catalogue_subject(subject, seed=args.seed))
        if i % 25 == 0 or i == len(codes):
            print(f"  {i}/{len(codes)} fetched, {len(subjects)} usable", flush=True)

    out = {
        "version": 1,
        "title": f"La Trobe handbook {args.year} subjects ({' '.join(args.prefix)}) -- SILOs real, assessments synthetic, competencies untagged",
        "competencies": [{"id": "untagged", "label": "Untagged", "description": "Placeholder until competency_tagger.py runs."}],
        "subjects": subjects,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.out).open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=110)
    n_silos = sum(len(s["silos"]) for s in subjects)
    print(f"Wrote {args.out}: {len(subjects)} subjects, {n_silos} SILOs. Skipped {len(skipped)}: {skipped[:15]}{' ...' if len(skipped) > 15 else ''}")
    print("Next: python -m lja.data.competency_tagger", args.out, "--out <tagged.yaml>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
