"""Tests for lja.data.catalogue: the model's validation rules, and the claim
that the three supplied subjects are carried VERBATIM from the supplied
workbook (checked against the workbook itself, not a copy of it).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lja.data.catalogue import (
    Catalogue,
    catalogue_to_dataset_shape,
    ground_truth_clustering,
    load_catalogue,
    save_catalogue,
)
from lja.data.excel_loader import load_dataset

_REPO = Path(__file__).resolve().parents[2]
_CATALOGUE = _REPO / "data-fixtures" / "subject_catalogue.yaml"
_SUPPLIED_XLSX = _REPO / "data-fixtures" / "CSE_results_150_students_3_Subjects.xlsx"


def _minimal(**overrides) -> dict:
    base = {
        "competencies": [{"id": "alpha", "label": "Alpha"}, {"id": "beta", "label": "Beta"}],
        "subjects": [
            {
                "code": "SUBA",
                "title": "Subject A",
                "year_level": 1,
                "silos": [
                    {"id": "SILO1", "text": "do alpha things", "competency": "alpha"},
                    {"id": "SILO2", "text": "do beta things", "competency": "beta"},
                ],
                "assessments": [
                    {"name": "Test", "weight": 0.4, "silos": ["SILO1"]},
                    {"name": "Exam", "weight": 0.6, "silos": ["SILO1", "SILO2"]},
                ],
            },
            {
                "code": "SUBB",
                "title": "Subject B",
                "year_level": 2,
                "silos": [{"id": "SILO1", "text": "more alpha", "competency": "alpha"}],
                "assessments": [{"name": "Exam", "weight": 1.0, "silos": ["SILO1"]}],
            },
        ],
    }
    base.update(overrides)
    return base


def test_repo_catalogue_loads_and_is_wide() -> None:
    catalogue = load_catalogue(_CATALOGUE)
    assert len(catalogue.subjects) >= 12
    assert sum(len(s.silos) for s in catalogue.subjects) >= 50
    # Every competency should be evidenced by 2+ subjects, otherwise it can
    # never be a 'persistent gap' and is dead weight in the ground truth.
    assert set(catalogue.cross_subject_competencies()) == {c.id for c in catalogue.competencies}


@pytest.mark.skipif(not _SUPPLIED_XLSX.exists(), reason="supplied workbook not present")
def test_supplied_subjects_match_the_workbook_verbatim() -> None:
    catalogue = load_catalogue(_CATALOGUE)
    supplied = {s.code for s in catalogue.subjects if s.source == "supplied"}
    assert supplied == {"CSE1OOF", "CSE2ALG", "CSE3CAP"}

    real = load_dataset(str(_SUPPLIED_XLSX))
    shape = catalogue_to_dataset_shape(catalogue)
    assert {k: v for k, v in shape.silos.items() if k.split(":")[0] in supplied} == real.silos
    assert [a for a in shape.assessments if a.subject_code in supplied] == real.assessments


def test_ground_truth_clustering_covers_every_silo() -> None:
    catalogue = load_catalogue(_CATALOGUE)
    clustering = ground_truth_clustering(catalogue)
    covered = {f"{m.subject_code}:{m.silo_local_id}" for c in clustering.clusters for m in c.members}
    assert covered == set(catalogue.silo_key_to_competency())
    assert {c.competency_label for c in clustering.clusters} == {c.label for c in catalogue.competencies}


def test_moodle_assignment_defaults_positionally() -> None:
    catalogue = Catalogue.model_validate(_minimal())
    names = [a.moodle_assignment for a in catalogue.subject("SUBA").assessments]
    assert names == ["Assignment 1", "Assignment 2"]


def test_weights_must_sum_to_one() -> None:
    data = _minimal()
    data["subjects"][0]["assessments"][0]["weight"] = 0.5
    with pytest.raises(ValidationError, match="weights sum"):
        Catalogue.model_validate(data)


def test_unknown_competency_rejected() -> None:
    data = _minimal()
    data["subjects"][1]["silos"][0]["competency"] = "gamma"
    with pytest.raises(ValidationError, match="unknown competency"):
        Catalogue.model_validate(data)


def test_unknown_silo_in_assessment_rejected() -> None:
    data = _minimal()
    data["subjects"][1]["assessments"][0]["silos"] = ["SILO9"]
    with pytest.raises(ValidationError, match="unknown SILO"):
        Catalogue.model_validate(data)


def test_semicolon_in_silo_text_rejected() -> None:
    data = _minimal()
    data["subjects"][0]["silos"][0]["text"] = "alpha; beta"
    with pytest.raises(ValidationError, match="';'"):
        Catalogue.model_validate(data)


def test_round_trip_through_yaml(tmp_path: Path) -> None:
    catalogue = Catalogue.model_validate(_minimal())
    out = tmp_path / "c.yaml"
    save_catalogue(catalogue, out)
    assert load_catalogue(out) == catalogue
