import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ai.providers.claude_code_client import ClaudeCodeProvider


def test_init_refuses_when_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        ClaudeCodeProvider()


def test_init_refuses_when_cli_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("shutil.which", return_value=None):
        with pytest.raises(EnvironmentError, match="not found"):
            ClaudeCodeProvider()


def _make_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        return ClaudeCodeProvider()


def test_generate_parses_json_result(monkeypatch):
    provider = _make_provider(monkeypatch)
    fake_proc = MagicMock(stdout='{"result": "John Doe\\nTailored resume text"}', stderr="")
    with patch("subprocess.run", return_value=fake_proc) as mock_run:
        result = provider.generate(prompt="p", system_prompt="s", model="claude-sonnet-4-6")

    assert result.text == "John Doe\nTailored resume text"
    assert result.provider == "claude_code"
    assert result.estimated_cost_usd == 0.0
    called_cmd = mock_run.call_args.args[0]
    assert called_cmd[0] == "/usr/local/bin/claude"
    assert "-p" in called_cmd
    assert "--model" in called_cmd and "claude-sonnet-4-6" in called_cmd


def test_generate_falls_back_to_raw_stdout_on_non_json(monkeypatch):
    provider = _make_provider(monkeypatch)
    fake_proc = MagicMock(stdout="plain text output, not json", stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        result = provider.generate(prompt="p", system_prompt="s", model="m")
    assert result.text == "plain text output, not json"


def test_generate_raises_on_called_process_error(monkeypatch):
    provider = _make_provider(monkeypatch)
    err = subprocess.CalledProcessError(1, "claude", stderr="boom")
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError, match="boom"):
            provider.generate(prompt="p", system_prompt="s", model="m")


def test_generate_raises_on_timeout(monkeypatch):
    provider = _make_provider(monkeypatch)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 300)):
        with pytest.raises(RuntimeError, match="timed out"):
            provider.generate(prompt="p", system_prompt="s", model="m")


def test_generate_raises_on_empty_output(monkeypatch):
    provider = _make_provider(monkeypatch)
    fake_proc = MagicMock(stdout='{"result": ""}', stderr="no content")
    with patch("subprocess.run", return_value=fake_proc):
        with pytest.raises(RuntimeError, match="empty output"):
            provider.generate(prompt="p", system_prompt="s", model="m")
