"""Loads the read-only extraction SQL and fills in the Moodle table prefix.

sql/moodle_attainment_extraction.sql is written with a {prefix} placeholder
wherever a Moodle table is named, rather than a hardcoded mdl_, because the
prefix is configuration -- our devenv uses m_, a hosted instance usually uses
mdl_ (see sql/README.md and IOLG-105). This module is the single place that
turns that template into runnable SQL, substituting the prefix from
config.MOODLE_TABLE_PREFIX unless the caller overrides it.

It only substitutes the prefix; it does not open a database connection. The
connection settings live in config.MOODLE_DB, so a future loader can do its own
psycopg.connect(**config.MOODLE_DB.connect_kwargs) without this module growing a
driver dependency.
"""

from __future__ import annotations

from pathlib import Path

from .. import config

# repo-root/sql/moodle_attainment_extraction.sql, reached from python/lja/data/.
_SQL_DIR = Path(__file__).resolve().parents[3] / "sql"
EXTRACTION_SQL_PATH = _SQL_DIR / "moodle_attainment_extraction.sql"

# The literal token the SQL file carries in place of a hardcoded prefix.
PREFIX_PLACEHOLDER = "{prefix}"


def load_extraction_sql(prefix: str | None = None, *, path: Path | None = None) -> str:
    """Return the extraction SQL with every {prefix} placeholder substituted.

    prefix defaults to config.MOODLE_TABLE_PREFIX. A plain str.replace (not
    str.format) is used deliberately: the SQL contains no other braces to
    escape, and replace can't be tripped by one appearing in future.
    """
    if prefix is None:
        prefix = config.MOODLE_TABLE_PREFIX
    text = (path or EXTRACTION_SQL_PATH).read_text(encoding="utf-8")
    return text.replace(PREFIX_PLACEHOLDER, prefix)
