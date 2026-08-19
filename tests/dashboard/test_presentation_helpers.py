from decimal import Decimal

from dashboard.charts import (
    baseline_candidate_scatter,
    breakdown_bar,
    case_delta_bar,
    comparison_bar,
    delta_distribution,
    metric_history,
    quality_latency_scatter,
)
from dashboard.components import format_delta, format_score


def test_component_formatters_handle_units_and_invalid_values():
    assert format_score(None) == "N/A"
    assert format_score(Decimal("0.1234")) == "0.123"
    assert format_score(0.125, "percent") == "12.5%"
    assert format_score(1500, "milliseconds") == "1.50 s"
    assert format_score(12, "count") == "12"
    assert format_score(0.25, "currency") == "$0.2500"
    assert format_delta(None) == "No baseline"
    assert format_delta(-0.125, "percent") == "-12.5 pp"
    assert format_delta(-0.5, "currency") == "-$0.5000"


def test_chart_factories_create_expected_trace_shapes():
    history_rows = [
        {"run_id": "selected", "started_at": "2024-01-01", "mean_score": 0.8, "run_name": "candidate", "run_type": "evaluation", "sample_count": 3},
        {"run_id": "baseline", "started_at": "2024-01-02", "mean_score": None, "run_name": "baseline", "run_type": "baseline", "sample_count": 3},
    ]
    assert len(metric_history(history_rows, "mrr", "selected", "baseline").data) == 1
    assert len(breakdown_bar([{"dimension_value": "A", "mean_score": 0.9, "sample_count": 2}]).data) == 1
    assert len(comparison_bar([{"metric_name": "mrr", "baseline_mean": 0.5, "candidate_mean": 0.7, "mean_delta": 0.2}]).data) == 3
    assert len(delta_distribution([{"delta": 0.1}, {"delta": None}]).data) == 1
    assert len(
        quality_latency_scatter(
            [{"run_id": "selected", "run_name": "run", "mean_score": 0.7, "p95_latency_ms": 100, "run_type": "evaluation"}],
            "mrr",
            selected_run_id="selected",
        ).data
    ) == 1
    assert len(
        baseline_candidate_scatter(
            [{"case_id": "av_0001", "baseline_score": 0.2, "candidate_score": 0.8, "delta": 0.6}],
            "mrr",
        ).data
    ) == 2
    assert len(
        case_delta_bar(
            [{"case_id": "av_0001", "delta": 0.4, "category": "quality", "question": "q"}],
            "mrr",
        ).data
    ) == 1
