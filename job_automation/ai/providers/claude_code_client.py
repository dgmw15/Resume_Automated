"""
ai/providers/claude_code_client.py — Claude Code subscription provider (Phase 2B).

Calls the `claude` CLI in headless mode (`claude -p`), authenticated via the
user's Pro/Max subscription login rather than ANTHROPIC_API_KEY. Subscription
usage shares the account's 5-hour rolling + weekly windows across Claude
chat/Code/Cowork — it is not billed per token, so cost is reported as $0.00.
It still flows through the same ProviderResult/BudgetLedger contract so
callers don't special-case it; the daily/monthly USD caps in config.yaml
simply have no bite on this provider (Anthropic enforces the real limit).

Mutual exclusivity (see resume-tailoring-automation-plan.md Phase 2B):
- `claude -p` will NOT read subscription OAuth credentials if
  ANTHROPIC_API_KEY is set in the environment — it uses the API key instead,
  which bills pay-per-token. This class refuses to initialise in that case
  so the two paths can never silently double up.
- `--bare` mode never reads OAuth credentials at all. This class does not
  pass --bare.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess

from ai.providers.base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)

CLAUDE_BIN = "claude"
TIMEOUT_SECONDS = 300


def _resolve_claude_bin() -> str | None:
    """
    Locate the claude executable, preferring a real Windows executable
    extension over the bare name.

    On Windows, npm installs CLI tools as a trio of shim files with no
    extension, .cmd, and .ps1 (e.g. `claude`, `claude.cmd`, `claude.ps1`).
    Python 3.12's shutil.which() checks the bare name first — but that file
    is a Node shebang script, not a valid Win32 executable, so
    subprocess.run() fails with WinError 193 if we hand it that path
    directly. Asking for the .cmd/.exe/.bat variant explicitly sidesteps
    the bare-name-first search order.
    """
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat"):
            resolved = shutil.which(CLAUDE_BIN + ext)
            if resolved:
                return resolved
    return shutil.which(CLAUDE_BIN)


class ClaudeCodeProvider(BaseProvider):
    """Calls the Claude Code CLI in non-interactive mode using subscription auth."""

    def __init__(self) -> None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is set — 'claude -p' would authenticate with it "
                "(pay-per-token) instead of the subscription. Unset it to use the "
                "claude_code provider."
            )
        self._claude_path = _resolve_claude_bin()
        if self._claude_path is None:
            raise EnvironmentError(
                f"'{CLAUDE_BIN}' CLI not found on PATH — install Claude Code and log "
                "in with your subscription to use this provider."
            )

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResult:
        full_prompt = f"{system_prompt}\n\n{prompt}"
        try:
            # Prompt goes via stdin, not as a CLI arg: on Windows, claude.cmd
            # runs through cmd.exe, which caps command lines at ~8191 chars —
            # a tailoring prompt (JD + full base resume) routinely exceeds
            # that and fails with "The command line is too long."
            proc = subprocess.run(
                [self._claude_path, "-p", "--output-format", "json", "--model", model],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"claude -p failed (exit {exc.returncode}): {exc.stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"claude -p timed out after {TIMEOUT_SECONDS}s") from exc

        text = self._extract_text(proc.stdout)
        if not text:
            raise RuntimeError(f"claude -p returned empty output. stderr: {proc.stderr}")

        return ProviderResult(
            text=text,
            model=model,
            provider="claude_code",
            estimated_cost_usd=0.0,  # subscription usage — no per-token charge
        )

    @staticmethod
    def _extract_text(stdout: str) -> str:
        """Parse `claude -p --output-format json` stdout; fall back to raw text."""
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout.strip()
        return str(payload.get("result", "")).strip()


if __name__ == "__main__":
    # ponytail: minimal runnable check for the parsing logic — the actual subprocess
    # call needs a live subscription login and isn't testable here or in CI; see
    # tests/test_claude_code_client.py for the mocked subprocess.run coverage.
    assert ClaudeCodeProvider._extract_text('{"result": "John Doe\\n..."}') == "John Doe\n..."
    assert ClaudeCodeProvider._extract_text("not json, plain text") == "not json, plain text"
    print("claude_code_client self-check OK")
