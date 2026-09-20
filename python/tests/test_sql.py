"""Tests for lja.data.sql -- the Moodle table-prefix substitution (IOLG-105).

The load-bearing check is the last one: after substitution, Query 2 (the core
extraction query) must contain neither a literal mdl_ nor an unreplaced
{prefix} placeholder, so the prefix is genuinely configuration end to end.
"""

from __future__ import annotations

from lja import config
from lja.data.sql import PREFIX_PLACEHOLDER, extract_query, load_extraction_sql, load_query_2


def _query2(sql: str) -> str:
    """Slice out Query 2, between its banner and Query 3's."""
    start = sql.index("QUERY 2")
    end = sql.index("QUERY 3", start)
    return sql[start:end]


def test_default_prefix_comes_from_config() -> None:
    sql = load_extraction_sql()
    assert PREFIX_PLACEHOLDER not in sql
    # Whatever config resolved to, it should actually appear on a table name.
    assert f"{config.MOODLE_TABLE_PREFIX}gradingform_rubric_fillings" in sql


def test_explicit_prefix_is_substituted_everywhere() -> None:
    sql = load_extraction_sql(prefix="m_")
    assert PREFIX_PLACEHOLDER not in sql
    assert "m_gradingform_rubric_fillings" in sql
    # Note: the file header's prose and its `sed 's/{prefix}/mdl_/g'` example
    # mention mdl_ as documentation, so a whole-file "no mdl_" assertion would
    # wrongly fail. The query *bodies* carry no literal prefix -- see the
    # Query 2 test below, which is the acceptance check.


def test_mdl_prefix_round_trips() -> None:
    sql = load_extraction_sql(prefix="mdl_")
    assert "mdl_gradingform_rubric_fillings" in sql
    assert PREFIX_PLACEHOLDER not in sql


def test_substituted_query2_has_no_literal_prefix_or_placeholder() -> None:
    query2 = _query2(load_extraction_sql(prefix="m_"))
    assert "mdl_" not in query2
    assert PREFIX_PLACEHOLDER not in query2
    # Sanity: substitution really reached Query 2's body, not just the header.
    assert "m_gradingform_rubric_fillings" in query2
    assert "m_assign_grades" in query2


def test_extract_query_ignores_semicolons_in_line_comments() -> None:
    # Query 4 has a ';' inside a -- comment ("several subjects; this fans out
    # deliberately") before its real terminator. A naive index(';') truncates
    # the statement and drops the LEFT JOIN course, so `c` goes out of scope.
    sql = load_extraction_sql(prefix="m_")
    query4 = extract_query(sql, "QUERY 4")
    assert query4.rstrip().endswith(";")
    # The join that the truncation used to drop must be present.
    assert "m_course" in query4
    assert "linked_subject" in query4


def test_load_query_2_is_a_single_complete_statement() -> None:
    query2 = load_query_2(prefix="m_")
    assert query2.rstrip().endswith(";")
    # Exactly one statement -- only the terminating semicolon, none mid-body.
    assert query2.count(";") == 1
