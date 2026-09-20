"""Tests for lja.cli helpers that don't need the full pipeline.

The load-bearing one is uncovered_silos: it is what makes
`python -m lja.cli --source moodle` work when a stale clustering cache from a
different --source is on disk. Without it, gap detection raises on the first
SILO the cache doesn't cover (the IOLG-104 acceptance command failed exactly
this way against a leftover Excel cache).
"""

from __future__ import annotations

from lja.cli import uncovered_silos
from lja.data.excel_loader import LjaDataset, Silo
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef


def _dataset(*silo_keys: str) -> LjaDataset:
    silos = {}
    for key in silo_keys:
        subject, local = key.split(":", 1)
        silos[key] = Silo(subject_code=subject, silo_local_id=local, text=key)
    return LjaDataset(silos=silos, assessments=[], results=[], student_summaries=[])


def _clustering(*silo_keys: str) -> SiloClusteringResult:
    members = [SiloRef(subject_code=k.split(":", 1)[0], silo_local_id=k.split(":", 1)[1]) for k in silo_keys]
    return SiloClusteringResult(
        clusters=[CompetencyCluster(competency_label="C", members=members, rationale="r")],
        flagged_silos=[],
    )


def test_no_missing_when_cache_covers_dataset() -> None:
    clustering = _clustering("CSE1IOI:SILO1", "CSE1IOI:SILO2")
    dataset = _dataset("CSE1IOI:SILO1", "CSE1IOI:SILO2")
    assert uncovered_silos(clustering, dataset) == set()


def test_stale_cache_from_other_source_is_reported_missing() -> None:
    # Cache built for the Excel subjects, dataset loaded from Moodle.
    clustering = _clustering("CSE1OOF:SILO1", "CSE2ALG:SILO1")
    dataset = _dataset("CSE1IOI:SILO1", "CSE1IOI:SILO2", "CSE1IOI:SILO3")
    assert uncovered_silos(clustering, dataset) == {
        "CSE1IOI:SILO1",
        "CSE1IOI:SILO2",
        "CSE1IOI:SILO3",
    }


def test_partial_cover_reports_only_the_gap() -> None:
    clustering = _clustering("CSE1IOI:SILO1")
    dataset = _dataset("CSE1IOI:SILO1", "CSE1IOI:SILO2")
    assert uncovered_silos(clustering, dataset) == {"CSE1IOI:SILO2"}
