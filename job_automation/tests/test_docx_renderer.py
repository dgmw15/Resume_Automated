"""Integration tests for output/docx_renderer.py"""
import pytest
from pathlib import Path
from docx import Document

from output.docx_renderer import DocxRenderer


@pytest.fixture
def renderer(tmp_path):
    return DocxRenderer(output_dir=tmp_path / "docs")


class TestDocxRenderer:
    def test_creates_output_directory(self, tmp_path):
        out_dir = tmp_path / "nested" / "docs"
        renderer = DocxRenderer(output_dir=out_dir)
        assert out_dir.exists()

    def test_generates_file_with_correct_name(self, renderer, tmp_path):
        path = renderer.render("job-abc-123", "My tailored resume content.")
        assert path.name == "job-abc-123.docx"
        assert path.exists()

    def test_generated_file_is_readable(self, renderer, tmp_path):
        content = "Jane Doe\nData Analyst\nExperience:\n- Wrote SQL queries"
        path = renderer.render("test-job", content)

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs]
        assert "Jane Doe" in paragraphs
        assert "Data Analyst" in paragraphs

    def test_multiline_content_preserved(self, renderer):
        lines = ["Line 1", "", "Line 3", "Line 4"]
        content = "\n".join(lines)
        path = renderer.render("multi-job", content)

        doc = Document(str(path))
        texts = [p.text for p in doc.paragraphs]
        assert "Line 1" in texts
        assert "Line 3" in texts
        assert "Line 4" in texts

    def test_template_used_if_provided(self, tmp_path):
        # Create a minimal template docx
        template_path = tmp_path / "template.docx"
        template_doc = Document()
        template_doc.add_paragraph("TEMPLATE HEADER")
        template_doc.save(str(template_path))

        renderer = DocxRenderer(output_dir=tmp_path / "docs", template_path=template_path)
        path = renderer.render("tmpl-job", "Tailored content.")
        assert path.exists()

    def test_missing_template_falls_back_to_blank(self, tmp_path):
        renderer = DocxRenderer(
            output_dir=tmp_path / "docs",
            template_path=tmp_path / "nonexistent.docx",
        )
        # Should not raise — falls back to blank Document
        path = renderer.render("fallback-job", "Some content.")
        assert path.exists()
