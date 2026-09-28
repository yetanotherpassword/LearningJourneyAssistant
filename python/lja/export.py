"""Structured export for longitudinal and A/B evaluation (tender requirement 7).

    cd python
    conda activate lja
    # once, to cache the clustering the export reads:
    python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx
    # then export from the same source:
    python -m lja.export ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx --out output/export
    python -m lja.export --source moodle --out output/export --anonymise

Writes students.csv, competencies.csv, cohort.csv and manifest.json. The whole
point is that two runs can be diffed -- one cohort against another, one
semester against the next -- so every column is documented in
docs/export-schema.md and manifest.json records exactly what produced the
files (source, git commit, clustering cache, thresholds).

Like lja.plan, this never calls the LLM and never regenerates the clustering:
it requires the cache lja.cli wrote for the same --source, so an export is
always drawn from the same clustering the dashboard and the plans are. Nothing
here re-decides anything -- it is a faithful CSV projection of compute_gaps()
plus the gap_evidence trend, and the per-student subject totals the loader
already carries.

--anonymise replaces every student id with an HMAC-SHA256 pseudonym keyed on
config.EXPORT_SALT (LJA_EXPORT_SALT). The same student maps to the same
pseudonym across every export taken with the same salt -- which is what lets a
"used the assistant" cohort be lined up against a "did not" cohort without
either file carrying a real id -- while the mapping cannot be reversed without
the key. An empty salt disables it rather than keying on "", which would be
stable but guessable.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import hmac
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from . import config
from .data.loading import add_source_arguments, clustering_cache_path, load_dataset_for_source
from .model.gap_detection import GapThresholds, compute_gaps
from .model.gap_evidence import describe_trend, subject_breakdown
from .model.silo_clustering import SiloClusteringResult

# Bumped by docs/export-schema.md's stated policy: first digit on any removed
# or renamed column, second on additions. Recorded in every manifest so a
# consumer can refuse a file it doesn't understand.
SCHEMA_VERSION = "1.0"


def pseudonym(student_id: str, salt: str) -> str:
    """A stable, non-reversible pseudonym for one student id.

    HMAC (not a bare hash) so the salt is a real key: without it the 12-hex
    output cannot be brute-forced back to a short id like "S001" the way an
    unsalted SHA-256 of a small id space could. Truncated to 12 hex chars --
    48 bits, ample to keep 150-student (or even whole-cohort) exports
    collision-free while staying short enough to eyeball in a diff.
    """
    return hmac.new(salt.encode(), student_id.encode(), hashlib.sha256).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LJA: structured export for longitudinal and A/B evaluation (tender req 7)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "xlsx_path",
        nargs="?",
        help="Path to the CSE_results_*.xlsx workbook (required for --source excel)",
    )
    add_source_arguments(parser)
    parser.add_argument(
        "--clustering-cache",
        default=None,
        help="The SILO clustering written by lja.cli (default: output/silo_clustering.json "
             "for --source excel, output/silo_clustering_moodle.json for --source moodle). "
             "Required; never regenerated here",
    )
    parser.add_argument(
        "--out",
        default="output/export",
        help="Directory the CSVs and manifest.json are written to (default: %(default)s)",
    )
    parser.add_argument(
        "--plans-dir",
        default="output/plans",
        help="Where lja.plan wrote learning_plan_<id>.json, used only to set the in_plan "
             "column (default: %(default)s)",
    )
    parser.add_argument(
        "--anonymise",
        action="store_true",
        help="Replace student ids with an HMAC pseudonym keyed on LJA_EXPORT_SALT",
    )
    args = parser.parse_args(argv)

    # Fail fast on the anonymise-without-salt combination, before any loading:
    # an empty salt would key the HMAC on "", producing stable but guessable
    # ids, so refuse it rather than emit a file that only looks anonymised.
    salt = config.EXPORT_SALT
    if args.anonymise and not salt:
        print("--anonymise needs LJA_EXPORT_SALT set (see .env.example)", file=sys.stderr)
        return 2
    ident = (lambda s: pseudonym(s, salt)) if args.anonymise else (lambda s: s)

    # Load exactly as lja.plan does: resolve the source-aware cache, require it
    # (never regenerate here), then load the dataset from the same source.
    cache_path = Path(clustering_cache_path(args.source, args.clustering_cache))
    if not cache_path.exists():
        print(
            f"No clustering cache at {cache_path}. Run python -m lja.cli --source {args.source} first.",
            file=sys.stderr,
        )
        return 2

    dataset = load_dataset_for_source(args.source, args.xlsx_path, args.mapping, parser=parser)
    clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
    thresholds = GapThresholds()
    gaps = compute_gaps(dataset, clustering, thresholds=thresholds)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plans_dir = Path(args.plans_dir)

    # --- students.csv: one row per student, with a column per subject -------
    # Subject columns are the sorted set of subject codes seen in results, so
    # the header is stable for a given dataset and two runs of the same cohort
    # line up column-for-column. A student who did not sit a subject gets a
    # blank cell (subject_totals omits it -- see excel_loader), not a 0.
    subjects = sorted({r.subject_code for r in dataset.results})
    with (out / "students.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "performance_band", "average_total", *subjects])
        for s in dataset.student_summaries:
            w.writerow(
                [
                    ident(s.student_id),
                    s.performance_band,
                    s.average_total,
                    *[s.subject_totals.get(c, "") for c in subjects],
                ]
            )

    # in_plan asks a precise question: did lja.plan target THIS competency as a
    # priority for THIS student? So it matches against the priorities' own
    # competency_label field, not a substring of the whole plan -- a label that
    # merely appears in the summary prose or under strengths_to_build_on is not
    # "in the plan" in the sense a cohort comparison cares about. Each student's
    # plan is parsed once and cached; a plan that is missing or won't parse
    # counts as no targeted competency rather than failing the export.
    plan_priorities: dict[str, set[str]] = {}

    def priority_competencies(student_id: str) -> set[str]:
        if student_id not in plan_priorities:
            path = plans_dir / f"learning_plan_{student_id}.json"
            labels: set[str] = set()
            if path.exists():
                try:
                    plan = json.loads(path.read_text())
                    labels = {
                        p["competency_label"]
                        for p in plan.get("priorities", [])
                        if isinstance(p, dict) and p.get("competency_label")
                    }
                except (json.JSONDecodeError, OSError):
                    labels = set()
            plan_priorities[student_id] = labels
        return plan_priorities[student_id]

    # --- competencies.csv: one row per (student, competency) gap ------------
    # classification_basis and relative_position travel with every row for the
    # same reason lja.cli's gap_report carries them: tender req 5 asks that a
    # figure be traceable to how it was reached. trend and in_plan are the two
    # export-only enrichments -- the longitudinal signal and whether the plan
    # generated for this student targets this competency.
    with (out / "competencies.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "student_id", "competency_label", "attainment_pct", "classification",
                "classification_basis", "relative_position", "subjects_evidencing",
                "n_observations", "trend", "in_plan",
            ]
        )
        for g in gaps:
            trend = describe_trend(
                subject_breakdown(dataset, clustering, g.student_id, g.competency_label)
            )
            in_plan = g.competency_label in priority_competencies(g.student_id)
            w.writerow(
                [
                    ident(g.student_id),
                    g.competency_label,
                    g.attainment_pct,
                    g.classification,
                    g.classification_basis,
                    "" if g.relative_position is None else g.relative_position,
                    g.subjects_evidencing,
                    g.n_observations,
                    trend,
                    in_plan,
                ]
            )

    # --- cohort.csv: one row per competency, aggregated across students -----
    # The A/B-comparison grain: gap_rate is the fraction of students whose
    # verdict for this competency is a gap (isolated OR persistent -- both end
    # in "gap"), proficient_rate the fraction proficient. No student ids here,
    # so this file is safe to share even from a non-anonymised run.
    by_label: dict[str, list] = defaultdict(list)
    for g in gaps:
        by_label[g.competency_label].append(g)
    with (out / "cohort.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["competency_label", "n_students", "mean_attainment", "gap_rate", "proficient_rate"])
        for label, rows in sorted(by_label.items()):
            n = len(rows)
            w.writerow(
                [
                    label,
                    n,
                    round(mean(r.attainment_pct for r in rows), 2),
                    round(sum(r.classification.endswith("gap") for r in rows) / n, 3),
                    round(sum(r.classification == "proficient" for r in rows) / n, 3),
                ]
            )

    # --- manifest.json: exactly what produced the files above ---------------
    # Two runs are meant to be diffed, so a reader needs to know they came from
    # the same code, thresholds and clustering before trusting a difference is
    # about the students and not the pipeline. git_commit falls back to
    # "unknown" rather than failing the export when run outside a checkout.
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit = "unknown"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": args.source,
        "git_commit": commit,
        "clustering_cache": str(cache_path),
        "thresholds": dataclasses.asdict(thresholds),
        "anonymised": args.anonymise,
        "files": ["students.csv", "competencies.csv", "cohort.csv"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"Wrote {out}/students.csv, competencies.csv, cohort.csv, manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
