"""lja.quiz command: review gate, catalogue lookup, no-gap exit, and fail-closed grounding (tender R8)."""

from __future__ import annotations

from types import SimpleNamespace

import lja.quiz as quiz_module
from lja.llm.grounding import GroundingError
from lja.model.quiz import EducatorReview, QuizContext, QuizDocument, SubjectInfo  # noqa: E402

_EMPTY_DOCUMENT = QuizDocument(student_id="S001", introduction="Practice.", items=[])


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
    plan_context = SimpleNamespace(competencies=[competency], assessments=[SimpleNamespace()], known_subjects=frozenset({"CSE1OOF"}))
    context = QuizContext(plan=plan_context, subjects=(SubjectInfo("CSE1OOF", "OO", 1, "synopsis"),))

    monkeypatch.setattr(quiz_module.SiloClusteringResult, "model_validate_json", lambda _t: SimpleNamespace())
    monkeypatch.setattr(quiz_module, "load_dataset_for_source", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(
        quiz_module, "compute_gaps", lambda *_a, **_k: [SimpleNamespace(student_id="S001", competency_label="Data Structures")]
    )
    monkeypatch.setattr(quiz_module, "load_or_create_reviews", lambda *_a, **_k: SimpleNamespace())
    monkeypatch.setattr(quiz_module, "current_reviews", lambda *_a, **_k: [review])
    monkeypatch.setattr(quiz_module, "build_plan_context", lambda *_a, **_k: plan_context)
    monkeypatch.setattr(quiz_module, "build_quiz_context", lambda *_a, **_k: context)
    monkeypatch.setattr(quiz_module, "has_gaps", lambda _c: gaps)
    monkeypatch.setattr(quiz_module, "gap_competencies", lambda _c: [competency] if gaps else [])
    monkeypatch.setattr(quiz_module, "get_llm_client", lambda: _FakeClient())
    monkeypatch.setattr(quiz_module, "generate_quiz", generate or (lambda *_a, **_k: SimpleNamespace()))
    monkeypatch.setattr(quiz_module.QuizDocument, "from_quiz", classmethod(lambda cls, *_a: _EMPTY_DOCUMENT))
    monkeypatch.setattr(quiz_module, "review_quiz", lambda *_a, **_k: EducatorReview(notes=[], reviewer="fake"))
    monkeypatch.setattr(quiz_module, "render_markdown", lambda *_a: "# quiz")
    return ["dummy.xlsx", "S001", "--clustering-cache", str(cache), "--out-dir", str(tmp_path / "out"), "--catalogue", str(tmp_path / "none.yaml")]


def test_confirmed_review_writes_both_files(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path)
    assert quiz_module.main(argv) == 0
    written = QuizDocument.model_validate_json((tmp_path / "out" / "quiz_S001.json").read_text())
    assert written.student_id == "S001" and written.educator_review.reviewer == "fake"
    assert (tmp_path / "out" / "quiz_S001.md").read_text() == "# quiz"
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err
    assert "1/1 subjects with a synopsis" in captured.out


def test_rejected_review_blocks(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path, state="rejected")
    assert quiz_module.main(argv) == 2
    assert "Cannot generate quiz" in capsys.readouterr().err


def test_pending_review_warns_but_writes(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path, state="pending")
    assert quiz_module.main(argv) == 0
    assert "WARNING: quiz uses unreviewed clustering" in capsys.readouterr().err


def test_no_gap_exits_cleanly_without_calling_the_llm(monkeypatch, tmp_path, capsys):
    def boom(*_a, **_k):
        raise AssertionError("the LLM must not be called for a student with no gap")

    argv = _setup(monkeypatch, tmp_path, gaps=False, generate=boom)
    assert quiz_module.main(argv) == 0
    assert "no quiz is needed" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_ungrounded_quiz_fails_and_writes_nothing(monkeypatch, tmp_path, capsys):
    def ungrounded(*_a, **_k):
        raise GroundingError("quiz for S001 failed grounding validation on all 3 attempts")

    argv = _setup(monkeypatch, tmp_path, generate=ungrounded)
    assert quiz_module.main(argv) == 1
    assert "failed grounding validation" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_load_subject_info_reads_the_catalogue_and_tolerates_a_missing_file(tmp_path):
    assert quiz_module.load_subject_info(None) == {}
    assert quiz_module.load_subject_info(tmp_path / "missing.yaml") == {}
    info = quiz_module.load_subject_info("../data-fixtures/subject_catalogue.yaml")
    assert info["CSE1OOF"].title == "Object-Oriented Programming Fundamentals"
    assert info["CSE1OOF"].year_level == 1
    assert info["CSE1OOF"].synopsis.startswith("The Object-Oriented (OO) paradigm")
    assert info["CSE2ALG"].synopsis and info["CSE3CAP"].synopsis


def test_educator_review_runs_by_default_and_reports_disagreement(monkeypatch, tmp_path, capsys):
    from lja.model.quiz import EducatorNote, QuizItem

    item = QuizItem(
        competency_label="Data Structures", gap_kind="persistent gap", subject_code="CSE1OOF", silo_key="CSE1OOF:SILO1",
        assessment_key="CSE1OOF:Test", kind="multiple_choice", stem="Q?", options=["a", "b", "c"], correct_index=0, explanation="a.",
    )
    document = QuizDocument(student_id="S001", introduction="Practice.", items=[item])
    argv = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(quiz_module.QuizDocument, "from_quiz", classmethod(lambda cls, *_a: document))
    calls = []

    def fake_review(client, doc, ctx, *, max_attempts):
        calls.append(doc)
        return EducatorReview(notes=[EducatorNote(question_index=0, chosen_index=2, marking_verdict=None, confidence="low", teaching_explanation="c, because.")])

    monkeypatch.setattr(quiz_module, "review_quiz", fake_review)
    assert quiz_module.main(argv) == 0
    assert calls == [document]
    written = QuizDocument.model_validate_json((tmp_path / "out" / "quiz_S001.json").read_text())
    assert written.disagreements == [0]
    assert "Blind check DISAGREES with the answer key on question(s) 1." in capsys.readouterr().out


def test_skip_educator_review_never_calls_it(monkeypatch, tmp_path):
    argv = _setup(monkeypatch, tmp_path) + ["--skip-educator-review"]

    def boom(*_a, **_k):
        raise AssertionError("review must not run")

    monkeypatch.setattr(quiz_module, "review_quiz", boom)
    assert quiz_module.main(argv) == 0


def test_failed_educator_review_warns_but_still_writes_the_quiz(monkeypatch, tmp_path, capsys):
    argv = _setup(monkeypatch, tmp_path)

    def ungrounded(*_a, **_k):
        raise GroundingError("Educator review for S001 failed grounding validation on all 3 attempts")

    monkeypatch.setattr(quiz_module, "review_quiz", ungrounded)
    assert quiz_module.main(argv) == 0
    assert (tmp_path / "out" / "quiz_S001.json").exists()
    assert "WARNING: educator review not written" in capsys.readouterr().err
