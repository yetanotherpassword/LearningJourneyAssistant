"""Program-based enrolment and the latent-trait ability model in
lja.data.catalogue_generator, plus the loader's handling of untaken subjects."""

from __future__ import annotations

import random
import statistics
from pathlib import Path

import pytest
from pydantic import ValidationError

from lja.data.catalogue import Catalogue
from lja.data.catalogue_generator import (
    CohortParams,
    enrol_by_program,
    generate_cohort,
    program_trait_means,
    write_workbook,
)
from lja.data.excel_loader import load_dataset
from lja.data.synth_generator import _FALLBACK_TEMPLATES


def _uni(with_traits: bool = True, with_programs: bool = True) -> Catalogue:
    def comp(cid: str, traits):
        return {"id": cid, "label": cid, "traits": traits if with_traits else None}

    def subj(code: str, comps: list[str]):
        return {
            "code": code, "title": code, "year_level": int(code[3]),
            "silos": [{"id": f"SILO{i + 1}", "text": f"{code} outcome {i + 1}", "competency": c} for i, c in enumerate(comps)],
            "assessments": [
                {"name": "Test", "weight": 0.4, "silos": ["SILO1"], "early_assessment": True},
                {"name": "Exam", "weight": 0.6, "silos": [f"SILO{i + 1}" for i in range(len(comps))]},
            ],
        }

    data = {
        "competencies": [comp("quant", [1.0, 0.0]), comp("lab", [0.0, 1.0]), comp("writing", [0.7071, 0.7071])],
        "subjects": [
            subj("MAT1A", ["quant", "quant"]), subj("CHE1A", ["lab", "writing"]), subj("PHY1A", ["quant", "lab"]),
            subj("ENG1A", ["quant", "writing"]), subj("BIO1A", ["lab", "lab"]),
            subj("ENG2A", ["quant", "quant"]), subj("ENG2B", ["quant", "writing"]), subj("BIO2A", ["lab", "writing"]),
            subj("BIO2B", ["lab", "lab"]), subj("CHE2A", ["lab", "quant"]),
        ],
    }
    if with_programs:
        data["programs"] = [
            {"code": "BENG", "title": "Engineering", "intake_share": 2, "rules": [
                {"pattern": ["MAT1A", "PHY1A", "CHE1A"], "year": 1},
                {"pattern": "ENG1*", "year": 1},
                {"pattern": "ENG2*", "year": 2},
                {"pattern": ["BIO2*", "CHE2*"], "year": 2, "take": 1, "core": False},
            ]},
            {"code": "BBIO", "title": "Biology", "intake_share": 1, "rules": [
                {"pattern": ["CHE1A", "BIO1A"], "year": 1},
                {"pattern": ["MAT1A", "PHY1A"], "year": 1, "take": 1, "core": False},
                {"pattern": "BIO2*", "year": 2},
            ]},
        ]
    return Catalogue.model_validate(data)


def _gen(catalogue: Catalogue, seed: int = 1, **kw):
    params = CohortParams(n_students=kw.pop("n_students", 300), **kw)
    return generate_cohort(catalogue, params, feedback_bank=dict(_FALLBACK_TEMPLATES), rng=random.Random(seed)), params


def test_program_rule_must_match_a_subject() -> None:
    data = _uni().model_dump(mode="json", exclude_none=True)
    data["programs"][0]["rules"].append({"pattern": "LAW1*", "year": 1})
    with pytest.raises(ValidationError, match="matches no subject"):
        Catalogue.model_validate(data)


def test_enrolment_follows_program_rules() -> None:
    cat = _uni()
    rng = random.Random(0)
    eng = enrol_by_program(cat, cat.program("BENG"), rng)
    assert {"MAT1A", "PHY1A", "CHE1A", "ENG1A", "ENG2A", "ENG2B"} <= set(eng)
    assert len(set(eng) & {"BIO2A", "BIO2B", "CHE2A"}) == 1  # one elective
    assert len(eng) == 7
    bio = enrol_by_program(cat, cat.program("BBIO"), rng)
    assert {"CHE1A", "BIO1A", "BIO2A", "BIO2B"} <= set(bio)
    assert len(set(bio) & {"MAT1A", "PHY1A"}) == 1
    assert "ENG2A" not in bio


def test_cohort_shares_common_subjects_and_diverges() -> None:
    cohort, _ = _gen(_uni(), n_students=300)
    by_prog = {}
    for s in cohort.students:
        by_prog.setdefault(s.program, []).append(s)
    assert set(by_prog) == {"BENG", "BBIO"}
    assert len(by_prog["BENG"]) > len(by_prog["BBIO"])  # intake_share 2:1
    assert all("CHE1A" in s.subjects for s in cohort.students)  # the shared first-year subject
    assert all("ENG2A" in s.subjects for s in by_prog["BENG"])
    assert not any("ENG2A" in s.subjects for s in by_prog["BBIO"])
    # Every result row belongs to a subject the student is enrolled in.
    enrolled = {s.student_id: set(s.subjects) for s in cohort.students}
    assert all(r.subject_code in enrolled[r.student_id] for r in cohort.results)


def test_program_selection_biases_traits_and_abilities() -> None:
    cat = _uni()
    cohort, params = _gen(cat, n_students=600, program_selection=1.0, planted_gap_fraction=0.0)
    means = program_trait_means(cat, params)
    assert means["BENG"][0] > means["BBIO"][0]  # engineering core leans quant
    assert means["BBIO"][1] > means["BENG"][1]  # biology core leans lab
    eng_quant = statistics.mean(s.abilities["quant"] for s in cohort.students if s.program == "BENG")
    bio_quant = statistics.mean(s.abilities["quant"] for s in cohort.students if s.program == "BBIO")
    eng_lab = statistics.mean(s.abilities["lab"] for s in cohort.students if s.program == "BENG")
    bio_lab = statistics.mean(s.abilities["lab"] for s in cohort.students if s.program == "BBIO")
    assert eng_quant > bio_quant + 1.0
    assert bio_lab > eng_lab + 1.0


def test_latent_share_controls_correlation() -> None:
    cat = _uni(with_programs=False)
    corr = {}
    for share in (0.0, 1.0):
        cohort, _ = _gen(cat, n_students=800, latent_share=share, program_selection=0.0, planted_gap_fraction=0.0)
        q = [s.abilities["quant"] for s in cohort.students]
        w = [s.abilities["writing"] for s in cohort.students]
        corr[share] = statistics.correlation(q, w)
    assert abs(corr[0.0]) < 0.15
    assert corr[1.0] > 0.6  # writing loads 0.71 on the quant axis


def test_planted_gap_only_in_a_competency_the_student_evidences_twice() -> None:
    cat = _uni()
    cohort, _ = _gen(cat, n_students=400, planted_gap_fraction=0.5)
    comp_subjects = cat.competency_subjects()
    assert cohort.planted
    for s in cohort.planted.values():
        assert len(comp_subjects[s.planted_competency] & set(s.subjects)) >= 2


def test_workbook_with_programs_round_trips_and_untaken_subjects_are_absent(tmp_path: Path) -> None:
    cat = _uni()
    cohort, _ = _gen(cat, n_students=20)
    out = tmp_path / "uni.xlsx"
    write_workbook(cat, cohort, out)
    dataset = load_dataset(str(out))
    by_id = {s.student_id: s for s in cohort.students}
    for summary in dataset.student_summaries:
        assert set(summary.subject_totals) == set(by_id[summary.student_id].subjects)
        assert all(v == v for v in summary.subject_totals.values())  # no NaN
