"""
core/dataframe_engine.py — Config-driven dataframe engine abstraction.

Provides a single load_roles() API used by trawl.py and orchestrator.py.
Supports pandas (default) and Polars backends, switchable via config.yaml:

    dataframe:
      engine: "pandas"               # "pandas" | "polars"
      allow_fallback_to_pandas: true  # Polars failure → pandas retry

Design rules
------------
- Output is always list[str]: trimmed, non-empty strings, original row order.
- Polars and pandas paths produce identical lists on well-formed input.
- No behavior change when engine="pandas" (default).
- Never raises on a missing/malformed workbook — returns [] and logs.
- Explicit log line always shows which engine served each load.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine constants
# ---------------------------------------------------------------------------

ENGINE_PANDAS = "pandas"
ENGINE_POLARS = "polars"
_VALID_ENGINES = {ENGINE_PANDAS, ENGINE_POLARS}


# ---------------------------------------------------------------------------
# DataFrameEngine
# ---------------------------------------------------------------------------

class DataFrameEngine:
    """
    Engine-agnostic wrapper for Excel role loading.

    Parameters
    ----------
    engine : str
        "pandas" or "polars".  Unknown values fall back to pandas with a warning.
    allow_fallback_to_pandas : bool
        When True, a Polars read failure retries with pandas and logs a warning.
        When False, the failure propagates as an empty list without retry.
    """

    def __init__(
        self,
        engine: str = ENGINE_PANDAS,
        allow_fallback_to_pandas: bool = True,
    ) -> None:
        if engine not in _VALID_ENGINES:
            logger.warning(
                "Unknown dataframe engine %r — falling back to pandas.", engine
            )
            engine = ENGINE_PANDAS
        self.engine = engine
        self.allow_fallback_to_pandas = allow_fallback_to_pandas
        logger.debug(
            "DataFrameEngine initialised: engine=%s, allow_fallback=%s",
            self.engine,
            self.allow_fallback_to_pandas,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_roles(self, path: Path, sheet: str, column: str) -> list[str]:
        """
        Load a list of role strings from an Excel workbook column.

        Semantics (engine-independent)
        --------------------------------
        - Null / NaN / None values are dropped.
        - Values are coerced to str and whitespace-stripped.
        - Empty strings remaining after strip are dropped.
        - Original row order is preserved.
        - Returns [] if the file doesn't exist, the sheet is missing,
          the column is missing, or an unrecoverable error occurs.

        Parameters
        ----------
        path : Path
            Absolute or relative path to the .xlsx workbook.
        sheet : str
            Worksheet name to read.
        column : str
            Column header whose values are returned.
        """
        ctx = f"workbook={path!r}, sheet={sheet!r}, column={column!r}"

        if not path.exists():
            logger.debug("load_roles: file not found — %s", ctx)
            return []

        if self.engine == ENGINE_POLARS:
            roles, ok = self._load_roles_polars(path, sheet, column, ctx)
            if not ok and self.allow_fallback_to_pandas:
                logger.warning(
                    "Polars load failed — falling back to pandas. %s", ctx
                )
                roles, _ = self._load_roles_pandas(path, sheet, column, ctx)
        else:
            roles, _ = self._load_roles_pandas(path, sheet, column, ctx)

        logger.info(
            "load_roles[%s]: %d roles loaded — %s",
            "polars" if self.engine == ENGINE_POLARS else "pandas",
            len(roles),
            ctx,
        )
        return roles

    # ------------------------------------------------------------------
    # Pandas backend
    # ------------------------------------------------------------------

    def _load_roles_pandas(
        self,
        path: Path,
        sheet: str,
        column: str,
        ctx: str,
    ) -> tuple[list[str], bool]:
        """
        Load roles using pandas.

        Returns (roles, success).  On any exception returns ([], False).
        """
        try:
            import pandas as pd  # local import keeps polars-only environments happy
        except ImportError:
            logger.error("pandas is not installed. %s", ctx)
            return [], False

        try:
            df = pd.read_excel(path, sheet_name=sheet)
        except Exception as exc:
            logger.warning("pandas: could not read workbook — %s — %s", exc, ctx)
            return [], False

        if column not in df.columns:
            logger.warning("pandas: column %r not found in %s", column, ctx)
            return [], False

        try:
            roles: list[str] = (
                df[column]
                .dropna()
                .astype(str)
                .str.strip()
                .loc[lambda s: s != ""]
                .tolist()
            )
            return roles, True
        except Exception as exc:
            logger.warning("pandas: column extraction failed — %s — %s", exc, ctx)
            return [], False

    # ------------------------------------------------------------------
    # Polars backend
    # ------------------------------------------------------------------

    def _load_roles_polars(
        self,
        path: Path,
        sheet: str,
        column: str,
        ctx: str,
    ) -> tuple[list[str], bool]:
        """
        Load roles using Polars.

        Returns (roles, success).  On any exception returns ([], False).

        Polars parity semantics vs pandas
        ----------------------------------
        pandas:  df[col].dropna().astype(str).str.strip().loc[s != ""].tolist()
        polars:  df[col].drop_nulls().cast(Utf8).str.strip_chars().filter(s != "").to_list()

        Both:
        - Drop nulls/NaN before str conversion so None never becomes "None".
        - Strip leading/trailing whitespace.
        - Drop empty strings that remain after strip.
        - Preserve original row order (neither sort nor deduplicate).
        """
        try:
            import polars as pl
        except ImportError:
            logger.error("polars is not installed. %s", ctx)
            return [], False

        try:
            df = pl.read_excel(source=path, sheet_name=sheet)
        except Exception as exc:
            logger.warning("polars: could not read workbook — %s — %s", exc, ctx)
            return [], False

        if column not in df.columns:
            logger.warning("polars: column %r not found in %s", column, ctx)
            return [], False

        try:
            stripped = (
                df[column]
                .drop_nulls()
                .cast(pl.Utf8)
                .str.strip_chars()
            )
            roles: list[str] = stripped.filter(stripped != "").to_list()
            return roles, True
        except Exception as exc:
            logger.warning("polars: column extraction failed — %s — %s", exc, ctx)
            return [], False

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> "DataFrameEngine":
        """
        Construct a DataFrameEngine from the top-level config dict.

        Reads:
            config["dataframe"]["engine"]                 → "pandas" | "polars"
            config["dataframe"]["allow_fallback_to_pandas"] → bool

        Missing keys use safe defaults (engine="pandas", fallback=True).
        """
        df_cfg = config.get("dataframe", {})
        engine = df_cfg.get("engine", ENGINE_PANDAS)
        allow_fallback = df_cfg.get("allow_fallback_to_pandas", True)
        return cls(engine=engine, allow_fallback_to_pandas=allow_fallback)
