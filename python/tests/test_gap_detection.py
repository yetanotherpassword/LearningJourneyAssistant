"""Unit tests for lja.model.gap_detection. Builds LjaDataset objects and
SiloClusteringResult objects directly rather than going through the Excel
loader or an LLM -- this module's job is pure arithmetic and classification,
and should be testable as such.

Classification is now RELATIVE to each student's own profile, so these tests
were re-expressed rather than replaced when that landed: the same scenarios
are still exercised, but the expected verdicts now follow from within-profile
position plus two absolute guards. See gap_detection.py's module docstring
and docs/adr/0001-relative-gap-detection.md.

Every expected value is hand-calculated in the test's own docstring. That is
not ceremony here -- Anup's Sprint 4 validation harness (S4-8) builds directly
on these numbers, and a test asserting whatever the code printed the first
time only detects change, not incorrectness.

All tests pin their own GapThresholds rather than relying on config defaults.
The defaults are an unratified team decision (actions.md A-01); a test suite
that moved when someone edited a .env would be worthless.
"""

from __future__ import annotations

from lja.data.excel_loader import LjaDataset, ResultRow
from lja.model.gap_detection import (
    BASIS_CEILING,
    BASIS_FLOOR,
    BASIS_INSUFFICIENT,
    BASIS_RELATIVE,
    GapThresholds,
    build_silo_to_competency_map,
    compute_gaps,
    profile_spread,
)
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef

# The proposed defaults, pinned. Mirrors config.py so a change there shows up
# here as a deliberate edit rather than a silent shift in every expectation.
THRESHOLDS = GapThresholds(
    absolute_floor=50.0,
    absolute_ceiling=75.0,
    relative_gap_cutoff=-1.0,
    relative_strong_cutoff=1.0,
    min_competencies=4,
    min_spread=2.0,
    fallback_proficient=65.0,
)


def _dataset(results: list[ResultRow]) -> LjaDataset:
    return LjaDataset(silos={}, assessments=[], results=results, student_summaries=[])


def _clustering(*groups: tuple[str, list[tuple[str, str]]]) -> SiloClusteringResult:
    return SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label=label,
                rationale="test",
                members=[SiloRef(subject_code=s, silo_local_id=i) for s, i in members],
            )
            for label, members in groups
        ]
    )


def _profile(scores: dict[str, float], student: str = "STU1", subject: str = "SUBA"):
    """One student, one competency per score, one assessment each in one subject.

    Returns (dataset, clustering). Competency N maps to SILO N so each score
    lands in its own competency and the student's profile is exactly `scores`.
    """
    labels = list(scores)
    clustering = _clustering(*[(label, [(subject, f"SILO{i + 1}")]) for i, label in enumerate(labels)])
    results = [
        ResultRow(student, subject, f"A{i + 1}", score=scores[label], feedback_comment="",
                  weight=1.0, weighted_score=scores[label], silo_ids=(f"SILO{i + 1}",))
        for i, label in enumerate(labels)
    ]
    return _dataset(results), clustering


def _by_label(gaps) -> dict:
    return {g.competency_label: g for g in gaps}


# --- unchanged behaviour: the mapping and the weighted-attainment arithmetic ---


def test_build_silo_to_competency_map_flattens_clusters() -> None:
    clustering = _clustering(("Verification", [("SUBA", "SILO1"), ("SUBB", "SILO2")]))
    mapping = build_silo_to_competency_map(clustering)
    assert mapping == {"SUBA:SILO1": "Verification", "SUBB:SILO2": "Verification"}


def test_compute_gaps_weights_multiple_assessments() -> None:
    """Weighted attainment is deliberately untouched by relative classification.

    (80*0.4 + 40*0.6) / (0.4+0.6) = (32 + 24) / 1.0 = 56.0
    """
    clustering = _clustering(("Skill", [("SUBA", "SILO1")]))
    results = [
        ResultRow("STU1", "SUBA", "Test", score=80.0, feedback_comment="", weight=0.4, weighted_score=32.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "SUBA", "Exam", score=40.0, feedback_comment="", weight=0.6, weighted_score=24.0, silo_ids=("SILO1",)),
    ]
    gaps = compute_gaps(_dataset(results), clustering, thresholds=THRESHOLDS)
    assert gaps[0].attainment_pct == 56.0
    assert gaps[0].n_observations == 2


def test_one_assessment_evidences_multiple_silos_independently() -> None:
    """A single assessment covering two SILOs contributes its full score to
    BOTH competencies, not a split fraction -- see the design-decision note in
    gap_detection.py's module docstring. Unchanged by relative classification.
    """
    clustering = _clustering(("Competency A", [("SUBA", "SILO1")]), ("Competency B", [("SUBA", "SILO2")]))
    results = [
        ResultRow("STU1", "SUBA", "Test", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO1", "SILO2")),
    ]
    gaps = _by_label(compute_gaps(_dataset(results), clustering, thresholds=THRESHOLDS))
    assert gaps["Competency A"].attainment_pct == 70.0
    assert gaps["Competency B"].attainment_pct == 70.0


def test_profile_spread_is_median_and_unscaled_mad() -> None:
    """Values [55, 60, 64, 70, 72].

    sorted -> 55, 60, 64, 70, 72; median is the middle value = 64
    absolute deviations from 64: 9, 4, 0, 6, 8
    sorted -> 0, 4, 6, 8, 9; median of those = 6

    MAD is NOT scaled by 1.4826 -- cut-offs are expressed in raw MAD units,
    and that constant would imply a normality assumption about a 5-point
    distribution that nothing here justifies.
    """
    median, mad = profile_spread([70.0, 64.0, 72.0, 60.0, 55.0])
    assert median == 64.0
    assert mad == 6.0


# --- the relative path ---


def test_relative_gap_is_flagged_although_it_is_a_pass() -> None:
    """The whole point of requirement 4. Profile [70, 64, 72, 60, 55].

    median = 64, MAD = 6 (see test_profile_spread_is_median_and_unscaled_mad)
    Every value sits between the floor (50) and ceiling (75), so no absolute
    guard fires and all five are decided relatively:

        70 -> (70-64)/6 =  1.00  >= +1.0  -> proficient
        64 -> (64-64)/6 =  0.00           -> developing
        72 -> (72-64)/6 =  1.33  >= +1.0  -> proficient
        60 -> (60-64)/6 = -0.67  > -1.0   -> developing
        55 -> (55-64)/6 = -1.50 <= -1.0   -> GAP

    55 is a pass mark. Absolute logic called it "developing" and said nothing.
    Relative logic flags it, because for THIS student it is the outlier.
    """
    dataset, clustering = _profile({"C1": 70.0, "C2": 64.0, "C3": 72.0, "C4": 60.0, "C5": 55.0})
    gaps = _by_label(compute_gaps(dataset, clustering, thresholds=THRESHOLDS))

    assert gaps["C5"].classification == "isolated gap"
    assert gaps["C5"].classification_basis == BASIS_RELATIVE
    assert gaps["C5"].relative_position == -1.5

    assert gaps["C1"].classification == "proficient"
    assert gaps["C3"].classification == "proficient"
    assert gaps["C2"].classification == "developing"
    assert gaps["C4"].classification == "developing"
    assert gaps["C4"].relative_position == -0.67   # -0.666... rounded to 2dp


# --- degenerate case 1: the uniformly weak student ---


def test_uniformly_weak_student_still_gets_gaps() -> None:
    """Every competency at 35%. median = 35, MAD = 0 -- no within-profile
    variance whatsoever, so relative logic finds no outliers and would report
    NO GAPS to a student failing everything. Unacceptable.

    The floor (50) fires first and every competency is a gap on that basis.
    """
    dataset, clustering = _profile({f"C{i}": 35.0 for i in range(1, 6)})
    gaps = compute_gaps(dataset, clustering, thresholds=THRESHOLDS)

    assert len(gaps) == 5
    assert all(g.classification == "isolated gap" for g in gaps)
    assert all(g.classification_basis == BASIS_FLOOR for g in gaps)
    assert all(g.relative_position is None for g in gaps)


# --- degenerate case 2: the uniformly strong student ---


def test_uniformly_strong_student_has_nothing_flagged() -> None:
    """Four competencies at 90 and one at 85.

    median = 90, deviations 0,0,0,0,5 -> MAD = 0. Even with spread, 85 is the
    clear low outlier and pure relative logic would flag it -- which is worse
    than useless, because it teaches a student on 85-90% to distrust the tool.

    The ceiling (75) fires first: everything at or above it is proficient
    regardless of relative position.
    """
    dataset, clustering = _profile({"C1": 90.0, "C2": 90.0, "C3": 90.0, "C4": 90.0, "C5": 85.0})
    gaps = _by_label(compute_gaps(dataset, clustering, thresholds=THRESHOLDS))

    assert all(g.classification == "proficient" for g in gaps.values())
    assert all(g.classification_basis == BASIS_CEILING for g in gaps.values())
    assert gaps["C5"].classification == "proficient"   # the one that must not be flagged


def test_single_catastrophic_result_among_strong_ones_is_still_a_gap() -> None:
    """Profile [92, 90, 88, 89, 30] -- the case the ceiling must NOT swallow.

    The four strong values are all >= 75 and become proficient on the ceiling.
    The 30 is below the floor (50), so it is a gap on that basis, and the
    ceiling never gets a chance to see it. A guard that suppressed this would
    be a worse bug than the one it was added to prevent.
    """
    dataset, clustering = _profile({"C1": 92.0, "C2": 90.0, "C3": 88.0, "C4": 89.0, "C5": 30.0})
    gaps = _by_label(compute_gaps(dataset, clustering, thresholds=THRESHOLDS))

    assert gaps["C5"].classification == "isolated gap"
    assert gaps["C5"].classification_basis == BASIS_FLOOR
    assert [gaps[c].classification for c in ("C1", "C2", "C3", "C4")] == ["proficient"] * 4


# --- the fallbacks, and the requirement that they announce themselves ---


def test_near_zero_spread_falls_back_and_records_that_it_did() -> None:
    """Profile [60, 60, 60, 61, 60], all between floor and ceiling.

    median = 60; deviations 0,0,0,1,0 -> MAD = 0, which is below min_spread
    (2.0). Dividing by that would turn a 1-point rounding difference into a
    large relative position, so classification falls back to absolute:
    60 and 61 are both < 65, so both are "developing".

    The basis must say "insufficient data" -- a relative verdict that was not
    actually computed relatively is exactly the untraceable claim requirement
    5 forbids.
    """
    dataset, clustering = _profile({"C1": 60.0, "C2": 60.0, "C3": 60.0, "C4": 61.0, "C5": 60.0})
    gaps = compute_gaps(dataset, clustering, thresholds=THRESHOLDS)

    assert all(g.classification == "developing" for g in gaps)
    assert all(g.classification_basis == BASIS_INSUFFICIENT for g in gaps)
    assert all(g.relative_position is None for g in gaps)


def test_too_few_competencies_falls_back_and_records_that_it_did() -> None:
    """Three competencies [55, 60, 70] -- below min_competencies (4).

    Whatever the statistic says at n=3, it is noise, so no relative verdict is
    offered. Absolute fallback against fallback_proficient (65):
        55 -> < 65 -> developing
        60 -> < 65 -> developing
        70 -> >= 65 -> proficient   (and < ceiling 75, so not a ceiling call)
    """
    dataset, clustering = _profile({"C1": 55.0, "C2": 60.0, "C3": 70.0})
    gaps = _by_label(compute_gaps(dataset, clustering, thresholds=THRESHOLDS))

    assert gaps["C1"].classification == "developing"
    assert gaps["C2"].classification == "developing"
    assert gaps["C3"].classification == "proficient"
    assert all(g.classification_basis == BASIS_INSUFFICIENT for g in gaps.values())


def test_a_lone_high_competency_is_proficient_on_the_ceiling() -> None:
    """One competency at 90. n=1 is far below min_competencies, but the
    ceiling is checked BEFORE the spread test, so this is decided absolutely
    and explicitly rather than falling through to "insufficient data".
    """
    dataset, clustering = _profile({"Skill": 90.0})
    gap = compute_gaps(dataset, clustering, thresholds=THRESHOLDS)[0]

    assert gap.classification == "proficient"
    assert gap.classification_basis == BASIS_CEILING


# --- persistent vs isolated, orthogonal to how the gap was found ---


def test_persistent_isolated_split_survives_relative_detection() -> None:
    """The distinction must survive the change: it describes whether a gap
    RECURS across subjects, which is a different question from whether it is a
    gap at all. Sprint 5's study-strategy generation depends on it.

    Both students have profile [55, 70, 64, 72, 60] -> median 64, MAD 6, and
    in both the 55 is at (55-64)/6 = -1.5, a relative gap.

    STU1 evidences that competency in SUBA only          -> isolated gap
    STU2 evidences it in SUBA and SUBB, scoring 55 in both
         (55*1 + 55*1)/2 = 55, same attainment          -> persistent gap
    """
    clustering = _clustering(
        ("Shared", [("SUBA", "SILO1"), ("SUBB", "SILO1")]),
        ("C2", [("SUBA", "SILO2")]),
        ("C3", [("SUBA", "SILO3")]),
        ("C4", [("SUBA", "SILO4")]),
        ("C5", [("SUBA", "SILO5")]),
    )

    def rows(student: str, shared_in_two_subjects: bool) -> list[ResultRow]:
        out = [
            ResultRow(student, "SUBA", "A1", score=55.0, feedback_comment="", weight=1.0, weighted_score=55.0, silo_ids=("SILO1",)),
            ResultRow(student, "SUBA", "A2", score=70.0, feedback_comment="", weight=1.0, weighted_score=70.0, silo_ids=("SILO2",)),
            ResultRow(student, "SUBA", "A3", score=64.0, feedback_comment="", weight=1.0, weighted_score=64.0, silo_ids=("SILO3",)),
            ResultRow(student, "SUBA", "A4", score=72.0, feedback_comment="", weight=1.0, weighted_score=72.0, silo_ids=("SILO4",)),
            ResultRow(student, "SUBA", "A5", score=60.0, feedback_comment="", weight=1.0, weighted_score=60.0, silo_ids=("SILO5",)),
        ]
        if shared_in_two_subjects:
            out.append(
                ResultRow(student, "SUBB", "B1", score=55.0, feedback_comment="", weight=1.0, weighted_score=55.0, silo_ids=("SILO1",))
            )
        return out

    isolated = _by_label(compute_gaps(_dataset(rows("STU1", False)), clustering, thresholds=THRESHOLDS))
    persistent = _by_label(compute_gaps(_dataset(rows("STU2", True)), clustering, thresholds=THRESHOLDS))

    assert isolated["Shared"].classification == "isolated gap"
    assert isolated["Shared"].subjects_evidencing == 1
    assert isolated["Shared"].classification_basis == BASIS_RELATIVE

    assert persistent["Shared"].classification == "persistent gap"
    assert persistent["Shared"].subjects_evidencing == 2
    assert persistent["Shared"].attainment_pct == 55.0
    assert persistent["Shared"].classification_basis == BASIS_RELATIVE


def test_persistent_isolated_split_also_applies_to_floor_gaps() -> None:
    """A gap found by the absolute floor still carries the distinction --
    subjects_evidencing is about evidence, not about detection method.

    Profile is all 35s (uniformly weak, so every competency trips the floor),
    with the shared competency evidenced in two subjects: (35+35)/2 = 35.
    """
    clustering = _clustering(
        ("Shared", [("SUBA", "SILO1"), ("SUBB", "SILO1")]),
        ("Other", [("SUBA", "SILO2")]),
    )
    results = [
        ResultRow("STU1", "SUBA", "A1", score=35.0, feedback_comment="", weight=1.0, weighted_score=35.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "SUBB", "B1", score=35.0, feedback_comment="", weight=1.0, weighted_score=35.0, silo_ids=("SILO1",)),
        ResultRow("STU1", "SUBA", "A2", score=35.0, feedback_comment="", weight=1.0, weighted_score=35.0, silo_ids=("SILO2",)),
    ]
    gaps = _by_label(compute_gaps(_dataset(results), clustering, thresholds=THRESHOLDS))

    assert gaps["Shared"].classification == "persistent gap"
    assert gaps["Other"].classification == "isolated gap"
    assert gaps["Shared"].classification_basis == BASIS_FLOOR


# --- the thresholds are configuration, and actually take effect ---


def test_thresholds_are_configuration_not_constants() -> None:
    """Same profile, two threshold sets, different verdicts.

    Profile [70, 64, 72, 60, 55]: median 64, MAD 6, and 55 sits at -1.5.
    With the proposed cut-off of -1.0 that is a gap. Loosen the cut-off to
    -2.0 and it is not -- it becomes "developing", because -1.5 is neither
    <= -2.0 nor >= +1.0.

    This is what makes Sprint 5's sensitivity testing possible without a code
    change, and it is why there are no numeric literals in gap_detection.py.
    """
    dataset, clustering = _profile({"C1": 70.0, "C2": 64.0, "C3": 72.0, "C4": 60.0, "C5": 55.0})

    strict = _by_label(compute_gaps(dataset, clustering, thresholds=THRESHOLDS))
    loose = _by_label(
        compute_gaps(dataset, clustering, thresholds=GapThresholds(
            absolute_floor=50.0, absolute_ceiling=75.0,
            relative_gap_cutoff=-2.0, relative_strong_cutoff=1.0,
            min_competencies=4, min_spread=2.0, fallback_proficient=65.0,
        ))
    )

    assert strict["C5"].classification == "isolated gap"
    assert loose["C5"].classification == "developing"
    assert loose["C5"].relative_position == -1.5   # the position is identical; only the verdict moves
