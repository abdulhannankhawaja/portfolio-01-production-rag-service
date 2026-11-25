from app.observability import Observability


def test_report_aggregates_latency_cost_tokens_and_parented_spans(tmp_path):
    telemetry = Observability(tmp_path / "observability.sqlite3")
    trace, trace_token, root_token = telemetry.start_trace(
        "trace-one",
        "POST",
        "/questions",
    )
    with telemetry.span("retrieval", {"top_k": 5}) as retrieval:
        with telemetry.span("embedding") as embedding:
            pass
    telemetry.set_question_metrics(
        input_tokens=100,
        output_tokens=20,
        token_source="provider",
        cost_usd=0.001,
        model="gemini:test",
        retrieved_chunks=3,
    )
    telemetry.finish_trace(trace, 200, 42.0, trace_token, root_token)

    failed, failed_token, failed_root = telemetry.start_trace(
        "trace-two",
        "GET",
        "/documents/missing",
    )
    telemetry.finish_trace(failed, 503, 20.0, failed_token, failed_root)

    report = telemetry.report()
    assert report["request_count"] == 2
    assert report["question_count"] == 1
    assert report["error_rate"] == 0.5
    assert report["question_error_rate"] == 0
    assert report["latency_ms"] == {"p50": 20.0, "p95": 42.0}
    assert report["tokens"]["input"] == 100
    assert report["tokens"]["output"] == 20
    assert report["cost"]["known_average_per_question_usd"] == 0.001

    question_trace = next(item for item in report["traces"] if item["trace_id"] == "trace-one")
    spans = {item["name"]: item for item in question_trace["spans"]}
    assert spans["retrieval"]["parent_span_id"] == spans["http_request"]["span_id"]
    assert spans["embedding"]["parent_span_id"] == spans["retrieval"]["span_id"]
