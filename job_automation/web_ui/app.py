"""
web_ui/app.py — Local review UI for DOCX_READY jobs.

Stdlib-only HTTP server: list tailored resumes awaiting review, approve or
reject them, download the rendered DOCX. No framework, no JS, no auto-refresh
(reload the page). Replaces the never-implemented Streamlit stub.

Run: python web_ui/app.py   ->  http://localhost:8765
"""
from __future__ import annotations

import html
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from data.models import JobStatus
from data.tracker import ExcelTracker
from output.docx_renderer import DEFAULT_OUTPUT_DIR, _validate_job_id, _validate_output_path

PORT = 8765


def _snippet(text: str | None, limit: int = 400) -> str:
    text = (text or "").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _row_html(row: dict) -> str:
    job_id = html.escape(str(row.get("id", "")))
    coverage_score = row.get("keyword_coverage_score")
    coverage_text = f"{coverage_score}%" if coverage_score is not None else "n/a"
    missing = html.escape(row.get("keyword_coverage_missing") or "none")
    verdict = html.escape(row.get("ats_verdict") or "n/a")
    critique = html.escape(row.get("ats_critique") or "")
    critique_block = f'<pre class="critique">{critique}</pre>' if critique else ""
    return f"""
<section class="job">
  <h2>{html.escape(row.get('role') or '')} — {html.escape(row.get('company') or '')}</h2>
  <p class="jd"><strong>JD:</strong> {html.escape(_snippet(row.get('raw_description')))}</p>
  <p class="ats"><strong>Keyword coverage:</strong> {html.escape(coverage_text)} —
    missing: {missing} &nbsp;|&nbsp; <strong>ATS verdict:</strong> {verdict}</p>
  {critique_block}
  <pre class="resume">{html.escape(row.get('tailored_resume') or '')}</pre>
  <div class="actions">
    <a href="/docx/{job_id}">Download .docx</a>
    <form method="post" action="/action" class="inline">
      <input type="hidden" name="job_id" value="{job_id}">
      <button name="decision" value="approved">Approve</button>
      <button name="decision" value="rejected">Reject</button>
    </form>
  </div>
</section>"""


def _index_html(rows: list[dict]) -> str:
    body = "".join(_row_html(r) for r in rows) or "<p>No jobs waiting for review.</p>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Resume review</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
.job {{ border: 1px solid #ccc; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }}
.ats {{ font-size: 0.9rem; color: #444; }}
.critique {{ white-space: pre-wrap; background: #fff8e1; padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.9rem; }}
.resume {{ white-space: pre-wrap; background: #f7f7f7; padding: 0.75rem; border-radius: 4px; max-height: 300px; overflow-y: auto; }}
.actions {{ display: flex; gap: 1rem; align-items: center; }}
.inline {{ display: inline-flex; gap: 0.5rem; }}
button {{ cursor: pointer; }}
</style></head>
<body><h1>Resumes awaiting review</h1>{body}</body></html>"""


class ReviewHandler(BaseHTTPRequestHandler):
    tracker: ExcelTracker  # set by main() before serve_forever()

    def do_GET(self) -> None:
        if self.path == "/":
            rows = self.tracker.list_rows_by_status(JobStatus.DOCX_READY)
            self._send_html(_index_html(rows))
        elif self.path.startswith("/docx/"):
            self._serve_docx(self.path.removeprefix("/docx/"))
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/action":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        fields = urllib.parse.parse_qs(self.rfile.read(length).decode())
        job_id = fields.get("job_id", [""])[0]
        decision = fields.get("decision", [""])[0]
        status = {"approved": JobStatus.APPROVED, "rejected": JobStatus.REJECTED}.get(decision)
        if job_id and status:
            self.tracker.update(job_id, status=status)
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def _serve_docx(self, raw_job_id: str) -> None:
        try:
            job_id = _validate_job_id(urllib.parse.unquote(raw_job_id))
            safe_path = _validate_output_path(DEFAULT_OUTPUT_DIR, f"{job_id}.docx")
        except ValueError:
            self.send_error(400)
            return
        rows = self.tracker.list_rows_by_status(JobStatus.DOCX_READY)
        if not any(r.get("id") == job_id for r in rows) or not safe_path.exists():
            self.send_error(404)
            return
        data = safe_path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.send_header("Content-Disposition", f'attachment; filename="{safe_path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, body: str) -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # quieter than the stdlib default
        pass


def main() -> None:
    ReviewHandler.tracker = ExcelTracker()
    server = ThreadingHTTPServer(("localhost", PORT), ReviewHandler)
    print(f"Review UI running at http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
