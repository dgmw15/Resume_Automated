"""tests/test_review_ui.py — smoke test for the stdlib review UI (web_ui/app.py)."""
from __future__ import annotations

import http.client
import threading
import urllib.parse
from http.server import ThreadingHTTPServer

from data.models import JobListing, JobStatus
from data.tracker import ExcelTracker
from web_ui.app import ReviewHandler


def test_review_ui_smoke(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tracker = ExcelTracker(tmp_path / "Database.xlsx")
    job = JobListing(
        portal_name="careersfuture",
        role="Data Analyst",
        company="Acme",
        url="https://example.com/1",
        raw_description="<script>alert(1)</script>",
        tailored_resume="Line one\nLine two",
    )
    tracker.append(job)
    tracker.update(job.id, status=JobStatus.DOCX_READY, docx_path=str(tmp_path / "does_not_exist.docx"))

    ReviewHandler.tracker = tracker
    server = ThreadingHTTPServer(("localhost", 0), ReviewHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("localhost", port, timeout=5)

        # Index page renders and escapes untrusted JD text (XSS trust boundary)
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read().decode()
        assert resp.status == 200
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body

        # Path traversal on the docx download is rejected
        conn.request("GET", "/docx/" + urllib.parse.quote("../../etc/passwd"))
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 400

        # A job_id with no matching DOCX_READY row 404s rather than leaking a path
        conn.request("GET", "/docx/does-not-exist")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 404

        # Approve action updates the tracker
        body_bytes = urllib.parse.urlencode({"job_id": job.id, "decision": "approved"}).encode()
        conn.request(
            "POST", "/action", body=body_bytes,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 303
        approved = tracker.list_rows_by_status(JobStatus.APPROVED)
        assert any(r["id"] == job.id for r in approved)
    finally:
        server.shutdown()
        thread.join(timeout=2)
