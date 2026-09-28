"""Tests for lja.export -- driven through main() end to end, the way
test_plan_cli.py drives lja.plan.

The dataset loader is monkeypatched to hand back a small in-memory LjaDataset
(so no real workbook or pandas parse is needed), but compute_gaps, the trend
derivation and the CSV/manifest writing all run for real against a genuine
clustering cache written to tmp_path -- those are the code under test. The
in-memory fixtures mirror the helpers at tests/test_dashboard.py L19-37.
"""

from __future__ import annotations

import csv
import dataclasses
import json

import lja.export as export_module
from lja.data.excel_loader import LjaDataset, ResultRow, StudentSummary
from lja.model.gap_detection import GapThresholds, compute_gaps
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef

_REAL_IDS = ("STU0001", "STU0002")


def _result(student_id: str, subject_code: str, score: float) -> ResultRow:
    return ResultRow(
        student_id=student_id,
        subject_code=subject_code,
        assessment_name="Test",
        score=score,
        feedback_comment="",
        weight=1.0,
        weighted_score=score,
        silo_ids=("SILO1",),
    )


def _dataset() -> LjaDataset:
    # Two subjects, each carrying one SILO that the clustering groups into a
    # single cross-subject competency, so every (student, competency) pair has
    # evidence from both subjects -> one gap row per student.
    results = [
        _result("STU0001", "CSE1OOF", 80.0),
        _result("STU0001", "CSE2ALG", 40.0),
        _result("STU0002", "CSE1OOF", 30.0),
        _result("STU0002", "CSE2ALG", 35.0),
    ]
    summaries = [
        StudentSummary(
            student_id="STU0001",
            subject_totals={"CSE1OOF": 80.0, "CSE2ALG": 40.0},
            average_total=60.0,
            performance_band="Credit",
        ),
        StudentSummary(
            student_id="STU0002",
            subject_totals={"CSE1OOF": 30.0},  # did not sit CSE2ALG -> blank cell, not 0
            average_total=32.5,
            performance_band="Fail",
        ),
    ]
    return LjaDataset(silos={}, assessments=[], results=results, student_summaries=summaries)


def _clustering() -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Problem Solving",
                rationale="test",
                members=[
                    SiloRef(subject_code="CSE1OOF", silo_local_id="SILO1"),
                    SiloRef(subject_code="CSE2ALG", silo_local_id="SILO1"),
                ],
            )
        ]
    )


def _run(monkeypatch, tmp_path, extra_args=(), *, dataset=None, clustering=None):
    """Write a real clustering cache, patch only the dataset loader, run main()."""
    dataset = dataset or _dataset()
    clustering = clustering or _clustering()
    tmp_path.mkdir(parents=True, exist_ok=True)
    cache = tmp_path / "silo_clustering.json"
    cache.write_text(clustering.model_dump_json())
    out = tmp_path / "export"

    monkeypatch.setattr(export_module, "load_dataset_for_source", lambda *_a, **_k: dataset)

    code = export_module.main(
        ["dummy.xlsx", "--clustering-cache", str(cache), "--out", str(out), *extra_args]
    )
    return code, out


def _rows(path):
    with path.open(newline="") as f:
        return list(csv.reader(f))


def test_competencies_has_one_row_per_gap(monkeypatch, tmp_path):
    dataset, clustering = _dataset(), _clustering()
    expected = len(compute_gaps(dataset, clustering, thresholds=GapThresholds()))

    code, out = _run(monkeypatch, tmp_path, dataset=dataset, clustering=clustering)

    assert code == 0
    rows = _rows(out / "competencies.csv")
    assert len(rows) - 1 == expected  # minus the header
    assert expected == 2  # guards the fixture itself: one gap per student


def test_manifest_has_schema_version_and_all_thresholds(monkeypatch, tmp_path):
    code, out = _run(monkeypatch, tmp_path)
    assert code == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["schema_version"] == export_module.SCHEMA_VERSION
    threshold_fields = {f.name for f in dataclasses.fields(GapThresholds)}
    assert len(threshold_fields) == 7  # the schema doc documents seven
    assert set(manifest["thresholds"]) == threshold_fields


def test_anonymise_is_stable_for_a_salt_and_never_equals_the_input(monkeypatch, tmp_path):
    monkeypatch.setattr(export_module.config, "EXPORT_SALT", "a-fixed-test-salt")

    code1, out1 = _run(monkeypatch, tmp_path / "run1", ["--anonymise"])
    code2, out2 = _run(monkeypatch, tmp_path / "run2", ["--anonymise"])
    assert code1 == 0 and code2 == 0

    ids1 = [r[0] for r in _rows(out1 / "students.csv")[1:]]
    ids2 = [r[0] for r in _rows(out2 / "students.csv")[1:]]

    assert ids1 == ids2  # same salt -> same pseudonyms, so two runs diff cleanly
    assert ids1, "expected at least one student row"
    assert not (set(ids1) & set(_REAL_IDS))  # no real id leaked through


def test_in_plan_matches_priorities_not_prose(monkeypatch, tmp_path):
    # STU0001's plan targets the competency as a priority -> True.
    # STU0002's plan only mentions it in the summary prose -> False: in_plan is
    # about what the plan targets, not every label it happens to name.
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "learning_plan_STU0001.json").write_text(
        json.dumps({"student_id": "STU0001", "priorities": [{"competency_label": "Problem Solving"}]})
    )
    (plans / "learning_plan_STU0002.json").write_text(
        json.dumps(
            {"student_id": "STU0002", "summary": "strongest in Problem Solving", "priorities": []}
        )
    )

    code, out = _run(monkeypatch, tmp_path, ["--plans-dir", str(plans)])
    assert code == 0

    header, *rows = _rows(out / "competencies.csv")
    sid, label, in_plan = header.index("student_id"), header.index("competency_label"), header.index("in_plan")
    flags = {r[sid]: r[in_plan] for r in rows if r[label] == "Problem Solving"}
    assert flags == {"STU0001": "True", "STU0002": "False"}


def test_anonymise_without_salt_returns_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(export_module.config, "EXPORT_SALT", "")

    code, _out = _run(monkeypatch, tmp_path, ["--anonymise"])

    assert code == 2
    assert "LJA_EXPORT_SALT" in capsys.readouterr().err
