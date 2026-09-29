"""Compare IOLG-110's independently calculated CSV with the public detector."""

import csv
from collections import defaultdict
from pathlib import Path

import pytest

from lja.data.excel_loader import LjaDataset, ResultRow
from lja.model.gap_detection import GapThresholds, compute_gaps, profile_spread
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef

THRESHOLDS = GapThresholds(
    absolute_floor=50.0,
    absolute_ceiling=75.0,
    relative_gap_cutoff=-1.0,
    relative_strong_cutoff=1.0,
    min_competencies=4,
    min_spread=1.0,
    fallback_proficient=65.0,
)

# Calculated independently in docs/validation-worksheet.md, in CSV A–E order.
PROFILE_EXPECTATIONS = {
    "uniform_weak": (43.5, 2.5, [None, None, None, None]),
    "uniform_strong": (82.5, 3.5, [None, None, None, None]),
    "flat_profile": (62.65, 0.25, [None, None, None, None]),
    "relative_clear": (69.0, 2.0, [0.5, -0.5, 1.5, -7.0]),
    "three_competencies": (70.0, 2.0, [None, None, None]),
    "boundary_exact": (64.0, 2.0, [-2.0, -1.0, 0.0, 1.0, 2.0]),
    "persistent": (69.0, 2.0, [0.5, -0.5, 1.5, -7.0]),
}


def _cases():
    cases = defaultdict(list)
    with (Path(__file__).parent / "validation" / "cases.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            cases[row["case_id"]].append(row)
    assert set(cases) == set(PROFILE_EXPECTATIONS)
    return cases


@pytest.mark.parametrize("case_id,rows", _cases().items(), ids=list(PROFILE_EXPECTATIONS))
def test_hand_calculated_profile(case_id, rows):
    median, mad, positions = PROFILE_EXPECTATIONS[case_id]
    assert len(rows) == len(positions)
    assert [row["competency"] for row in rows] == list("ABCDE"[:len(rows)])
    assert profile_spread([float(row["attainment"]) for row in rows]) == pytest.approx((median, mad))

    clusters = []
    results = []
    for row in rows:
        members = []
        for subject_index in range(int(row["subjects_evidencing"])):
            subject = f"SUB{subject_index + 1}"
            silo = f"SILO{row['competency']}"
            members.append(SiloRef(subject_code=subject, silo_local_id=silo))
            score = float(row["attainment"])
            results.append(ResultRow(
                student_id=case_id,
                subject_code=subject,
                assessment_name=f"Assessment {row['competency']}",
                score=score,
                feedback_comment="",
                weight=1.0,
                weighted_score=score,
                silo_ids=(silo,),
            ))
        clusters.append(CompetencyCluster(
            competency_label=row["competency"], rationale="IOLG-110 fixed profile", members=members,
        ))

    dataset = LjaDataset(silos={}, assessments=[], results=results, student_summaries=[])
    gaps = compute_gaps(dataset, SiloClusteringResult(clusters=clusters), thresholds=THRESHOLDS)
    by_label = {gap.competency_label: gap for gap in gaps}
    assert len(gaps) == len(rows)
    for row, position in zip(rows, positions, strict=True):
        actual = by_label[row["competency"]]
        assert actual.student_id == case_id
        assert actual.attainment_pct == pytest.approx(float(row["attainment"]))
        assert actual.subjects_evidencing == int(row["subjects_evidencing"])
        assert actual.classification == row["expected_classification"], row
        assert actual.classification_basis == row["expected_basis"], row
        assert actual.relative_position == position, row
