"""Runnable pipeline: Excel -> LLM SILO clustering (cached) -> gap report.

    cd python
    conda activate lja
    python -m lja.cli ../data-fixtures/CSE_results_150_students_3_Subjects.xlsx

The clustering result is cached to disk (output/silo_clustering.json by
default) because it's one LLM call whose answer doesn't change unless the
SILOs themselves do -- re-running the gap computation with different
thresholds shouldn't re-spend an LLM call every time. Pass
--refresh-clustering to force a new one.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import textwrap
from itertools import zip_longest
from pathlib import Path

from .data.excel_loader import load_dataset
from .llm.factory import get_llm_client
from .model.gap_detection import GapThresholds, compute_gaps
from .model.silo_clustering import SiloClusteringResult, cluster_silos


def _print_table(headers: list[str], rows: list[list[str]], col_widths: list[int]) -> None:
    """Fixed-column ASCII table. Cells that exceed their column's width wrap
    onto extra lines within the same row rather than truncating -- cluster
    rationales and flagged-SILO reasons are full sentences, not short labels.
    """

    def hline() -> str:
        return "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def print_row(cells: list[str]) -> None:
        wrapped = [textwrap.wrap(cell, width=w) or [""] for cell, w in zip(cells, col_widths)]
        for line_parts in zip_longest(*wrapped, fillvalue=""):
            print("|" + "|".join(f" {part:<{w}} " for part, w in zip(line_parts, col_widths)) + "|")

    print(hline())
    print_row(headers)
    print(hline())
    for row in rows:
        print_row(row)
        print(hline())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LJA: SILO clustering + gap detection over Scott's Excel dataset")
    parser.add_argument("excel_path", help="Path to the CSE_results_*.xlsx workbook")
    parser.add_argument(
        "--clustering-cache",
        default="output/silo_clustering.json",
        help="Where the LLM's SILO-to-competency clustering is cached (default: %(default)s)",
    )
    parser.add_argument(
        "--refresh-clustering",
        action="store_true",
        help="Ignore the cache and re-run the LLM clustering call",
    )
    parser.add_argument("--gaps-out", default="output/gap_report.csv")
    parser.add_argument(
        "--clusters-out",
        default="output/clusters.csv",
        help="Where to write the SILO clustering as CSV, one row per SILO (default: %(default)s)",
    )
    # Gap-detection tunables. Defaults come from lja/config.py (LJA_GAP_*),
    # which is the single source of truth; these flags exist so Sprint 5 can
    # sensitivity-test without editing a .env between runs.
    _defaults = GapThresholds()
    parser.add_argument("--absolute-floor", type=float, default=_defaults.absolute_floor,
                        help="Below this is a gap regardless of profile (default: %(default)s)")
    parser.add_argument("--absolute-ceiling", type=float, default=_defaults.absolute_ceiling,
                        help="At or above this is never a gap (default: %(default)s)")
    parser.add_argument("--relative-gap-cutoff", type=float, default=_defaults.relative_gap_cutoff,
                        help="MAD units below the student's own median at which a competency is a gap (default: %(default)s)")
    parser.add_argument("--relative-strong-cutoff", type=float, default=_defaults.relative_strong_cutoff,
                        help="MAD units above the median at which a competency counts as proficient (default: %(default)s)")
    parser.add_argument("--min-competencies", type=int, default=_defaults.min_competencies,
                        help="Below this many competencies, fall back to absolute classification (default: %(default)s)")
    parser.add_argument("--min-spread", type=float, default=_defaults.min_spread,
                        help="MAD below this counts as a flat profile; fall back to absolute (default: %(default)s)")
    parser.add_argument(
        "--extra-instructions",
        default=None,
        help=(
            "Extra text appended to the SILO clustering system prompt, for "
            "experimenting with prompt changes without editing silo_clustering.py. "
            "Ignored when the cache is used -- pair with --refresh-clustering."
        ),
    )
    args = parser.parse_args(argv)

    dataset = load_dataset(args.excel_path)
    print(
        f"Loaded {len(dataset.silos)} SILOs, {len(dataset.assessments)} assessments, "
        f"{len(dataset.results)} result rows, {len(dataset.student_summaries)} students."
    )

    cache_path = Path(args.clustering_cache)
    if cache_path.exists() and not args.refresh_clustering:
        clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
        print(f"Loaded cached SILO clustering from {cache_path} ({len(clustering.clusters)} competencies).")
    else:
        client = get_llm_client()
        print(f"LLM: {client.describe()}")
        print("Calling the LLM to semantically cluster SILOs across subjects...")
        clustering = cluster_silos(client, dataset, extra_instructions=args.extra_instructions)
        print(f"LLM usage: {client.usage_summary()}")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(clustering.model_dump_json(indent=2))
        print(
            f"Wrote clustering to {cache_path} ({len(clustering.clusters)} competencies). "
            f"mapped_by=llm, confirmed_by_staff=False -- review before trusting it."
        )

    print()
    term_width = shutil.get_terminal_size(fallback=(120, 24)).columns
    competency_w, members_w = 22, 24
    rationale_w = max(30, term_width - competency_w - members_w - 3 * 3 - 1)
    _print_table(
        ["Competency", "Members", "Rationale"],
        [
            [
                cluster.competency_label,
                ", ".join(f"{m.subject_code}:{m.silo_local_id}" for m in cluster.members),
                cluster.rationale,
            ]
            for cluster in clustering.clusters
        ],
        [competency_w, members_w, rationale_w],
    )
    if clustering.flagged_silos:
        print("\nFlagged SILOs (poorly worded, per the LLM -- feedback for subject coordinators):")
        silo_w = 16
        reason_w = max(30, term_width - silo_w - 2 * 3 - 1)
        _print_table(
            ["SILO", "Reason"],
            [[f"{flag.subject_code}:{flag.silo_local_id}", flag.reason] for flag in clustering.flagged_silos],
            [silo_w, reason_w],
        )

    # Cluster/flagged tables above only ever show a SILO by its id
    # (CSE1OOF:SILO2) -- print the actual wording too, so a reader isn't
    # forced back to the source Excel to see what a label refers to.
    silo_defs = sorted(dataset.silos.values(), key=lambda s: (s.subject_code, s.silo_local_id))
    print("\nSILO definitions (as loaded from the Assessment Map):")
    silo_id_w = 16
    silo_text_w = max(30, term_width - silo_id_w - 2 * 3 - 1)
    _print_table(
        ["SILO", "Definition"],
        [[f"{s.subject_code}:{s.silo_local_id}", s.text] for s in silo_defs],
        [silo_id_w, silo_text_w],
    )

    flag_reasons = {(f.subject_code, f.silo_local_id): f.reason for f in clustering.flagged_silos}
    clusters_out_path = Path(args.clusters_out)
    clusters_out_path.parent.mkdir(parents=True, exist_ok=True)
    with clusters_out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["competency_label", "subject_code", "silo_local_id", "rationale", "flagged", "flag_reason"])
        n_silo_rows = 0
        for cluster in clustering.clusters:
            for member in cluster.members:
                reason = flag_reasons.get((member.subject_code, member.silo_local_id), "")
                writer.writerow(
                    [cluster.competency_label, member.subject_code, member.silo_local_id, cluster.rationale, bool(reason), reason]
                )
                n_silo_rows += 1
        # Second section, appended after a blank row -- the raw SILO
        # definitions, independent of clustering, same reason as the
        # console table above.
        writer.writerow([])
        writer.writerow(["subject_code", "silo_local_id", "text"])
        for s in silo_defs:
            writer.writerow([s.subject_code, s.silo_local_id, s.text])
    print(f"\nWrote {n_silo_rows} SILO rows and {len(silo_defs)} SILO definitions to {clusters_out_path}")

    gaps = compute_gaps(
        dataset,
        clustering,
        thresholds=GapThresholds(
            absolute_floor=args.absolute_floor,
            absolute_ceiling=args.absolute_ceiling,
            relative_gap_cutoff=args.relative_gap_cutoff,
            relative_strong_cutoff=args.relative_strong_cutoff,
            min_competencies=args.min_competencies,
            min_spread=args.min_spread,
        ),
    )

    out_path = Path(args.gaps_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        # classification_basis and relative_position travel with every row:
        # tender requirement 5 asks that a displayed figure be traceable, and
        # a verdict in a CSV with no record of how it was reached is not.
        writer.writerow(
            [
                "student_id", "competency_label", "attainment_pct", "subjects_evidencing",
                "n_observations", "classification", "classification_basis", "relative_position",
            ]
        )
        for gap in gaps:
            writer.writerow(
                [
                    gap.student_id, gap.competency_label, gap.attainment_pct, gap.subjects_evidencing,
                    gap.n_observations, gap.classification, gap.classification_basis,
                    "" if gap.relative_position is None else gap.relative_position,
                ]
            )
    print(f"\nWrote {len(gaps)} gap rows to {out_path}")

    persistent = [g for g in gaps if g.classification == "persistent gap"]
    students_with_persistent_gaps = {g.student_id for g in persistent}
    print(
        f"{len(persistent)} persistent-gap rows across {len(students_with_persistent_gaps)} "
        f"of {len(dataset.student_summaries)} students."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
