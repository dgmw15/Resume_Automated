from pathlib import Path

from openpyxl import Workbook

from prompt_pipeline import build_prompt_records


def _write_trawl_sample(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Trawl"
    ws.append([
        "id", "scraped_at", "portal", "role", "company", "url", "page_num",
        "raw_description", "description_status", "notes", "skills", "continue",
    ])
    ws.append([
        "j1", "", "careersfuture", "Data Analyst", "Acme", "https://example.com/1", 1,
        "Need SQL and Python. Must have 2 years experience. Responsible for dashboards.",
        "OK", "", "sql, python", 1,
    ])
    ws.append([
        "j2", "", "careersfuture", "Data Engineer", "Beta", "https://example.com/2", 1,
        "Need Spark", "OK", "", "spark", 0,
    ])
    wb.save(path)


def test_build_prompt_records_writes_jsonl(tmp_path: Path) -> None:
    trawl_path = tmp_path / "trawl.xlsx"
    resume_path = tmp_path / "base_resume.txt"
    out_path = tmp_path / "prompts.jsonl"

    _write_trawl_sample(trawl_path)
    resume_path.write_text("Sample resume", encoding="utf-8")

    written, skipped = build_prompt_records(trawl_path, resume_path, out_path)

    assert written == 1
    assert skipped == 1
    content = out_path.read_text(encoding="utf-8")
    assert "system_prompt" in content
    assert "user_prompt" in content
    assert "signals" not in content
    assert "EXTRACTED JD SIGNALS" not in content
