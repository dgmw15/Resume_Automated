"""
tests/test_dataframe_engine.py — Deterministic parity and fallback tests
for core/dataframe_engine.py.

Covers:
1.  Pandas backend loads a well-formed sheet correctly
2.  Polars backend loads the same sheet and produces an identical list
3.  Pandas == Polars on a shared fixture (parity gate)
4.  Both engines drop null rows, strip whitespace, and drop empty strings
5.  Missing column → [] (both engines)
6.  Missing file → [] (both engines)
7.  Polars failure + allow_fallback=True → pandas result returned
8.  Polars failure + allow_fallback=False → [] returned
9.  from_config() reads engine and allow_fallback_to_pandas correctly
10. Unknown engine string → silently becomes pandas
11. from_config() missing "dataframe" key → safe defaults (pandas, fallback=True)
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from core.dataframe_engine import DataFrameEngine, ENGINE_PANDAS, ENGINE_POLARS


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_workbook(path: Path, sheet: str, column: str, values: list) -> None:
    """Write a minimal .xlsx fixture with one header row and values below."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append([column])
    for v in values:
        ws.append([v])
    wb.save(path)


@pytest.fixture()
def roles_xlsx(tmp_path: Path) -> tuple[Path, str, str, list[str]]:
    """
    Returns (path, sheet, column, expected_roles).

    The workbook has:
      - 3 clean strings
      - 1 None (null)
      - 1 whitespace-only string
      - 1 string with leading/trailing spaces
    Expected output: 4 trimmed non-empty strings.
    """
    sheet = "Roles"
    column = "Job Role"
    raw_values = [
        "Data Analyst",
        None,
        "  Backend Engineer  ",
        "   ",           # whitespace only → dropped after strip
        "Data Engineer",
        "Product Manager",
    ]
    expected = ["Data Analyst", "Backend Engineer", "Data Engineer", "Product Manager"]
    path = tmp_path / "job_roles.xlsx"
    _write_workbook(path, sheet, column, raw_values)
    return path, sheet, column, expected


# ---------------------------------------------------------------------------
# Pandas backend
# ---------------------------------------------------------------------------

class TestPandasBackend:
    def test_loads_roles(self, roles_xlsx):
        path, sheet, column, expected = roles_xlsx
        engine = DataFrameEngine(engine=ENGINE_PANDAS)
        assert engine.load_roles(path, sheet, column) == expected

    def test_missing_file_returns_empty(self, tmp_path):
        engine = DataFrameEngine(engine=ENGINE_PANDAS)
        result = engine.load_roles(tmp_path / "nonexistent.xlsx", "Roles", "Job Role")
        assert result == []

    def test_missing_column_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", ["Analyst"])
        engine = DataFrameEngine(engine=ENGINE_PANDAS)
        result = engine.load_roles(path, "Roles", "Wrong Column")
        assert result == []

    def test_all_nulls_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", [None, None])
        engine = DataFrameEngine(engine=ENGINE_PANDAS)
        assert engine.load_roles(path, "Roles", "Job Role") == []

    def test_all_whitespace_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", ["   ", "  "])
        engine = DataFrameEngine(engine=ENGINE_PANDAS)
        assert engine.load_roles(path, "Roles", "Job Role") == []


# ---------------------------------------------------------------------------
# Polars backend
# ---------------------------------------------------------------------------

class TestPolarsBackend:
    """Skip entire class if polars is not installed."""

    @pytest.fixture(autouse=True)
    def require_polars(self):
        pytest.importorskip("polars")

    def test_loads_roles(self, roles_xlsx):
        path, sheet, column, expected = roles_xlsx
        engine = DataFrameEngine(engine=ENGINE_POLARS)
        assert engine.load_roles(path, sheet, column) == expected

    def test_missing_file_returns_empty(self, tmp_path):
        engine = DataFrameEngine(engine=ENGINE_POLARS)
        result = engine.load_roles(tmp_path / "nonexistent.xlsx", "Roles", "Job Role")
        assert result == []

    def test_missing_column_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", ["Analyst"])
        engine = DataFrameEngine(engine=ENGINE_POLARS)
        result = engine.load_roles(path, "Roles", "Wrong Column")
        assert result == []

    def test_all_nulls_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", [None, None])
        engine = DataFrameEngine(engine=ENGINE_POLARS)
        assert engine.load_roles(path, "Roles", "Job Role") == []

    def test_all_whitespace_returns_empty(self, tmp_path):
        path = tmp_path / "test.xlsx"
        _write_workbook(path, "Roles", "Job Role", ["   ", "  "])
        engine = DataFrameEngine(engine=ENGINE_POLARS)
        assert engine.load_roles(path, "Roles", "Job Role") == []


# ---------------------------------------------------------------------------
# Parity gate — pandas == polars on identical fixture
# ---------------------------------------------------------------------------

class TestParityGate:
    """Both engines must produce an identical list on the same workbook."""

    @pytest.fixture(autouse=True)
    def require_polars(self):
        pytest.importorskip("polars")

    def _both(self, path, sheet, column):
        pd_engine = DataFrameEngine(engine=ENGINE_PANDAS)
        pl_engine = DataFrameEngine(engine=ENGINE_POLARS)
        return (
            pd_engine.load_roles(path, sheet, column),
            pl_engine.load_roles(path, sheet, column),
        )

    def test_parity_clean_data(self, roles_xlsx):
        path, sheet, column, _ = roles_xlsx
        pd_result, pl_result = self._both(path, sheet, column)
        assert pd_result == pl_result, (
            f"Parity failure:\n  pandas: {pd_result}\n  polars: {pl_result}"
        )

    def test_parity_mixed_types(self, tmp_path):
        """Numeric-looking strings and leading/trailing space must be handled identically."""
        path = tmp_path / "mixed.xlsx"
        _write_workbook(
            path, "Sheet1", "Role",
            ["  Data Analyst  ", None, "123", "  ", "Engineer"],
        )
        pd_result, pl_result = self._both(path, "Sheet1", "Role")
        assert pd_result == pl_result

    def test_parity_single_row(self, tmp_path):
        path = tmp_path / "single.xlsx"
        _write_workbook(path, "Sheet1", "Role", ["Backend Developer"])
        pd_result, pl_result = self._both(path, "Sheet1", "Role")
        assert pd_result == pl_result

    def test_parity_order_preserved(self, tmp_path):
        """Original Excel row order must be maintained — no sorting."""
        path = tmp_path / "order.xlsx"
        roles = ["Zebra", "Apple", "Mango"]
        _write_workbook(path, "Sheet1", "Role", roles)
        pd_result, pl_result = self._both(path, "Sheet1", "Role")
        assert pd_result == roles
        assert pl_result == roles

    def test_parity_empty_workbook(self, tmp_path):
        path = tmp_path / "empty.xlsx"
        _write_workbook(path, "Roles", "Job Role", [])
        pd_result, pl_result = self._both(path, "Roles", "Job Role")
        assert pd_result == [] == pl_result


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

class TestFallback:
    """Polars read failure → pandas when allow_fallback_to_pandas=True."""

    @pytest.fixture(autouse=True)
    def require_polars(self):
        pytest.importorskip("polars")

    def test_fallback_enabled_returns_pandas_result(self, roles_xlsx):
        path, sheet, column, expected = roles_xlsx
        engine = DataFrameEngine(engine=ENGINE_POLARS, allow_fallback_to_pandas=True)

        # Make the Polars read fail
        with patch.object(engine, "_load_roles_polars", return_value=([], False)):
            result = engine.load_roles(path, sheet, column)

        assert result == expected

    def test_fallback_disabled_returns_empty(self, roles_xlsx):
        path, sheet, column, _ = roles_xlsx
        engine = DataFrameEngine(engine=ENGINE_POLARS, allow_fallback_to_pandas=False)

        with patch.object(engine, "_load_roles_polars", return_value=([], False)):
            result = engine.load_roles(path, sheet, column)

        assert result == []

    def test_fallback_logs_warning(self, roles_xlsx, caplog):
        path, sheet, column, _ = roles_xlsx
        engine = DataFrameEngine(engine=ENGINE_POLARS, allow_fallback_to_pandas=True)

        with patch.object(engine, "_load_roles_polars", return_value=([], False)):
            with caplog.at_level(logging.WARNING):
                engine.load_roles(path, sheet, column)

        assert any("fall" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# from_config factory
# ---------------------------------------------------------------------------

class TestFromConfig:
    def _cfg(self, engine=ENGINE_PANDAS, allow_fallback=True) -> dict:
        return {
            "dataframe": {
                "engine": engine,
                "allow_fallback_to_pandas": allow_fallback,
            }
        }

    def test_reads_engine(self):
        ef = DataFrameEngine.from_config(self._cfg(engine=ENGINE_PANDAS))
        assert ef.engine == ENGINE_PANDAS

    def test_reads_polars_engine(self):
        ef = DataFrameEngine.from_config(self._cfg(engine=ENGINE_POLARS))
        assert ef.engine == ENGINE_POLARS

    def test_reads_allow_fallback_true(self):
        ef = DataFrameEngine.from_config(self._cfg(allow_fallback=True))
        assert ef.allow_fallback_to_pandas is True

    def test_reads_allow_fallback_false(self):
        ef = DataFrameEngine.from_config(self._cfg(allow_fallback=False))
        assert ef.allow_fallback_to_pandas is False

    def test_missing_dataframe_key_uses_defaults(self):
        ef = DataFrameEngine.from_config({})
        assert ef.engine == ENGINE_PANDAS
        assert ef.allow_fallback_to_pandas is True

    def test_unknown_engine_falls_back_to_pandas(self, caplog):
        with caplog.at_level(logging.WARNING):
            ef = DataFrameEngine(engine="dask")
        assert ef.engine == ENGINE_PANDAS
        assert any("unknown" in r.message.lower() for r in caplog.records)
