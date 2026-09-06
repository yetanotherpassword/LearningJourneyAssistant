"""Unit tests for lja.model.silo_clustering: the coverage validator (the
guard that stopped a real bad LLM response -- missing 3 SILOs -- from
silently reaching gap_detection.py), and the retry loop around it (added
after a SECOND live run, same model qwen3-vl:30b, same prompt, dropped a
different 3 SILOs -- confirming this is sampling variance worth retrying,
not a one-off fluke). Uses a scripted fake LLMClient rather than a live
model, so this runs offline and deterministically.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lja.data.excel_loader import LjaDataset, Silo
from lja.model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef, cluster_silos


class _FakeLLMClient:
    """Returns each entry in `results` in order, one per call; repeats the
    last entry if called more times than there are results. Tracks call
    count so retry tests can assert exactly how many attempts were made.
    """

    def __init__(self, *results: SiloClusteringResult) -> None:
        self._results = list(results)
        self.call_count = 0
        self.systems_seen: list[str] = []

    def complete_structured(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        index = min(self.call_count, len(self._results) - 1)
        self.call_count += 1
        self.systems_seen.append(system)
        return self._results[index]


def _two_silo_dataset() -> LjaDataset:
    silos = {
        "SUBA:SILO1": Silo("SUBA", "SILO1", "alpha"),
        "SUBB:SILO1": Silo("SUBB", "SILO1", "beta"),
    }
    return LjaDataset(silos=silos, assessments=[], results=[], student_summaries=[])


def test_cluster_silos_accepts_complete_coverage() -> None:
    canned = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Shared Skill",
                rationale="test",
                members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1"), SiloRef(subject_code="SUBB", silo_local_id="SILO1")],
            )
        ]
    )
    result = cluster_silos(_FakeLLMClient(canned), _two_silo_dataset())
    assert result is canned


def test_cluster_silos_rejects_missing_silo() -> None:
    canned = SiloClusteringResult(
        clusters=[CompetencyCluster(competency_label="Only A", rationale="test", members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1")])]
    )
    with pytest.raises(ValueError, match="absent from the output"):
        cluster_silos(_FakeLLMClient(canned), _two_silo_dataset())


def test_cluster_silos_rejects_duplicated_silo() -> None:
    ref = SiloRef(subject_code="SUBA", silo_local_id="SILO1")
    canned = SiloClusteringResult(
        clusters=[
            CompetencyCluster(competency_label="Group 1", rationale="test", members=[ref, SiloRef(subject_code="SUBB", silo_local_id="SILO1")]),
            CompetencyCluster(competency_label="Group 2", rationale="test", members=[ref]),
        ]
    )
    with pytest.raises(ValueError, match="referenced more than once"):
        cluster_silos(_FakeLLMClient(canned), _two_silo_dataset())


def test_cluster_silos_rejects_unknown_silo() -> None:
    canned = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Bogus",
                rationale="test",
                members=[
                    SiloRef(subject_code="SUBA", silo_local_id="SILO1"),
                    SiloRef(subject_code="SUBB", silo_local_id="SILO1"),
                    SiloRef(subject_code="SUBC", silo_local_id="SILO99"),
                ],
            )
        ]
    )
    with pytest.raises(ValueError, match="not present in the input"):
        cluster_silos(_FakeLLMClient(canned), _two_silo_dataset())


def test_cluster_silos_retries_and_recovers_from_a_bad_first_attempt() -> None:
    """The exact real scenario: qwen3-vl:30b dropped SILOs on one run and
    produced a complete, correct clustering on the next -- same model, same
    prompt. One bad sample must not be treated as a hard failure.
    """
    bad_first_attempt = SiloClusteringResult(
        clusters=[CompetencyCluster(competency_label="Only A", rationale="test", members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1")])]
    )
    good_second_attempt = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Shared Skill",
                rationale="test",
                members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1"), SiloRef(subject_code="SUBB", silo_local_id="SILO1")],
            )
        ]
    )
    fake = _FakeLLMClient(bad_first_attempt, good_second_attempt)
    result = cluster_silos(fake, _two_silo_dataset())
    assert result is good_second_attempt
    assert fake.call_count == 2


def test_cluster_silos_appends_extra_instructions_to_system_prompt() -> None:
    canned = SiloClusteringResult(
        clusters=[
            CompetencyCluster(
                competency_label="Shared Skill",
                rationale="test",
                members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1"), SiloRef(subject_code="SUBB", silo_local_id="SILO1")],
            )
        ]
    )
    fake = _FakeLLMClient(canned)
    cluster_silos(fake, _two_silo_dataset(), extra_instructions="Prefer shorter competency labels.")
    assert fake.systems_seen[0].endswith("Prefer shorter competency labels.")


def test_cluster_silos_gives_up_after_max_attempts() -> None:
    always_bad = SiloClusteringResult(
        clusters=[CompetencyCluster(competency_label="Only A", rationale="test", members=[SiloRef(subject_code="SUBA", silo_local_id="SILO1")])]
    )
    fake = _FakeLLMClient(always_bad)
    with pytest.raises(ValueError, match="failed coverage validation on all 2 attempts"):
        cluster_silos(fake, _two_silo_dataset(), max_attempts=2)
    assert fake.call_count == 2
