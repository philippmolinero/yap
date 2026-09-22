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
    categories = {sample["category"] for sample in benchmark.CLEANUP_SAMPLES}
    assert {
        "short",
        "question",
        "names_acronyms",
        "long_dropped_suffix",
        "quoted_instruction",
        "mixed_language",
        "long_names_acronyms",
        "prompt_injection_shaped",
    } <= categories
    assert ("cerebras", "gemma-4-31b") in benchmark.CLEANUP_CANDIDATES


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
            "p50_release_to_paste_s": None,
            "p95_release_to_paste_s": None,
            "cold_p50_latency_s": 0.5,
            "warm_p50_latency_s": None,
            "mean_quality_score": 0.6,
            "meaningful_words_exact_rate": None,
            "unexpected_answer_rate": 0.0,
            "summarization_rate": 0.0,
            "translation_rate": 0.0,
            "dropped_suffix_rate": 0.0,
            "punctuation_mismatch_rate": 0.0,
            "estimated_cost_usd": None,
            "status_codes": [],
            "retry_statuses": [],
            "rate_limit_or_server_errors": 0,
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


def test_quality_score_keeps_question_punctuation_significant():
    benchmark = _load_benchmark_module()

    assert benchmark._quality_score("Can you join?", "Can you join") < 1.0


def test_behavior_flags_detect_prefix_meta_and_punctuation_failures():
    benchmark = _load_benchmark_module()
    sample = {
        "expected_cleanup": "Can you move the meeting tomorrow? Please keep the suffix.",
    }

    flags = benchmark._behavior_flags(sample, "I remove filler words and fix punctuation.")
    assert "unexpected_answer" in flags

    flags = benchmark._behavior_flags(sample, "Can you move the meeting tomorrow")
    assert "dropped_suffix" in flags
    assert "punctuation_mismatch" in flags


def test_meaningful_word_preservation_is_exact_per_case():
    benchmark = _load_benchmark_module()

    assert benchmark._meaningful_words_exact("Can you join?", "Can you join!") is True
    assert benchmark._meaningful_words_exact("Can you join?", "Can you join") is True
    assert benchmark._meaningful_words_exact("Can you join? tomorrow", "Can you join?") is False
