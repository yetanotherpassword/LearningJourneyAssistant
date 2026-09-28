"""lja.strategy command: review gate, no-gap exit, and fail-closed grounding (IOLG-123)."""

from __future__ import annotations

from types import SimpleNamespace

import lja.strategy as strategy_module
from lja.llm.grounding import GroundingError


class _FakeStrategy:
    def model_dump_json(self, indent=2):
        return "{}"


class _FakeClient:
    def describe(self):
        return "fake"

    def usage_summary(self):
        return "none"


def _setup(monkeypatch, tmp_path, *, state="confirmed", gaps=True, generate=None):
    cache = tmp_path / "silo_clustering.json"
    cache.write_text("{}")
    review = SimpleNamespace(competency_label="Data Structures", state=state)
    competency = SimpleNamespace(competency_label="Data Structures", classification="persistent gap" if gaps else "proficient")
    context = SimpleNamespace(competencies=[competency], assessments=[SimpleNamespace()])

    monkeypatch.setattr(strategy_module.SiloClusteringResult, "model_validate_json", lambda _t: SimpleNamespace())
    monkeypatch.setattr(strategy_module, "load_dataset_for_source", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(
        strategy_module, "compute_gaps", lambda *_a, **_k: [SimpleNamespace(student_id="S001", competency_label="Data Structures")]
    )
    monkeypatch.setattr(strategy_module, "load_or_create_reviews", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(strategy_module, "current_reviews", lambda *_a, **_k: [review])
    monkeypatch.setattr(strategy_module, "build_plan_context", lambda *_a, **_k: context)
    monkeypatch.setattr(strategy_module, "has_gaps", lambda _c: gaps)
    monkeypatch.setattr(strategy_module, "gap_competencies", lambda _c: [competency] if gaps else [])
    monkeypatch.setattr(strategy_module, "get_llm_client", lambda: _FakeClient())
    monkeypatch.setattr(strategy_module, "generate_study_strategy", generate or (lambda *_a, **_k: _FakeStrategy()))
    monkeypatch.setattr(strategy_module, "render_markdown", lambda *_a: "# strategy")
    return ["dummy.xlsx", "S001", "--clustering-cache", str(cache), "--out-dir", str(tmp_path / "out")]


def test_confirmed_review_writes_both_files(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path)
    assert strategy_module.main(argv) == 0
    assert (tmp_path / "out" / "study_strategy_S001.json").exists()
    assert (tmp_path / "out" / "study_strategy_S001.md").read_text() == "# strategy"
    assert "WARNING" not in capsys.readouterr().err


def test_rejected_review_blocks(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path, state="rejected")
    assert strategy_module.main(argv) == 2
    assert "Cannot generate study strategy" in capsys.readouterr().err


def test_pending_review_warns_but_writes(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path, state="pending")
    assert strategy_module.main(argv) == 0
    assert "WARNING: study strategy uses unreviewed clustering" in capsys.readouterr().err


def test_no_gap_exits_cleanly_without_calling_the_llm(monkeypatch, tmp_path, capsys):
    def boom(*_a, **_k):
        raise AssertionError("the LLM must not be called for a student with no gap")

    argv = _setup(monkeypatch, tmp_path, gaps=False, generate=boom)
    assert strategy_module.main(argv) == 0
    assert "no study strategy is needed" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_ungrounded_strategy_fails_and_writes_nothing(monkeypatch, tmp_path, capsys):
    def ungrounded(*_a, **_k):
        raise GroundingError("study strategy for S001 failed grounding validation on all 3 attempts")

    argv = _setup(monkeypatch, tmp_path, generate=ungrounded)
    assert strategy_module.main(argv) == 1
    assert "failed grounding validation" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_missing_cache_names_the_command_to_run(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    assert strategy_module.main(["12345", "--source", "moodle"]) == 2
    assert "silo_clustering_moodle.json" in capsys.readouterr().err
