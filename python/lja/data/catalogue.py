"""The subject catalogue: one human-editable YAML file that defines subjects,
their SILOs, their assessments, and -- this is the part the supplied
workbook cannot carry -- which cross-subject COMPETENCY each SILO is really
evidence of.

Why it exists (IOLG-113). The supplied workbook fixes the subject list at
three; synth_generator.py can add students to it but never subjects or
SILOs, because it copies the Assessment Map verbatim. Scott was explicit
that the product's value arrives "across all of our, what, 30-plus
subjects", so the pipeline has to be exercised at that scale before it
meets production Moodle. The catalogue is the single source those subjects
come from, for BOTH the Excel path (catalogue_generator.py writes a
workbook in the supplied shape) and the Moodle path (moodle_emitters.py
writes competency-framework CSVs, the criterion-to-SILO map and a rubric
marking fixture from the same file). One source, two paths, no drift.

The competency tag on each SILO is the catalogue's ground truth. It is what
lets a generated cohort carry a per-student ability per competency (so
relative gaps exist to be found -- see docs/adr/0001 and the flat-profile
caution in config.py) and it is what the LLM's clustering can be scored
against, instead of eyeballed.
"""

from __future__ import annotations

import fnmatch
import math
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model.silo_clustering import CompetencyCluster, SiloClusteringResult, SiloRef
from .excel_loader import Assessment, LjaDataset, Silo

# The level ladder every emitted Moodle rubric uses unless the catalogue
# overrides it. Same four bands as the IOLG-56 fixture, so Query 2 output
# from a catalogue-driven load looks like Query 2 output from that one.
DEFAULT_RUBRIC_LEVELS: dict[int, str] = {
    0: "Not demonstrated",
    1: "Developing",
    2: "Proficient",
    3: "Exemplary",
}


class Competency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str = ""
    # Loadings onto the cohort's latent aptitude traits (see
    # catalogue_generator's ability model). Competencies with similar loadings
    # co-vary across students -- a student strong in one quantitative
    # competency tends to be strong in the others. Written by
    # competency_tagger.py from the SILO embeddings; None means "independent",
    # which is what the hand-written catalogue gets.
    traits: list[float] | None = None


class CatalogueSilo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # subject-local, e.g. "SILO1" -- same convention as the workbook
    text: str
    competency: str  # a Competency.id

    @model_validator(mode="after")
    def _text_is_loader_safe(self) -> CatalogueSilo:
        # excel_loader._parse_silo_list splits the "SILO Theme Summary" cell
        # on "; SILOn:", and a semicolon inside a SILO's own text breaks that.
        if ";" in self.text:
            raise ValueError(f"SILO {self.id!r} text must not contain ';' (the workbook cell delimiter)")
        if not self.id.startswith("SILO"):
            raise ValueError(f"SILO id {self.id!r} must look like 'SILOn' for the workbook loader")
        return self


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    silo: str  # subject-local SILO id


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterion] = Field(min_length=1)


class CatalogueAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    weight: float = Field(gt=0, le=1)
    contribution: str = "Individual"
    early_assessment: bool = False
    hurdle: bool = False
    silos: list[str] = Field(min_length=1)
    # Which assignment in the seeded Moodle course this maps onto. tool_generator
    # names them "Assignment 1".."Assignment N", so the default is positional
    # (filled in by Subject's validator); override when a restored .mbz uses
    # real names.
    moodle_assignment: str | None = None
    # Explicit rubric for the Moodle emitter. When omitted, one criterion per
    # SILO is derived from the SILO text, which keeps the criterion-to-SILO
    # map trivially correct.
    rubric: Rubric | None = None

    @model_validator(mode="after")
    def _name_is_loader_safe(self) -> CatalogueAssessment:
        # The workbook's "Assessment Type" cell is "CODE - name", split on the
        # FIRST " - ". A name may contain " - " itself; a code may not, and
        # that is checked on Subject.
        if not self.name.strip():
            raise ValueError("assessment name must not be blank")
        return self


class Subject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    year_level: int = Field(ge=1, le=6)
    # "supplied" for the three real subjects, "handbook" for La Trobe handbook
    # subjects (real SILOs, synthetic assessments), "synthetic" otherwise.
    source: str = "synthetic"
    discipline: str | None = None  # subject-code prefix, e.g. "CHE"
    credit_points: int | None = None
    assessments_synthetic: bool = False
    silos: list[CatalogueSilo] = Field(min_length=1)
    assessments: list[CatalogueAssessment] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Subject:
        if " - " in self.code or not self.code.strip():
            raise ValueError(f"subject code {self.code!r} must be non-blank and must not contain ' - '")
        silo_ids = [s.id for s in self.silos]
        if len(set(silo_ids)) != len(silo_ids):
            raise ValueError(f"{self.code}: duplicate SILO ids {silo_ids}")
        known = set(silo_ids)
        names = [a.name for a in self.assessments]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.code}: duplicate assessment names {names}")
        for i, assessment in enumerate(self.assessments):
            unknown = [s for s in assessment.silos if s not in known]
            if unknown:
                raise ValueError(f"{self.code} / {assessment.name}: unknown SILO ids {unknown}")
            if assessment.rubric is not None:
                bad = [c.silo for c in assessment.rubric.criteria if c.silo not in known]
                if bad:
                    raise ValueError(f"{self.code} / {assessment.name}: rubric references unknown SILOs {bad}")
            if assessment.moodle_assignment is None:
                assessment.moodle_assignment = f"Assignment {i + 1}"
        total = sum(a.weight for a in self.assessments)
        if not math.isclose(total, 1.0, abs_tol=0.005):
            raise ValueError(f"{self.code}: assessment weights sum to {total:.3f}, expected 1.0")
        return self


class ProgramRule(BaseModel):
    """'Take `take` subjects matching `pattern` in year `year`.' Patterns are
    shell globs over subject codes (CHE1*, CSE2ALG). `take: all` is spelled
    take=-1. Rules with the same year draw from disjoint pools in order, so a
    core rule listed first cannot be double-counted by a broader elective
    rule after it."""

    model_config = ConfigDict(extra="forbid")

    pattern: str | list[str]
    year: int = Field(ge=1, le=6)
    take: int = -1
    core: bool = True  # core: every student in the program takes these (up to `take`); elective: sampled

    @property
    def patterns(self) -> list[str]:
        return [self.pattern] if isinstance(self.pattern, str) else list(self.pattern)


class Program(BaseModel):
    """A degree program / major: which subjects its students take. Programs
    are what make a cohort look like a university rather than one giant
    class -- an engineering student and a biology student share first-year
    chemistry and maths, then diverge."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    intake_share: float = Field(gt=0)  # relative weight when assigning students to programs
    rules: list[ProgramRule] = Field(min_length=1)


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    title: str = "LJA subject catalogue"
    rubric_levels: dict[int, str] = Field(default_factory=lambda: dict(DEFAULT_RUBRIC_LEVELS))
    competencies: list[Competency] = Field(min_length=1)
    subjects: list[Subject] = Field(min_length=1)
    # Optional. Without programs every student takes every subject (the
    # supplied workbook's shape). With them, enrolment follows the rules.
    programs: list[Program] = Field(default_factory=list)

    @model_validator(mode="after")
    def _cross_refs(self) -> Catalogue:
        comp_ids = [c.id for c in self.competencies]
        if len(set(comp_ids)) != len(comp_ids):
            raise ValueError(f"duplicate competency ids {comp_ids}")
        codes = [s.code for s in self.subjects]
        if len(set(codes)) != len(codes):
            raise ValueError(f"duplicate subject codes {codes}")
        known = set(comp_ids)
        for subject in self.subjects:
            for silo in subject.silos:
                if silo.competency not in known:
                    raise ValueError(f"{subject.code}:{silo.id} references unknown competency {silo.competency!r}")
        if sorted(self.rubric_levels) != list(range(len(self.rubric_levels))):
            raise ValueError("rubric_levels must be a contiguous 0..N ladder")
        program_codes = [p.code for p in self.programs]
        if len(set(program_codes)) != len(program_codes):
            raise ValueError(f"duplicate program codes {program_codes}")
        for program in self.programs:
            for rule in program.rules:
                if not self.match_subjects(rule.patterns):
                    raise ValueError(f"program {program.code}: rule {rule.patterns} in year {rule.year} matches no subject")
        traits_lengths = {len(c.traits) for c in self.competencies if c.traits is not None}
        if len(traits_lengths) > 1:
            raise ValueError(f"competency traits must all have the same length, got {sorted(traits_lengths)}")
        return self

    def match_subjects(self, patterns: list[str]) -> list[str]:
        """Subject codes matching any of the glob patterns, in catalogue order."""
        return [s.code for s in self.subjects if any(fnmatch.fnmatchcase(s.code, p) for p in patterns)]

    def program(self, code: str) -> Program:
        for p in self.programs:
            if p.code == code:
                return p
        raise KeyError(code)

    # -- convenience views ----------------------------------------------------

    def subject(self, code: str) -> Subject:
        for s in self.subjects:
            if s.code == code:
                return s
        raise KeyError(code)

    def competency(self, comp_id: str) -> Competency:
        for c in self.competencies:
            if c.id == comp_id:
                return c
        raise KeyError(comp_id)

    def silo_key_to_competency(self) -> dict[str, str]:
        """"SUBJECT:SILOn" -> competency id, the ground truth mapping."""
        return {f"{s.code}:{silo.id}": silo.competency for s in self.subjects for silo in s.silos}

    def competency_subjects(self) -> dict[str, set[str]]:
        """competency id -> the subject codes that carry a SILO tagged with it."""
        out: dict[str, set[str]] = {c.id: set() for c in self.competencies}
        for s in self.subjects:
            for silo in s.silos:
                out[silo.competency].add(s.code)
        return out

    def cross_subject_competencies(self) -> list[str]:
        """Competencies evidenced by two or more subjects -- the only ones a
        'persistent gap' (gap_detection's label for ≥2 subjects evidencing)
        can ever be reported against, so the only sensible planted-gap
        targets.
        """
        return sorted(cid for cid, subjects in self.competency_subjects().items() if len(subjects) >= 2)


def load_catalogue(path: str | Path) -> Catalogue:
    with Path(path).open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Catalogue.model_validate(raw)


def save_catalogue(catalogue: Catalogue, path: str | Path) -> None:
    data = catalogue.model_dump(mode="json", exclude_none=True)
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)


# -- bridges to the rest of the pipeline --------------------------------------


def catalogue_to_dataset_shape(catalogue: Catalogue) -> LjaDataset:
    """The catalogue expressed as the loader's own types, with no students.

    This is exactly what load_dataset() would return for a workbook whose
    Assessment Map came from this catalogue -- test_catalogue.py checks that
    against the supplied workbook for the three real subjects, which is
    what makes 'verbatim' a tested claim rather than a comment.
    """
    silos: dict[str, Silo] = {}
    assessments: list[Assessment] = []
    for subject in catalogue.subjects:
        for silo in subject.silos:
            silos[f"{subject.code}:{silo.id}"] = Silo(subject.code, silo.id, silo.text)
        for a in subject.assessments:
            assessments.append(
                Assessment(
                    subject_code=subject.code,
                    assessment_name=a.name,
                    weight=a.weight,
                    contribution=a.contribution,
                    early_assessment=a.early_assessment,
                    hurdle=a.hurdle,
                    silo_ids=tuple(a.silos),
                )
            )
    return LjaDataset(silos=silos, assessments=assessments, results=[], student_summaries=[])


def ground_truth_clustering(catalogue: Catalogue) -> SiloClusteringResult:
    """The catalogue's competency tags in the exact shape the LLM's
    clustering is cached in, so `lja.cli --clustering-cache <this>` runs the
    gap detector against known-correct clusters. That isolates gap detection
    from clustering quality, which the LLM path never lets you do.
    """
    members: dict[str, list[SiloRef]] = {c.id: [] for c in catalogue.competencies}
    for subject in catalogue.subjects:
        for silo in subject.silos:
            members[silo.competency].append(SiloRef(subject_code=subject.code, silo_local_id=silo.id))
    clusters = [
        CompetencyCluster(
            competency_label=catalogue.competency(cid).label,
            rationale=f"Catalogue ground truth ({cid}): {catalogue.competency(cid).description or 'as tagged in the catalogue'}",
            members=refs,
        )
        for cid, refs in members.items()
        if refs  # a competency nobody tags is not a cluster
    ]
    return SiloClusteringResult(clusters=clusters, flagged_silos=[])
