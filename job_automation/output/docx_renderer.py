"""
output/docx_renderer.py — Renders tailored resume text to .docx files.

Safe write workflow (Prompt 12)
--------------------------------
1. Write to a temporary file (.tmp.docx) in the output directory.
2. Re-open the temp file and validate:
   a. File opens without exception.
   b. Body is non-empty (at least one non-whitespace paragraph).
   c. All required sections (from config) are present in the text.
3. Atomically rename temp → final path only after validation passes.
4. On validation failure:
   - Status is set to DOCX_GENERATION_FAILED by the caller.
   - Temp file is retained for up to docx_temp_retention_hours for debugging.
   - A DocxValidationError is raised with a descriptive message.

File path pattern: output/docs/{job_id}.docx
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("output/docs")
DEFAULT_TEMP_RETENTION_HOURS = 24


class DocxValidationError(Exception):
    """Raised when a generated DOCX fails the content validation gate."""


class DocxRenderer:
    """
    Writes plain-text tailored resumes to DOCX files with an atomic
    write-validate-move pipeline to prevent silent corruption.

    Args:
        output_dir:             directory where final files are saved.
        template_path:          optional path to a .docx template file.
        required_sections:      list of strings that must appear (case-insensitive)
                                in the DOCX body text before it is accepted.
                                Empty list → only non-empty body is required.
        temp_retention_hours:   how long failed-validation temp files are kept.
    """

    def __init__(
        self,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        template_path: Optional[Path] = None,
        required_sections: Optional[list[str]] = None,
        temp_retention_hours: int = DEFAULT_TEMP_RETENTION_HOURS,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._template_path = Path(template_path) if template_path else None
        self._required_sections: list[str] = [
            s.lower() for s in (required_sections or [])
        ]
        self._temp_retention_hours = temp_retention_hours

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self, job_id: str, tailored_text: str) -> Path:
        """
        Write tailored_text to output_dir/{job_id}.docx.

        Workflow: write → validate → atomic move.

        Returns the Path of the final file on success.
        Raises DocxValidationError if content validation fails.
        Raises IOError if the file cannot be written.
        """
        final_path = self._output_dir / f"{job_id}.docx"

        # Idempotency: if the final file already exists and is valid, return it.
        if final_path.exists():
            try:
                self._validate(final_path)
                logger.info("DOCX already exists and valid — skipping re-render: %s", final_path)
                return final_path
            except DocxValidationError:
                logger.warning("Existing DOCX failed validation — re-rendering: %s", final_path)

        # Write to temp file in the same directory (same filesystem → atomic rename)
        tmp_path = self._output_dir / f"{job_id}.tmp.docx"
        try:
            doc = self._load_template_or_new()
            self._write_content(doc, tailored_text)
            doc.save(str(tmp_path))
            logger.debug("DOCX temp written: %s", tmp_path)

            # Validate before promoting
            self._validate(tmp_path)

            # Atomic move: rename is atomic on POSIX, near-atomic on Windows
            shutil.move(str(tmp_path), str(final_path))
            logger.info("DOCX ready: %s", final_path)
            return final_path

        except DocxValidationError:
            # Retain temp for debugging; caller sets DOCX_GENERATION_FAILED
            logger.warning(
                "DOCX validation failed for job %s — temp retained at %s (for %dh)",
                job_id, tmp_path, self._temp_retention_hours,
            )
            raise

        except Exception as exc:
            # Clean up temp on unexpected errors
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise IOError(f"DOCX write failed for job {job_id}: {exc}") from exc

    def cleanup_stale_temps(self) -> int:
        """
        Delete .tmp.docx files older than temp_retention_hours.
        Returns the number of files deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._temp_retention_hours)
        deleted = 0
        for tmp_file in self._output_dir.glob("*.tmp.docx"):
            mtime = datetime.fromtimestamp(tmp_file.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                tmp_file.unlink(missing_ok=True)
                logger.debug("Deleted stale temp DOCX: %s", tmp_file)
                deleted += 1
        if deleted:
            logger.info("Cleaned up %d stale temp DOCX file(s).", deleted)
        return deleted

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_template_or_new(self) -> Document:
        if self._template_path and self._template_path.exists():
            return Document(str(self._template_path))
        return Document()

    def _write_content(self, doc: Document, text: str) -> None:
        """Write each line of resume text as a paragraph with 11pt font."""
        for line in text.splitlines():
            para = doc.add_paragraph(line)
            for run in para.runs:
                run.font.size = Pt(11)

    def _validate(self, path: Path) -> None:
        """
        Validate that path is a readable, non-empty DOCX with required sections.

        Raises DocxValidationError describing the first failure found.
        """
        # 1. File opens without exception
        try:
            doc = Document(str(path))
        except Exception as exc:
            raise DocxValidationError(f"DOCX could not be opened: {exc}") from exc

        # 2. Non-empty body
        body_text = "\n".join(p.text for p in doc.paragraphs)
        if not body_text.strip():
            raise DocxValidationError("DOCX body is empty — no paragraphs found.")

        # 3. Required sections present
        body_lower = body_text.lower()
        missing = [
            section
            for section in self._required_sections
            if section not in body_lower
        ]
        if missing:
            raise DocxValidationError(
                f"DOCX is missing required section(s): {missing}"
            )


def build_renderer_from_config(config: dict) -> DocxRenderer:
    """Convenience factory from config dict."""
    out_cfg = config.get("output", {})
    output_dir = Path(out_cfg.get("docx_output_dir", "output/docs"))
    template_path_str = out_cfg.get("docx_template_path", "")
    template_path = Path(template_path_str) if template_path_str else None
    required_sections: list[str] = out_cfg.get("docx_validation_required_sections", [])
    temp_retention_hours: int = int(out_cfg.get("docx_temp_retention_hours", DEFAULT_TEMP_RETENTION_HOURS))
    return DocxRenderer(
        output_dir=output_dir,
        template_path=template_path,
        required_sections=required_sections,
        temp_retention_hours=temp_retention_hours,
    )
