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

import re
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


def _terminating_semicolon(sql_text: str, stmt_start: int) -> int:
    """Index of the statement-terminating ';', skipping ';' inside -- comments.

    A naive sql_text.index(';') is wrong here: several queries carry a line
    comment with a semicolon in the prose (e.g. 'linked to several subjects;
    this fans out deliberately'), which would truncate the statement before its
    real end. We scan character by character, ignoring anything from a '--' to
    the end of its line, and return the first ';' in actual SQL.
    """
    i = stmt_start
    n = len(sql_text)
    while i < n:
        if sql_text.startswith("--", i):
            newline = sql_text.find("\n", i)
            if newline == -1:
                break
            i = newline + 1
            continue
        if sql_text[i] == ";":
            return i
        i += 1
    raise ValueError("No terminating semicolon found for the extracted statement.")


def extract_query(sql_text: str, banner: str) -> str:
    """Slice one query out of the multi-query extraction file.

    The file holds six queries plus a CREATE TABLE, each introduced by a
    banner comment like 'QUERY 2 —'. A caller that wants a single result set
    (e.g. the loader running Query 2 through psycopg) needs just that one
    statement, not the whole file. Returns from the query's leading SELECT/WITH
    up to and including its terminating semicolon -- so leading banner comments
    are dropped and the result is a single runnable statement.
    """
    start = sql_text.index(banner)
    match = re.search(r"\b(?:SELECT|WITH)\b", sql_text[start:])
    if match is None:
        raise ValueError(f"No SELECT/WITH statement found after banner {banner!r}.")
    stmt_start = start + match.start()
    end = _terminating_semicolon(sql_text, stmt_start) + 1
    return sql_text[stmt_start:end]


def load_query_2(prefix: str | None = None, *, path: Path | None = None) -> str:
    """Query 2 (per-criterion rubric fills, per student) as a single runnable
    statement with the prefix substituted -- the one query the Moodle loader runs.
    """
    return extract_query(load_extraction_sql(prefix, path=path), "QUERY 2")
