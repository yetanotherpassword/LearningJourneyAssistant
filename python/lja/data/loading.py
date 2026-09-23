"""Source-aware dataset loading shared by the CLI entry points (IOLG-119).

Both `lja.cli` and `lja.plan` need to load the same `LjaDataset` from either
Scott's Excel workbook (`--source excel`, the default) or a live Moodle
database (`--source moodle`, IOLG-104), and both resolve a source-aware default
for the clustering cache. That logic lived only in `lja.cli`; `lja.plan`
shipped Excel-only. Keeping it here -- one loader, one arg group, one cache
rule -- is what stops the two commands from drifting again (e.g. one growing a
new source while the other silently stays behind).

Nothing in here calls the LLM or reads the clustering cache: it only turns a
`--source`/`--mapping`/`--clustering-cache` choice into a dataset and a Path.
"""

from __future__ import annotations

import argparse

from .. import config
from .excel_loader import LjaDataset, load_dataset
from .moodle_loader import load_dataset_from_moodle

# Default location of the IOLG-56 criterion->SILO mapping CSV, relative to
# python/ (where the CLIs are run from).
DEFAULT_MAPPING = "../data-fixtures/criterion_silo_map_CSE1IOI.csv"

# Source-aware clustering-cache defaults. Excel keeps the historical path the
# dashboard reads (config.DASHBOARD_CLUSTERING_CACHE); Moodle gets its own so an
# Excel run and a Moodle run don't clobber each other's clustering -- their SILO
# sets differ, and a cache that doesn't cover the dataset is unusable.
_CACHE_DEFAULTS = {
    "excel": "output/silo_clustering.json",
    "moodle": "output/silo_clustering_moodle.json",
}


def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the identical --source / --mapping options to any entry point.

    Defined once so lja.cli and lja.plan present the same choices and help
    text; each command still owns its own positionals and other flags.
    """
    parser.add_argument(
        "--source",
        choices=("excel", "moodle"),
        default="excel",
        help="Where to load the dataset from (default: %(default)s)",
    )
    parser.add_argument(
        "--mapping",
        default=DEFAULT_MAPPING,
        help="criterion->SILO mapping CSV for --source moodle (default: %(default)s)",
    )


def clustering_cache_path(source: str, override: str | None) -> str:
    """Resolve the clustering-cache path: explicit override wins, else the
    source-aware default. Returned as a str so callers wrap it in Path (or not)
    exactly as they already do.
    """
    if override is not None:
        return override
    return _CACHE_DEFAULTS[source]


def load_dataset_for_source(
    source: str,
    excel_path: str | None,
    mapping_path: str,
    *,
    parser: argparse.ArgumentParser | None = None,
) -> LjaDataset:
    """Load an `LjaDataset` from the chosen source.

    Excel takes the workbook path (required for `--source excel`); Moodle opens
    a read-only connection from config.MOODLE_DB (env-driven, IOLG-105; expected
    to be the least-privilege lja_reader role) and joins the criterion->SILO
    mapping CSV. psycopg2 is imported lazily inside the Moodle branch so the
    Excel path -- and the whole offline test suite -- never needs the driver.

    When `--source excel` is chosen with no workbook, `parser.error` is used if
    a parser is supplied (so the CLI exits 2 with usage); otherwise a
    ValueError is raised, which keeps the function testable without argparse.
    """
    if source == "moodle":
        print(
            f"Loading dataset from Moodle ({config.MOODLE_DB.host}:{config.MOODLE_DB.port}/"
            f"{config.MOODLE_DB.dbname} as {config.MOODLE_DB.user}, "
            f"prefix {config.MOODLE_TABLE_PREFIX!r})..."
        )
        import psycopg2

        conn = psycopg2.connect(**config.MOODLE_DB.connect_kwargs)
        try:
            return load_dataset_from_moodle(conn, mapping_path)
        finally:
            conn.close()

    if not excel_path:
        message = "excel_path is required when --source is excel"
        if parser is not None:
            parser.error(message)
        raise ValueError(message)
    return load_dataset(excel_path)
