"""Tests for benchmark corpus and latency summaries."""

import importlib.util
from pathlib import Path
import sys


def _load_benchmark_module():
    path = Path(__file__).parent.parent / "benchmarks" / "model_benchmark.py"
    spec = importlib.util.spec_from_file_location("yap_model_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_cleanup_corpus_has_fifty_cases_and_bilingual_coverage():
    benchmark = _load_benchmark_module()

    assert len(benchmark.CLEANUP_SAMPLES) == 50
    assert {sample["language"] for sample in benchmark.CLEANUP_SAMPLES} == {"en", "de"}
    assert all(sample["raw_cleanup"] != sample["expected_cleanup"] for sample in benchmark.CLEANUP_SAMPLES)


def test_summary_reports_p50_p95_quality_errors_and_fallbacks():
    benchmark = _load_benchmark_module()
    results = [
        benchmark.Result(
            stage="cleanup",
            provider="cerebras",
            model="gpt-oss-120b",
            sample_id="one",
            language="en",
            latency_s=0.2,
            output="clean",
            expected="clean",
            quality_score=1.0,
        ),
        benchmark.Result(
            stage="cleanup",
            provider="cerebras",
            model="gpt-oss-120b",
            sample_id="two",
            language="en",
            latency_s=0.8,
            output="raw",
            expected="clean",
            quality_score=0.2,
            fallback_reason="truncated_response",
        ),
        benchmark.Result(
            stage="cleanup",
            provider="cerebras",
            model="gpt-oss-120b",
            sample_id="three",
            language="en",
            latency_s=None,
            output="",
            error="network",
        ),
    ]

    summary = benchmark.summarize(results)

    assert summary == [
        {
            "stage": "cleanup",
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "samples": 3,
            "successes": 2,
            "errors": 1,
            "fallbacks": 1,
            "p50_latency_s": 0.5,
            "p95_latency_s": 0.77,
            "mean_quality_score": 0.6,
        }
    ]


def test_candidate_parser_keeps_provider_and_model_separate():
    benchmark = _load_benchmark_module()

    assert benchmark.parse_candidates(
        ["groq:openai/gpt-oss-120b", "cerebras:gpt-oss-120b"]
    ) == [
        ("groq", "openai/gpt-oss-120b"),
        ("cerebras", "gpt-oss-120b"),
    ]
