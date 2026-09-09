"""Load a completed pipeline run and serve it.

    cd python
    conda activate lja
    python -m lja.dashboard

Never calls the LLM. The clustering cache (output/silo_clustering.json by
default) must already exist -- run `python -m lja.cli <xlsx>
--refresh-clustering` first if it doesn't. This mirrors the CLI's own
cache-hit path (cli.py) rather than duplicating the "call the LLM, retry on
a coverage failure, write the cache" logic here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from .. import config
from ..data.excel_loader import load_dataset
from ..model.gap_detection import GapThresholds, compute_gaps
from ..model.silo_clustering import SiloClusteringResult
from .app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LJA dashboard: serves an already-computed pipeline run")
    parser.add_argument("--excel-path", default=config.DASHBOARD_EXCEL_PATH)
    parser.add_argument("--clustering-cache", default=config.DASHBOARD_CLUSTERING_CACHE)
    # Only the two absolute guards are exposed here. The dashboard renders a
    # run rather than tuning one -- anyone sweeping the relative cut-offs
    # should do it through lja.cli, which exposes the full set, or via the
    # LJA_GAP_* environment variables.
    _defaults = GapThresholds()
    parser.add_argument("--absolute-floor", type=float, default=_defaults.absolute_floor)
    parser.add_argument("--absolute-ceiling", type=float, default=_defaults.absolute_ceiling)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    cache_path = Path(args.clustering_cache)
    if not cache_path.exists():
        print(
            f"No clustering cache at {cache_path} -- the dashboard never calls the LLM itself. "
            f"Run this first:\n\n"
            f"  python -m lja.cli {args.excel_path} --refresh-clustering\n",
            file=sys.stderr,
        )
        return 1

    dataset = load_dataset(args.excel_path)
    clustering = SiloClusteringResult.model_validate_json(cache_path.read_text())
    gaps = compute_gaps(
        dataset,
        clustering,
        thresholds=GapThresholds(absolute_floor=args.absolute_floor, absolute_ceiling=args.absolute_ceiling),
    )
    print(f"Serving {len(dataset.student_summaries)} students, {len(gaps)} gap rows, from {cache_path}")

    app = create_app(dataset, gaps, clustering)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
