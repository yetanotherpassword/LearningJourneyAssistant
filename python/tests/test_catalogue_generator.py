"""Tests for the catalogue-driven cohort generator and the Moodle emitters.
Everything runs on the built-in feedback/remark templates: no LLM."""

from __future__ import annotations

import csv
import json
import random
import statistics
from pathlib import Path

import pytest

from lja.data.catalogue import Catalogue, load_catalogue
from lja.data.catalogue_generator import (
    CohortParams,
    generate_cohort,
    write_truth_files,
    write_workbook,
)
from lja.data.excel_loader import load_dataset
from lja.data.moodle_emitters import _FRAMEWORK_COLUMNS, effective_criteria, write_moodle_fixtures
from lja.data.synth_generator import _FALLBACK_TEMPLATES
from lja.model.gap_detection import compute_gaps
from lja.model.silo_clustering import SiloClusteringResult

_REPO = Path(__file__).resolve().parents[2]
_CATALOGUE = _REPO / "data-fixtures" / "subject_catalogue.yaml"
_EXISTING_FRAMEWORK = _REPO / "data-fixtures" / "competency_framework_cse5idp.csv"


def _small() -> Catalogue:
    return Catalogue.model_validate(
        {
            "competencies": [{"id": "alpha", "label": "Alpha"}, {"id": "beta", "label": "Beta"}, {"id": "gamma", "label": "Gamma"}],
            "subjects": [
                {
                    "code": "SUBA", "title": "A", "year_level": 1,
                    "silos": [
                        {"id": "SILO1", "text": "alpha one", "competency": "alpha"},
                        {"id": "SILO2", "text": "beta one", "competency": "beta"},
                        {"id": "SILO3", "text": "gamma one", "competency": "gamma"},
                    ],
                    "assessments": [
                        {"name": "Test", "weight": 0.3, "silos": ["SILO1"], "early_assessment": True},
                        {"name": "Assignment", "weight": 0.3, "silos": ["SILO2"]},
                        {"name": "Exam", "weight": 0.4, "silos": ["SILO3"]},
                    ],
                },
                {
                    "code": "SUBB", "title": "B", "year_level": 2,
                    "silos": [
                        {"id": "SILO1", "text": "alpha two", "competency": "alpha"},
                        {"id": "SILO2", "text": "beta two", "competency": "beta"},
                        {"id": "SILO3", "text": "gamma two", "competency": "gamma"},
                    ],
                    "assessments": [
                        {"name": "Test", "weight": 0.5, "silos": ["SILO1"]},
                        {"name": "Exam", "weight": 0.5, "silos": ["SILO2", "SILO3"]},
                    ],
                },
            ],
        }
    )


def _gen(catalogue: Catalogue, seed: int = 1, **kw):
    params = CohortParams(n_students=kw.pop("n_students", 60), **kw)
    return generate_cohort(catalogue, params, feedback_bank=dict(_FALLBACK_TEMPLATES), rng=random.Random(seed))


def test_deterministic_for_a_seed() -> None:
    a = _gen(_small(), seed=7)
    b = _gen(_small(), seed=7)
    assert a.results == b.results
    assert a.summaries == b.summaries
    assert _gen(_small(), seed=8).results != a.results


def test_every_student_gets_every_assessment_by_default() -> None:
    cohort = _gen(_small(), n_students=10)
    assert len(cohort.results) == 10 * 5
    assert all(len(s.subject_totals) == 2 for s in cohort.summaries)
    assert all(1 <= r.score <= 100 for r in cohort.results)


def test_planted_students_are_weak_in_the_planted_competency() -> None:
    cohort = _gen(_small(), n_students=200, planted_gap_fraction=0.3, planted_gap_competencies=("beta",))
    planted = cohort.planted
    assert 30 <= len(planted) <= 90
    silo_comp = _small().silo_key_to_competency()
    deficits = []
    for sid, student in planted.items():
        assert student.planted_competency == "beta"
        by_comp: dict[str, list[float]] = {}
        for r in cohort.results:
            if r.student_id == sid:
                for silo in r.silo_ids:
                    by_comp.setdefault(silo_comp[f"{r.subject_code}:{silo}"], []).append(r.score)
        beta = statistics.mean(by_comp["beta"])
        others = statistics.mean(by_comp["alpha"] + by_comp["gamma"])
        # Every planted student is below their own other competencies; the
        # depth (18-30 points) shows up clearly in aggregate, but a single
        # student whose other abilities also happen to be low can sit closer.
        assert beta < others, (sid, beta, others)
        deficits.append(others - beta)
    assert statistics.mean(deficits) > 15


def test_competency_sd_zero_reproduces_flat_profiles() -> None:
    flat = _gen(_small(), n_students=100, competency_sd=0.0, noise_sd=0.0, planted_gap_fraction=0.0)
    for student in flat.students:
        scores = {r.score for r in flat.results if r.student_id == student.student_id}
        assert max(scores) - min(scores) <= 1  # rounding only


def test_enrolment_fraction_keeps_planted_students_in_their_gap_subjects() -> None:
    cohort = _gen(_small(), n_students=150, enrolment_fraction=0.5, planted_gap_fraction=0.5)
    assert any(len(s.subjects) < 2 for s in cohort.students) is False  # min_subjects=2 of 2
    for student in cohort.planted.values():
        assert set(student.subjects) == {"SUBA", "SUBB"}


def test_workbook_round_trips_through_the_loader(tmp_path: Path) -> None:
    catalogue = _small()
    cohort = _gen(catalogue, n_students=12)
    out = tmp_path / "cohort.xlsx"
    write_workbook(catalogue, cohort, out)
    dataset = load_dataset(str(out))
    assert set(dataset.silos) == set(catalogue.silo_key_to_competency())
    assert [(a.subject_code, a.assessment_name, a.weight, a.silo_ids) for a in dataset.assessments] == [
        (s.code, a.name, a.weight, tuple(a.silos)) for s in catalogue.subjects for a in s.assessments
    ]
    assert len(dataset.results) == len(cohort.results)
    assert [s.student_id for s in dataset.student_summaries] == [s.student_id for s in cohort.summaries]
    assert all(r.feedback_comment for r in dataset.results)


def test_truth_clustering_runs_the_real_gap_detector(tmp_path: Path) -> None:
    catalogue = _small()
    cohort = _gen(catalogue, n_students=80, planted_gap_fraction=0.2)
    out = tmp_path / "cohort.xlsx"
    write_workbook(catalogue, cohort, out)
    paths = write_truth_files(catalogue, cohort, CohortParams(n_students=80), 1, "c.yaml", out)
    clustering = SiloClusteringResult.model_validate_json(paths["clustering"].read_text())
    dataset = load_dataset(str(out))
    gaps = compute_gaps(dataset, clustering)
    assert {g.student_id for g in gaps} == {s.student_id for s in cohort.students}
    truth = json.loads(paths["truth"].read_text())
    assert set(truth["planted"]) == set(cohort.planted)
    review = json.loads(paths["review"].read_text())
    assert all(r["state"] == "confirmed" for r in review["reviews"].values())


def test_repo_catalogue_generates_at_scale() -> None:
    catalogue = load_catalogue(_CATALOGUE)
    cohort = _gen(catalogue, n_students=50)
    n_assessments = sum(len(s.assessments) for s in catalogue.subjects)
    assert len(cohort.results) == 50 * n_assessments


# -- Moodle emitters ----------------------------------------------------------


def test_effective_criteria_derive_from_silos_when_no_rubric() -> None:
    subject = _small().subject("SUBB")
    criteria = effective_criteria(subject, subject.assessments[1])
    assert [(c.text, c.silo) for c in criteria] == [("Beta two", "SILO2"), ("Gamma two", "SILO3")]


def test_moodle_fixtures_written(tmp_path: Path) -> None:
    catalogue = _small()
    cohort = _gen(catalogue, n_students=9)
    written = write_moodle_fixtures(catalogue, cohort, tmp_path / "m", n_students=4)
    names = {p.name for p in written}
    assert {"competency_framework_SUBA.csv", "competency_framework_SUBB.csv", "criterion_silo_map.csv",
            "rubric_fixture.json", "seed_subjects.txt"} <= names

    with (tmp_path / "m" / "competency_framework_SUBA.csv").open(newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == _FRAMEWORK_COLUMNS
    if _EXISTING_FRAMEWORK.exists():
        with _EXISTING_FRAMEWORK.open(newline="") as f:
            assert next(csv.reader(f)) == rows[0]
    assert rows[1][12] == "1" and rows[1][0] == ""  # framework row
    assert [r[1] for r in rows[2:]] == ["SUBA-SILO1", "SUBA-SILO2", "SUBA-SILO3"]

    with (tmp_path / "m" / "criterion_silo_map.csv").open(newline="") as f:
        cmap = list(csv.DictReader(f))
    assert len(cmap) == 1 + 1 + 1 + 1 + 2  # SUBA: 3 single-SILO assessments; SUBB: 1 + 2
    assert cmap[0] == {"subject_code": "SUBA", "assessment_name": "Assignment 1", "criterion_text": "Alpha one",
                       "silo_key": "SUBA:SILO1", "weight": "1.0"}

    fixtures = json.loads((tmp_path / "m" / "rubric_fixture.json").read_text())
    assert len(fixtures) == 5
    first = fixtures[0]
    assert first["course"] == "SUBA" and first["assignment"] == "Assignment 1"
    assert len(first["students"]) == 4
    for st in first["students"]:
        assert len(st["scores"]) == len(first["criteria"]) == len(st["remarks"])
        assert all(0 <= s <= 3 for s in st["scores"])
        assert all("{criterion}" not in r and r for r in st["remarks"])

    assert (tmp_path / "m" / "seed_subjects.txt").read_text() == "SUBA\nSUBB\n"


def test_repo_catalogue_keeps_the_iolg56_criterion_map(tmp_path: Path) -> None:
    """The hand-built CSE1IOI map from IOLG-56 must be a subset of what the
    catalogue emits, so the two fixtures agree on what Assignment 1 assesses."""
    catalogue = load_catalogue(_CATALOGUE)
    cohort = _gen(catalogue, n_students=5)
    write_moodle_fixtures(catalogue, cohort, tmp_path / "m", n_students=5)
    with (tmp_path / "m" / "criterion_silo_map.csv").open(newline="") as f:
        emitted = {(r["subject_code"], r["assessment_name"], r["criterion_text"], r["silo_key"]) for r in csv.DictReader(f)}
    existing = _REPO / "data-fixtures" / "criterion_silo_map_CSE1IOI.csv"
    if not existing.exists():
        pytest.skip("IOLG-56 map not on this branch")
    with existing.open(newline="") as f:
        wanted = {(r["subject_code"], r["assessment_name"], r["criterion_text"], r["silo_key"]) for r in csv.DictReader(f)}
    assert wanted <= emitted
