"""Cross-subject SILO clustering -- the semantic-matching step Scott asked
for on the call (transcript 2026-08-11, ~03:00-03:25 and ~08:00-09:10):
"I don't really want to go down the route of just basic keyword matching...
that second [semantic] approach is kind of what we're looking at, such that
Silo 1 in this particular subject might map in its intent to Silo 3 in ALG
and Silo 4 in Capstone."

This is the LLM-driven equivalent of the Moodle-path's
lja_criterion_silo_map: it groups the 13 subject-local SILOs into
cross-subject competencies. Nothing here is staff-confirmed -- treat the
output the same way the SQL bundle treats an unconfirmed mapping row: fit
for review, not for driving a live intervention yet.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..data.excel_loader import LjaDataset
from ..llm.base import LLMClient
from ..llm.grounding import ReferenceCheck, validate_grounding

# extra="forbid" is not just strictness -- Anthropic's structured-output
# endpoint (output_config.format) rejects any object schema that doesn't
# explicitly set additionalProperties: false, and that's exactly what this
# pydantic setting adds to model_json_schema(). Required on every model
# below, not just the top-level one -- each nested model gets its own
# object schema under $defs.


class SiloRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_code: str
    silo_local_id: str


class CompetencyCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competency_label: str
    rationale: str
    members: list[SiloRef]


class FlaggedSilo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_code: str
    silo_local_id: str
    reason: str


class SiloClusteringResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clusters: list[CompetencyCluster]
    flagged_silos: list[FlaggedSilo] = []


_SYSTEM_PROMPT = """You are assisting a university curriculum analyst who is comparing \
Subject Intended Learning Outcomes (SILOs) across several subjects in a degree.

Each SILO is identified by its subject code and a subject-local id (e.g. "SILO1"). \
The same id is reused independently in every subject and carries no meaning across \
subjects -- only the SILO's text describes what it actually is.

The whole point of this exercise is finding competencies that SPAN subjects -- e.g. a \
first-year subject's "abstraction and encapsulation" outcome and a second-year subject's \
"choosing and applying the right data structure" outcome may be evidence of the same \
underlying competency even though they are in different subjects, use different words, and \
sit at different points in the degree. Grouping by subject is the one thing this analysis \
must NOT do -- that information is already in each SILO's subject_code field and adds \
nothing new. A cluster whose members are all from a single subject should be treated as a \
sign you have NOT yet found the real cross-subject grouping, not as an acceptable answer.

Work SILO by SILO. For each one, actively compare it against every SILO from every OTHER \
subject and ask: does this describe the same underlying skill or knowledge area, even if the \
wording, examples, or language used are completely different? Only fall back to a \
single-subject or single-member group for a SILO once you have genuinely checked it against \
every other subject's SILOs and found no real match -- and say so explicitly in that group's \
rationale ("no equivalent outcome found in the other subjects").

Worked example of the reasoning expected (not from this dataset -- illustrative only): a \
subject's outcome about "testing and debugging code to verify correctness" and a different \
subject's outcome about "validating that a solution meets its requirements" describe the same \
underlying competency (verification) despite sharing almost no vocabulary. By contrast, a \
subject's outcome about "written technical reporting" and another's about "oral presentation \
to an audience" are both communication-related but are NOT the same competency -- writing and \
speaking are different skills that should stay in separate groups unless the SILO text itself \
ties them together.

Your task:

1. Group SILOs that describe substantially the same underlying competency, prioritising \
cross-subject groups per the reasoning above. A competency group should represent one \
coherent skill or knowledge area a student either has or is lacking -- not an entire subject, \
and not so broad that it swallows unrelated skills.
2. Every SILO provided MUST appear in exactly one group's members list. Do not omit any \
SILO, and do not place the same SILO in more than one group.
3. Give each group a short, human-readable competency_label (a few words, Title Case) and \
a one-sentence rationale explaining what actually ties its members together, referring to \
the SILO text itself -- and explicitly naming which subjects it spans.
4. Separately, in flagged_silos, list any SILO whose wording is vague, not assessable, or \
does not clearly describe a specific skill (e.g. "understands the topic" without saying \
what about it). This is feedback for the subject coordinator who wrote it, not a judgement \
on any student. IMPORTANT: flagged_silos is an ADDITIONAL, separate list -- flagging a SILO \
here never removes the requirement in step 2 that it also appear in exactly one cluster's \
members. A vaguely-worded SILO still needs a best-effort cluster assignment (even if that \
means its own single-member group); do not omit it from every cluster just because you \
flagged it.

Ground every judgement strictly in the SILO text you were given below. Do not invent \
SILOs, subjects, or wording that was not provided.
"""


def cluster_silos(
    client: LLMClient,
    dataset: LjaDataset,
    *,
    max_attempts: int = 3,
    extra_instructions: str | None = None,
) -> SiloClusteringResult:
    """Cluster, then validate, then retry on a validation failure --
    confirmed necessary live, not defensive-for-its-own-sake: qwen3-vl:30b
    produced a perfect, full-coverage clustering on one run and dropped 3
    SILOs on the next, same prompt, same model. Single-shot LLM sampling
    has visible run-to-run variance even on a model that's good at this
    task, so treating one bad sample as a hard failure wastes a
    known-good model. Each retry tells the model specifically what it got
    wrong last time, rather than blindly resending the same prompt.

    extra_instructions, if given, is appended to the system prompt verbatim
    -- a way to experiment with prompt changes (e.g. via --extra-instructions
    on the CLI) without editing _SYSTEM_PROMPT itself.
    """
    system_prompt = _SYSTEM_PROMPT
    if extra_instructions:
        system_prompt = f"{system_prompt}\n\n{extra_instructions}"

    ordered_silos = sorted(dataset.silos.values(), key=lambda s: (s.subject_code, s.silo_local_id))
    silo_lines = "\n".join(f"- {s.subject_code} {s.silo_local_id}: {s.text}" for s in ordered_silos)
    base_prompt = f"Here are all {len(ordered_silos)} SILOs across the subject suite:\n\n{silo_lines}"

    last_error: ValueError | None = None
    for attempt in range(1, max_attempts + 1):
        user_prompt = base_prompt
        if last_error is not None:
            user_prompt += (
                f"\n\nYour previous attempt failed a completeness check: {last_error} "
                f"Every one of the {len(ordered_silos)} SILOs listed above must appear in "
                f"exactly one cluster's members -- check the ones named in that error "
                f"specifically before answering again."
            )
        result = client.complete_structured(system=system_prompt, user=user_prompt, schema=SiloClusteringResult)
        try:
            _validate_coverage(result, dataset)
            return result
        except ValueError as exc:
            last_error = exc
            continue

    raise ValueError(
        f"SILO clustering failed coverage validation on all {max_attempts} attempts. "
        f"Last error: {last_error}"
    ) from last_error


def _validate_coverage(result: SiloClusteringResult, dataset: LjaDataset) -> None:
    """Catch the model dropping or duplicating a SILO -- fail loudly rather
    than silently under-counting a student's evidence later in gap
    detection. Retrying on this failure is cluster_silos()'s job, above;
    this function only ever checks one candidate result.

    Since S4-3 this is a thin adapter over lja.llm.grounding, the shared
    validator every generated artefact goes through. Clustering is the one
    artefact that needs all three checks: nothing invented (unknown),
    nothing dropped (require_complete) and nothing double-counted
    (require_unique).
    """
    referenced = [f"{m.subject_code}:{m.silo_local_id}" for cluster in result.clusters for m in cluster.members]
    validate_grounding(
        "SILO clustering",
        [
            ReferenceCheck(
                kind="SILO",
                referenced=referenced,
                known=dataset.silos.keys(),
                require_complete=True,
                require_unique=True,
            )
        ],
    )
