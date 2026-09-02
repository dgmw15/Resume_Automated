from unittest.mock import MagicMock

from ai.critic import AtsCritic, CritiqueResult, _parse_critique
from ai.providers.base import ProviderResult


def test_parse_critique_well_formed():
    text = "COVERAGE: 85\nMISSING: airflow, kafka\nCONCERNS: none\nVERDICT: PASS\n"
    result = _parse_critique(text)
    assert result.coverage_pct == 85
    assert result.missing == ["airflow", "kafka"]
    assert result.concerns == "none"
    assert result.verdict == "PASS"


def test_parse_critique_none_missing():
    text = "COVERAGE: 100\nMISSING: none\nCONCERNS: none\nVERDICT: PASS"
    result = _parse_critique(text)
    assert result.missing == []


def test_parse_critique_malformed_output_falls_back_to_unknown():
    result = _parse_critique("The model ignored the format entirely.")
    assert result.verdict == "UNKNOWN"
    assert result.coverage_pct == 0
    assert result.missing == []


def test_parse_critique_clamps_out_of_range_coverage():
    result = _parse_critique("COVERAGE: 250\nMISSING: none\nCONCERNS: none\nVERDICT: FAIL")
    assert result.coverage_pct == 100


def test_ats_critic_calls_router_and_parses_result():
    router = MagicMock()
    router.generate.return_value = ProviderResult(
        text="COVERAGE: 60\nMISSING: sql\nCONCERNS: none\nVERDICT: WEAK",
        model="m", provider="anthropic", estimated_cost_usd=0.01,
    )
    critic = AtsCritic(router)

    result = critic.critique(
        job_description="Need SQL.",
        tailored_resume="No SQL mentioned.",
        idempotency_key="idem-critique",
        job_id="job-1",
    )

    assert isinstance(result, CritiqueResult)
    assert result.verdict == "WEAK"
    assert result.missing == ["sql"]
    router.generate.assert_called_once()
    call_kwargs = router.generate.call_args.kwargs
    assert call_kwargs["idempotency_key"] == "idem-critique"
    assert call_kwargs["job_id"] == "job-1"
