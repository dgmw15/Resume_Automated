"""Tests for ai/pipeline.py"""
import pytest
from ai.pipeline import get_prompts, select_track
from ai.prompts import (
    ANALYST_SYSTEM_PROMPT,
    ANALYST_USER_TEMPLATE,
    ENGINEER_SYSTEM_PROMPT,
    ENGINEER_USER_TEMPLATE,
)


class TestSelectTrack:
    def test_data_engineer_title(self):
        assert select_track("Data Engineer") == "engineer"

    def test_data_analyst_title(self):
        assert select_track("Data Analyst") == "analyst"

    def test_analytics_engineer_goes_to_engineer(self):
        assert select_track("Analytics Engineer") == "engineer"

    def test_business_analyst_goes_to_analyst(self):
        assert select_track("Business Analyst") == "analyst"

    def test_pipeline_engineer_goes_to_engineer(self):
        assert select_track("Pipeline Engineer") == "engineer"

    def test_ambiguous_defaults_to_analyst(self):
        assert select_track("Growth Specialist") == "analyst"

    def test_case_insensitive(self):
        assert select_track("DATA ENGINEER") == "engineer"
        assert select_track("data analyst") == "analyst"

    def test_mlops_goes_to_engineer(self):
        assert select_track("MLOps Engineer") == "engineer"

    def test_classifier_mode_falls_back_to_role_hint(self):
        # classifier mode not yet implemented — should still return a valid track
        result = select_track("Data Engineer", mode="classifier")
        assert result in ("analyst", "engineer")


class TestGetPrompts:
    def test_analyst_returns_analyst_prompts(self):
        sys, tmpl = get_prompts("analyst")
        assert sys == ANALYST_SYSTEM_PROMPT
        assert tmpl == ANALYST_USER_TEMPLATE

    def test_engineer_returns_engineer_prompts(self):
        sys, tmpl = get_prompts("engineer")
        assert sys == ENGINEER_SYSTEM_PROMPT
        assert tmpl == ENGINEER_USER_TEMPLATE

    def test_unknown_track_defaults_to_analyst(self):
        sys, tmpl = get_prompts("unknown")
        assert sys == ANALYST_SYSTEM_PROMPT

    def test_templates_contain_format_placeholders(self):
        _, tmpl = get_prompts("analyst")
        assert "{job_description}" in tmpl
        assert "{base_resume}" in tmpl

        _, tmpl = get_prompts("engineer")
        assert "{job_description}" in tmpl
        assert "{base_resume}" in tmpl
