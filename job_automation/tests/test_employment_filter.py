"""
tests/test_employment_filter.py — Deterministic tests for ai/employment_filter.py

Covers:
1. Internship patterns trigger FILTERED only when exclude_internship=True
2. Contract patterns trigger FILTERED only when exclude_contract=True
3. Both toggles False → role always PASSED (type still detected)
4. Unknown type follows unknown_policy ("allow" → PASSED, "deny" → FILTERED)
5. Master enabled=False → all results are SKIPPED regardless of content
6. from_config() factory reads the correct keys
7. Detection from title, description, and tags independently
8. Integration: filtered rows are skipped by _phase_validate logic
"""
from __future__ import annotations

import pytest

from ai.employment_filter import EmploymentFilter, FilterResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_filter(**kwargs) -> EmploymentFilter:
    """Convenience factory with sensible defaults."""
    defaults = dict(
        enabled=True,
        exclude_internship=True,
        exclude_contract=True,
        unknown_policy="allow",
    )
    defaults.update(kwargs)
    return EmploymentFilter(**defaults)


# ---------------------------------------------------------------------------
# Master enabled toggle
# ---------------------------------------------------------------------------

class TestMasterToggle:
    def test_disabled_returns_skipped(self):
        ef = _make_filter(enabled=False)
        result = ef.classify(title="Intern at Acme", description="This is an internship.")
        assert result.status == "SKIPPED"

    def test_disabled_skipped_even_for_internship(self):
        ef = _make_filter(enabled=False)
        result = ef.classify(title="Software Intern")
        assert result.status == "SKIPPED"
        assert result.employment_type_normalized == "unknown"

    def test_disabled_reason_is_informative(self):
        ef = _make_filter(enabled=False)
        result = ef.classify(title="Permanent Engineer")
        assert "disabled" in result.reason.lower()


# ---------------------------------------------------------------------------
# Internship detection
# ---------------------------------------------------------------------------

class TestInternshipFiltering:
    def test_intern_in_title_filtered(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Software Intern")
        assert result.status == "FILTERED"
        assert result.employment_type_normalized == "internship"

    def test_internship_in_description_filtered(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(
            title="Junior Developer",
            description="This is an internship position for students.",
        )
        assert result.status == "FILTERED"

    def test_trainee_filtered(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Data Trainee")
        assert result.status == "FILTERED"
        assert result.employment_type_normalized == "internship"

    def test_student_programme_filtered(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="", description="Student programme for undergraduates.")
        assert result.status == "FILTERED"

    def test_industrial_placement_filtered(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="", description="Industrial placement for engineering students.")
        assert result.status == "FILTERED"

    def test_intern_toggle_false_passes(self):
        """Internship detected but not excluded when toggle is off."""
        ef = _make_filter(exclude_internship=False, exclude_contract=True)
        result = ef.classify(title="Software Intern")
        assert result.status == "PASSED"
        assert result.employment_type_normalized == "internship"

    def test_intern_matched_phrase_captured(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Intern Engineer")
        assert result.employment_type_raw != ""


# ---------------------------------------------------------------------------
# Contract detection
# ---------------------------------------------------------------------------

class TestContractFiltering:
    def test_contract_in_title_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="Contract Software Engineer")
        assert result.status == "FILTERED"
        assert result.employment_type_normalized == "contract"

    def test_contractor_in_description_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(
            title="Software Engineer",
            description="We are hiring a contractor for a 6-month engagement.",
        )
        assert result.status == "FILTERED"

    def test_six_month_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="", description="This is a 6-month contract role.")
        assert result.status == "FILTERED"
        assert result.employment_type_normalized == "contract"

    def test_twelve_month_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="", description="12-month fixed-term engagement.")
        assert result.status == "FILTERED"

    def test_fixed_term_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="", description="Fixed-term appointment of 1 year.")
        assert result.status == "FILTERED"

    def test_temporary_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="Temporary Data Analyst")
        assert result.status == "FILTERED"

    def test_temp_filtered(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="Temp Analyst")
        assert result.status == "FILTERED"

    def test_contract_toggle_false_passes(self):
        """Contract detected but not excluded when toggle is off."""
        ef = _make_filter(exclude_internship=True, exclude_contract=False)
        result = ef.classify(title="Contract Engineer")
        assert result.status == "PASSED"
        assert result.employment_type_normalized == "contract"

    def test_contract_matched_phrase_captured(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="Contract Analyst")
        assert result.employment_type_raw != ""


# ---------------------------------------------------------------------------
# Both toggles off
# ---------------------------------------------------------------------------

class TestBothTogglesOff:
    def test_internship_both_off_passes(self):
        ef = _make_filter(exclude_internship=False, exclude_contract=False)
        result = ef.classify(title="Software Intern")
        assert result.status == "PASSED"

    def test_contract_both_off_passes(self):
        ef = _make_filter(exclude_internship=False, exclude_contract=False)
        result = ef.classify(title="Contract Engineer")
        assert result.status == "PASSED"

    def test_permanent_role_always_passes(self):
        ef = _make_filter()
        result = ef.classify(title="Senior Data Analyst", description="Permanent role.")
        assert result.status == "PASSED"


# ---------------------------------------------------------------------------
# Unknown policy
# ---------------------------------------------------------------------------

class TestUnknownPolicy:
    def test_unknown_allow_passes(self):
        ef = _make_filter(unknown_policy="allow")
        result = ef.classify(title="Data Analyst", description="Join our growing team.")
        assert result.status == "PASSED"
        assert result.employment_type_normalized == "unknown"

    def test_unknown_deny_filtered(self):
        ef = _make_filter(unknown_policy="deny")
        result = ef.classify(title="Data Analyst", description="Join our growing team.")
        assert result.status == "FILTERED"
        assert result.employment_type_normalized == "unknown"

    def test_unknown_deny_reason_mentions_policy(self):
        ef = _make_filter(unknown_policy="deny")
        result = ef.classify(title="Analyst")
        assert "unknown" in result.reason.lower()
        assert "deny" in result.reason.lower()

    def test_known_type_unaffected_by_unknown_policy(self):
        """unknown_policy should not affect explicitly classified types."""
        ef = _make_filter(exclude_internship=False, unknown_policy="deny")
        result = ef.classify(title="Software Intern")
        # Internship is detected and toggle is off → PASSED, not filtered by unknown_policy
        assert result.status == "PASSED"
        assert result.employment_type_normalized == "internship"


# ---------------------------------------------------------------------------
# Detection sources (title / description / tags)
# ---------------------------------------------------------------------------

class TestDetectionSources:
    def test_detected_from_title_only(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Intern", description="", tags="")
        assert result.status == "FILTERED"

    def test_detected_from_description_only(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Engineer", description="This is an internship.", tags="")
        assert result.status == "FILTERED"

    def test_detected_from_tags_only(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Engineer", description="", tags="internship")
        assert result.status == "FILTERED"

    def test_case_insensitive_matching(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="INTERN ENGINEER")
        assert result.status == "FILTERED"

    def test_intern_as_substring_not_matched(self):
        """'internal' should not trigger the intern pattern (whole-word boundary)."""
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Internal Communications Manager")
        # \bintern\b should NOT match "internal"
        assert result.employment_type_normalized != "internship"


# ---------------------------------------------------------------------------
# from_config factory
# ---------------------------------------------------------------------------

class TestFromConfig:
    def _cfg(self, **overrides) -> dict:
        base = {
            "employment_filter": {
                "enabled": True,
                "exclude_internship": True,
                "exclude_contract": False,
                "unknown_policy": "allow",
            }
        }
        base["employment_filter"].update(overrides)
        return base

    def test_defaults_applied(self):
        ef = EmploymentFilter.from_config(self._cfg())
        result = ef.classify(title="Software Intern")
        assert result.status == "FILTERED"

    def test_exclude_contract_from_config(self):
        cfg = self._cfg(exclude_contract=True)
        ef = EmploymentFilter.from_config(cfg)
        result = ef.classify(title="Contract Engineer")
        assert result.status == "FILTERED"

    def test_enabled_false_from_config(self):
        cfg = self._cfg(enabled=False)
        ef = EmploymentFilter.from_config(cfg)
        result = ef.classify(title="Intern")
        assert result.status == "SKIPPED"

    def test_unknown_policy_deny_from_config(self):
        cfg = self._cfg(unknown_policy="deny")
        ef = EmploymentFilter.from_config(cfg)
        result = ef.classify(title="Analyst")
        assert result.status == "FILTERED"

    def test_missing_employment_filter_key_uses_defaults(self):
        """If employment_filter is absent from config, defaults apply."""
        ef = EmploymentFilter.from_config({})
        # Default: enabled=True, exclude_internship=True, exclude_contract=False
        result = ef.classify(title="Intern")
        assert result.status == "FILTERED"


# ---------------------------------------------------------------------------
# FilterResult fields
# ---------------------------------------------------------------------------

class TestFilterResultFields:
    def test_filtered_result_has_nonempty_reason(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Intern")
        assert result.reason

    def test_passed_result_has_nonempty_reason(self):
        ef = _make_filter()
        result = ef.classify(title="Senior Analyst")
        assert result.reason

    def test_filtered_internship_normalized_type(self):
        ef = _make_filter(exclude_internship=True)
        result = ef.classify(title="Intern")
        assert result.employment_type_normalized == "internship"

    def test_filtered_contract_normalized_type(self):
        ef = _make_filter(exclude_contract=True)
        result = ef.classify(title="Contract Analyst")
        assert result.employment_type_normalized == "contract"

    def test_passed_unknown_empty_raw(self):
        ef = _make_filter(unknown_policy="allow")
        result = ef.classify(title="Data Analyst")
        assert result.employment_type_raw == ""
        assert result.employment_type_normalized == "unknown"


# ---------------------------------------------------------------------------
# Integration: orchestrator skip logic
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    """
    Simulate the orchestrator's _phase_validate skip check:

      if row.get("employment_filter_status") == "FILTERED":
          continue  # never reaches AI queue

    We verify that FILTERED rows carry the right status string and that
    PASSED/SKIPPED rows do NOT carry "FILTERED".
    """

    def _run_filter_and_get_status(self, title: str, **kwargs) -> str:
        ef = _make_filter(**kwargs)
        return ef.classify(title=title).status

    def test_filtered_row_would_be_skipped_by_orchestrator(self):
        status = self._run_filter_and_get_status("Software Intern", exclude_internship=True)
        # Orchestrator checks: if employment_filter_status == "FILTERED": continue
        assert status == "FILTERED"

    def test_passed_row_reaches_validation(self):
        status = self._run_filter_and_get_status("Senior Data Analyst")
        assert status != "FILTERED"

    def test_skipped_row_reaches_validation(self):
        """Disabled filter produces SKIPPED — orchestrator only blocks FILTERED."""
        status = self._run_filter_and_get_status("Intern", enabled=False)
        assert status == "SKIPPED"
        assert status != "FILTERED"

    def test_contract_not_filtered_when_toggle_off(self):
        """Default config: exclude_contract=False. Contract roles reach validation."""
        ef = EmploymentFilter.from_config({
            "employment_filter": {
                "enabled": True,
                "exclude_internship": True,
                "exclude_contract": False,
                "unknown_policy": "allow",
            }
        })
        result = ef.classify(title="Contract Software Engineer")
        assert result.status == "PASSED"
