"""Tests for lja.data.loading -- the source-aware loader shared by the CLIs.

This is the IOLG-119 anti-drift seam: lja.cli and lja.plan both route dataset
loading and clustering-cache resolution through here, so if this behaves, the
two entry points behave identically. The Moodle branch is exercised with a
fake psycopg2 injected into sys.modules, proving the driver stays a lazy
import (never needed for the Excel path or the offline suite) and the
connection is always closed.
"""

from __future__ import annotations

import argparse
import sys
from types import SimpleNamespace

import pytest

from lja.data import loading


def test_cache_path_excel_default() -> None:
    assert loading.clustering_cache_path("excel", None) == "output/silo_clustering.json"


def test_cache_path_moodle_default() -> None:
    assert loading.clustering_cache_path("moodle", None) == "output/silo_clustering_moodle.json"


def test_cache_path_override_wins_over_source_default() -> None:
    assert loading.clustering_cache_path("moodle", "custom/path.json") == "custom/path.json"


def test_excel_source_loads_the_workbook(monkeypatch) -> None:
    monkeypatch.setattr(loading, "load_dataset", lambda path: ("excel", path))
    assert loading.load_dataset_for_source("excel", "book.xlsx", "map.csv") == ("excel", "book.xlsx")


def test_excel_source_without_path_raises_without_a_parser() -> None:
    with pytest.raises(ValueError, match="excel_path is required"):
        loading.load_dataset_for_source("excel", None, "map.csv")


def test_excel_source_without_path_calls_parser_error_when_given_a_parser() -> None:
    parser = argparse.ArgumentParser()
    # parser.error exits 2, matching the CLI's usage-error behaviour.
    with pytest.raises(SystemExit):
        loading.load_dataset_for_source("excel", None, "map.csv", parser=parser)


def test_moodle_source_uses_lazy_driver_and_closes_connection(monkeypatch) -> None:
    closed = {"value": False}

    class _FakeConn:
        def close(self) -> None:
            closed["value"] = True

    captured = {}

    def _fake_connect(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeConn()

    # Inject a fake psycopg2 so the lazy `import psycopg2` inside the loader
    # resolves without the real driver installed.
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=_fake_connect))
    monkeypatch.setattr(
        loading,
        "load_dataset_from_moodle",
        lambda conn, mapping_path: ("moodle", mapping_path),
    )

    result = loading.load_dataset_for_source("moodle", None, "map.csv")

    assert result == ("moodle", "map.csv")
    assert closed["value"] is True
    assert captured["kwargs"]["user"]  # connected via config.MOODLE_DB.connect_kwargs
