"""Draft new subjects for the catalogue with the LLM (IOLG-113).

    cd python
    python -m lja.data.catalogue_draft ../data-fixtures/subject_catalogue.yaml \
        --subject CSE2OSA "Operating Systems and Architecture" 2 \
        --subject CSE3MLA "Machine Learning Applications" 3 \
        --out ../data-fixtures/subject_catalogue.yaml

Writing 30 subjects' worth of plausible SILOs and assessment maps by hand
is the tedious part of scaling the test data, and it is exactly the kind of
varied, grounded text an LLM is good for (devenv/README.md, "Synthetic
data"). The model is shown the existing competency list and the supplied
subjects as style examples, asked for a structured draft, and the draft is
merged into the base catalogue and validated by the same Pydantic model
everything else uses -- so a draft that violates the catalogue's rules
(weights not summing to 1, unknown competency, semicolons in SILO text)
never lands. New competencies are allowed but reported loudly, because each
one is a claim about the degree's structure a person should look at.

Drafted subjects are marked `source: synthetic`; the three supplied
subjects stay `supplied` and are never rewritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .catalogue import Catalogue, load_catalogue, save_catalogue


class DraftSilo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    competency: str


class DraftAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    weight: float
    contribution: str
    early_assessment: bool
    hurdle: bool
    silos: list[str]


class DraftSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    year_level: int
    silos: list[DraftSilo]
    assessments: list[DraftAssessment]


class DraftCompetency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[DraftSubject]
    new_competencies: list[DraftCompetency] = []


_SYSTEM_PROMPT = """You are helping a university learning-analytics team build SYNTHETIC test data. \
You will draft Subject Intended Learning Outcomes (SILOs) and an assessment map for computer science \
subjects. Nothing you write describes a real subject; it must simply be plausible, in the style of \
the examples given.

Rules:
- Each subject gets 4 or 5 SILOs with ids "SILO1", "SILO2", ... numbered from 1 within the subject.
- SILO text is a lower-case GERUND noun phrase naming the capability, exactly like the examples -- \
"identifying data structures and searching and sorting algorithms in computing contexts" -- so it reads \
naturally after "a strong command of ...". 8-25 words, NO semicolons anywhere in the text. Use Australian \
English spelling (analysing, optimising). Start with an observable -ing verb (applying, designing, \
evaluating, implementing, explaining); never "understanding" or "knowing", which cannot be assessed.
- Every SILO is tagged with the id of ONE competency from the list provided. Prefer an existing \
competency; only propose a new competency (in new_competencies, with a short kebab-case id, a label \
and a one-sentence description) if none genuinely fits, and then tag the SILO with that new id.
- Each subject gets 3 or 4 assessments. Weights are decimals that sum to exactly 1.0. Contribution is \
"Individual", "Group" or "Combined". Exactly one assessment is early_assessment=true. Each assessment \
lists 1-4 of the subject's SILO ids. Every SILO must appear in at least one assessment.
- Assessment names are short, like "Test", "Assignment", "Practical portfolio", "Central examination".
- Use the requested subject code, title and year level exactly as given.
"""


def _user_prompt(base: Catalogue, requests: list[tuple[str, str, int]]) -> str:
    lines = ["Existing competencies (tag SILOs with these ids):"]
    for c in base.competencies:
        lines.append(f"- {c.id}: {c.label}. {c.description}".rstrip())
    lines.append("")
    lines.append("Style examples (real subjects already in the catalogue -- match this register):")
    for s in [s for s in base.subjects if s.source == "supplied"][:2]:
        lines.append(f"Subject {s.code} {s.title} (year {s.year_level}):")
        for silo in s.silos:
            lines.append(f"  {silo.id} [{silo.competency}]: {silo.text}")
        for a in s.assessments:
            lines.append(f"  assessment {a.name!r} weight {a.weight} {a.contribution} early={a.early_assessment} silos={a.silos}")
    lines.append("")
    lines.append("Draft these subjects now:")
    for code, title, year in requests:
        lines.append(f"- code {code}, title {title!r}, year level {year}")
    return "\n".join(lines)


def _normalise_weights(weights: list[float]) -> list[float]:
    """Round to 2 dp and push any rounding residue onto the largest weight,
    so a draft that sums to 0.99 or 1.01 lands rather than being rejected
    for what is a formatting slip."""
    total = sum(weights)
    if total <= 0:
        return weights
    scaled = [round(w / total, 2) for w in weights]
    residue = round(1.0 - sum(scaled), 2)
    if residue:
        i = max(range(len(scaled)), key=lambda k: scaled[k])
        scaled[i] = round(scaled[i] + residue, 2)
    return scaled


def merge_draft(base: Catalogue, draft: Draft) -> Catalogue:
    data = base.model_dump(mode="json", exclude_none=True)
    existing_codes = {s["code"] for s in data["subjects"]}
    existing_comps = {c["id"] for c in data["competencies"]}
    for c in draft.new_competencies:
        if c.id not in existing_comps:
            data["competencies"].append(c.model_dump())
            existing_comps.add(c.id)
    for s in draft.subjects:
        if s.code in existing_codes:
            raise ValueError(f"draft subject {s.code} already exists in the catalogue; not overwriting")
        subject = s.model_dump()
        subject["source"] = "synthetic"
        weights = _normalise_weights([a["weight"] for a in subject["assessments"]])
        for a, w in zip(subject["assessments"], weights):
            a["weight"] = w
        data["subjects"].append(subject)
    return Catalogue.model_validate(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft new catalogue subjects with the LLM (IOLG-113)")
    parser.add_argument("base", help="Existing catalogue YAML to extend")
    parser.add_argument("--subject", nargs=3, action="append", metavar=("CODE", "TITLE", "YEAR"), required=True,
                        help="A subject to draft; repeat for several")
    parser.add_argument("--out", required=True, help="Where to write the merged catalogue (may equal base)")
    parser.add_argument("--raw-out", default=None,
                        help="Also dump the model's raw draft JSON here (defaults to <out>.draft.json)")
    args = parser.parse_args(argv)

    from ..llm.factory import get_llm_client

    base = load_catalogue(args.base)
    requests = [(code, title, int(year)) for code, title, year in args.subject]
    client = get_llm_client()
    print(f"LLM: {client.describe()}")
    print(f"Drafting {len(requests)} subject(s)...")
    draft = client.complete_structured(system=_SYSTEM_PROMPT, user=_user_prompt(base, requests), schema=Draft)
    print(f"LLM usage: {client.usage_summary()}")

    raw_out = Path(args.raw_out) if args.raw_out else Path(args.out).with_suffix(".draft.json")
    raw_out.write_text(json.dumps(draft.model_dump(), indent=2))
    print(f"Raw draft saved to {raw_out}")

    try:
        merged = merge_draft(base, draft)
    except (ValidationError, ValueError) as exc:
        print(f"\nDraft rejected by catalogue validation -- fix the raw draft or re-run:\n{exc}", file=sys.stderr)
        return 1

    save_catalogue(merged, args.out)
    print(f"Wrote {args.out}: now {len(merged.subjects)} subjects, {len(merged.competencies)} competencies.")
    if draft.new_competencies:
        print("\nNEW competencies proposed by the model -- review these, they change the ground truth:")
        for c in draft.new_competencies:
            print(f"  {c.id}: {c.label} -- {c.description}")
    for s in draft.subjects:
        print(f"  {s.code}: {len(s.silos)} SILOs, {len(s.assessments)} assessments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
