"""Score a pipeline run against a generated cohort's ground truth (IOLG-113).

    cd python
    python -m lja.cli ../data-fixtures/X.xlsx --clustering-cache ../data-fixtures/X.clustering.json
    python -m lja.data.catalogue_verify ../data-fixtures/X.truth.json --gaps output/gap_report.csv

    # or, to score the LLM's own clustering as well as the gaps found through it:
    python -m lja.cli ../data-fixtures/X.xlsx --refresh-clustering --allow-unconfirmed
    python -m lja.data.catalogue_verify ../data-fixtures/X.truth.json \
        --gaps output/gap_report.csv --clustering output/silo_clustering.json

Reports three things, none of which the supplied dataset can give:

1. Planted-gap recall: of the students the generator deliberately
   suppressed in one competency, how many does the gap report flag in that
   competency (as any gap, and as a "persistent gap" specifically)?
2. Unplanted flags: students flagged with a persistent gap who were NOT
   planted. These are not automatically false positives -- every student
   has a real per-competency ability vector -- so each is checked against
   the truth: was the flagged competency genuinely that student's weakest?
3. Clustering agreement (when --clustering is given): pairwise
   precision/recall of "these two SILOs are the same competency" between the
   LLM's clusters and the catalogue's tags.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from ..model.silo_clustering import SiloClusteringResult

GAP_CLASSES = {"persistent gap", "isolated gap"}


def load_gap_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def labels_by_truth_competency(truth: dict, clustering: SiloClusteringResult | None) -> dict[str, set[str]]:
    """truth competency id -> the labels the gap report would use for it.

    Against the ground-truth clustering that is just the competency's own
    label. Against an LLM clustering it is every LLM cluster that absorbed
    at least one of the competency's SILOs.
    """
    if clustering is None:
        return {cid: {label} for cid, label in truth["competency_labels"].items()}
    silo_to_llm = {f"{m.subject_code}:{m.silo_local_id}": c.competency_label for c in clustering.clusters for m in c.members}
    out: dict[str, set[str]] = defaultdict(set)
    for silo_key, cid in truth["silo_competency"].items():
        if silo_key in silo_to_llm:
            out[cid].add(silo_to_llm[silo_key])
    return dict(out)


def score_planted(truth: dict, rows: list[dict[str, str]], label_map: dict[str, set[str]]) -> dict:
    by_student: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_student[r["student_id"]].append(r)
    detected_any = detected_persistent = 0
    misses: list[str] = []
    for sid, info in truth["planted"].items():
        labels = label_map.get(info["competency"], set())
        hits = [r for r in by_student.get(sid, []) if r["competency_label"] in labels and r["classification"] in GAP_CLASSES]
        if hits:
            detected_any += 1
            if any(r["classification"] == "persistent gap" for r in hits):
                detected_persistent += 1
        else:
            misses.append(sid)
    n = len(truth["planted"])
    return {
        "planted": n,
        "detected_any": detected_any,
        "detected_persistent": detected_persistent,
        "recall_any": detected_any / n if n else None,
        "recall_persistent": detected_persistent / n if n else None,
        "missed": misses,
    }


def score_unplanted(truth: dict, rows: list[dict[str, str]], label_map: dict[str, set[str]]) -> dict:
    label_to_cids: dict[str, set[str]] = defaultdict(set)
    for cid, labels in label_map.items():
        for label in labels:
            label_to_cids[label].add(cid)
    planted = set(truth["planted"])
    flagged: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["classification"] == "persistent gap" and r["student_id"] not in planted:
            flagged[r["student_id"]].add(r["competency_label"])
    consistent = 0
    for sid, labels in flagged.items():
        abilities = truth["students"][sid]["abilities"]
        ranked = sorted(abilities, key=abilities.get)
        weakest_third = set(ranked[: max(1, len(ranked) // 3)])
        cids = set().union(*(label_to_cids.get(label, set()) for label in labels))
        if cids & weakest_third:
            consistent += 1
    return {
        "unplanted_flagged": len(flagged),
        "consistent_with_ability": consistent,
        "students_total": len(truth["students"]),
    }


def score_clustering(truth: dict, clustering: SiloClusteringResult) -> dict:
    truth_map = truth["silo_competency"]
    llm_map = {f"{m.subject_code}:{m.silo_local_id}": c.competency_label for c in clustering.clusters for m in c.members}
    keys = sorted(k for k in truth_map if k in llm_map)
    tp = fp = fn = 0
    for a, b in combinations(keys, 2):
        same_truth = truth_map[a] == truth_map[b]
        same_llm = llm_map[a] == llm_map[b]
        if same_truth and same_llm:
            tp += 1
        elif same_llm:
            fp += 1
        elif same_truth:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    return {
        "silos_compared": len(keys),
        "silos_uncovered": len(truth_map) - len(keys),
        "truth_clusters": len(set(truth_map.values())),
        "llm_clusters": len(clustering.clusters),
        "pair_precision": precision,
        "pair_recall": recall,
        "pair_f1": f1,
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a gap report against generated ground truth (IOLG-113)")
    parser.add_argument("truth", help="The .truth.json written beside the generated workbook")
    parser.add_argument("--gaps", required=True, help="gap_report.csv from lja.cli")
    parser.add_argument("--clustering", default=None,
                        help="The clustering JSON the run used, if it was the LLM's rather than the ground truth")
    parser.add_argument("--min-recall", type=float, default=None,
                        help="Exit 1 if persistent-gap recall on planted students is below this fraction")
    parser.add_argument("--json", action="store_true", help="Print the scores as JSON instead of text")
    args = parser.parse_args(argv)

    truth = json.loads(Path(args.truth).read_text())
    rows = load_gap_rows(Path(args.gaps))
    clustering = SiloClusteringResult.model_validate_json(Path(args.clustering).read_text()) if args.clustering else None

    label_map = labels_by_truth_competency(truth, clustering)
    report = {
        "planted": score_planted(truth, rows, label_map),
        "unplanted": score_unplanted(truth, rows, label_map),
    }
    if clustering is not None:
        report["clustering"] = score_clustering(truth, clustering)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        p = report["planted"]
        u = report["unplanted"]
        print(f"Gap report: {len(rows)} rows over {len({r['student_id'] for r in rows})} students "
              f"(truth has {u['students_total']}).")
        print(f"Planted gaps: {p['planted']} students")
        print(f"  flagged in the planted competency (any gap):     {p['detected_any']}  ({_pct(p['recall_any'])})")
        print(f"  flagged as a PERSISTENT gap in that competency:  {p['detected_persistent']}  ({_pct(p['recall_persistent'])})")
        if p["missed"]:
            print(f"  missed: {', '.join(p['missed'][:20])}{' ...' if len(p['missed']) > 20 else ''}")
        print(f"Unplanted students with a persistent gap: {u['unplanted_flagged']}")
        print(f"  of which the flagged competency is in the student's weakest third by true ability: "
              f"{u['consistent_with_ability']}")
        if clustering is not None:
            c = report["clustering"]
            print(f"Clustering vs catalogue: {c['llm_clusters']} LLM clusters vs {c['truth_clusters']} true competencies "
                  f"over {c['silos_compared']} SILOs ({c['silos_uncovered']} uncovered)")
            print(f"  pairwise precision {_pct(c['pair_precision'])}, recall {_pct(c['pair_recall'])}, F1 {_pct(c['pair_f1'])}")

    if args.min_recall is not None:
        r = report["planted"]["recall_persistent"]
        if r is None or r < args.min_recall:
            print(f"\nFAIL: persistent-gap recall {_pct(r)} is below --min-recall {_pct(args.min_recall)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
