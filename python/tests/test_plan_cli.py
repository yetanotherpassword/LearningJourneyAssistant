from types import SimpleNamespace

import lja.plan as plan_module


class _FakePlan:
    def model_dump_json(self, indent=2):
        return "{}"


class _FakeClient:
    def describe(self):
        return "fake"

    def usage_summary(self):
        return "none"


def _setup_common(monkeypatch, tmp_path, state):
    cache = tmp_path / "silo_clustering.json"
    cache.write_text("{}")

    clustering = SimpleNamespace()
    dataset = SimpleNamespace()
    gaps = [SimpleNamespace(student_id="S001", competency_label="Data Structures")]
    review = SimpleNamespace(
        competency_label="Data Structures",
        state=state,
    )
    context = SimpleNamespace(
        competencies=[SimpleNamespace()],
        known_silos={"CSE1OOF:SILO1"},
        assessments=[SimpleNamespace()],
    )

    monkeypatch.setattr(
        plan_module.SiloClusteringResult,
        "model_validate_json",
        lambda _text: clustering,
    )
    monkeypatch.setattr(plan_module, "load_dataset", lambda _path: dataset)
    monkeypatch.setattr(plan_module, "compute_gaps", lambda *_args, **_kwargs: gaps)
    monkeypatch.setattr(
        plan_module,
        "load_or_create_reviews",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        plan_module,
        "current_reviews",
        lambda *_args, **_kwargs: [review],
    )
    monkeypatch.setattr(
        plan_module,
        "build_plan_context",
        lambda *_args, **_kwargs: context,
    )
    monkeypatch.setattr(plan_module, "get_llm_client", lambda: _FakeClient())
    monkeypatch.setattr(
        plan_module,
        "generate_learning_plan",
        lambda *_args, **_kwargs: _FakePlan(),
    )
    monkeypatch.setattr(plan_module, "render_markdown", lambda *_args: "# plan")

    return cache


def test_rejected_review_blocks_learning_plan(monkeypatch, tmp_path, capsys):
    cache = _setup_common(monkeypatch, tmp_path, "rejected")

    result = plan_module.main(
        [
            "dummy.xlsx",
            "S001",
            "--clustering-cache",
            str(cache),
            "--out-dir",
            str(tmp_path / "plans"),
        ]
    )

    assert result == 2
    assert "Cannot generate learning plan" in capsys.readouterr().err


def test_pending_review_warns_but_allows_learning_plan(monkeypatch, tmp_path, capsys):
    cache = _setup_common(monkeypatch, tmp_path, "pending")

    result = plan_module.main(
        [
            "dummy.xlsx",
            "S001",
            "--clustering-cache",
            str(cache),
            "--out-dir",
            str(tmp_path / "plans"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "WARNING: learning plan uses unreviewed clustering" in captured.err


def test_confirmed_review_allows_learning_plan_without_warning(
    monkeypatch, tmp_path, capsys
):
    cache = _setup_common(monkeypatch, tmp_path, "confirmed")

    result = plan_module.main(
        [
            "dummy.xlsx",
            "S001",
            "--clustering-cache",
            str(cache),
            "--out-dir",
            str(tmp_path / "plans"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "WARNING" not in captured.err
