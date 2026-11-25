import json
import math
import sqlite3
import time
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterator
from contextlib import contextmanager


@dataclass
class Span:
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: str
    started: float
    attributes: dict
    status: str = "ok"

    def skip(self, reason: str) -> None:
        self.status = "skipped"
        self.attributes["reason"] = reason


@dataclass
class Trace:
    trace_id: str
    method: str
    path: str
    started_at: str
    is_question: bool
    spans: list[dict] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_source: str = "unavailable"
    cost_usd: float | None = None
    model: str | None = None
    retrieved_chunks: int = 0
    root_span_id: str = ""


_active_trace: ContextVar[Trace | None] = ContextVar("active_trace", default=None)
_active_span: ContextVar[str | None] = ContextVar("active_span", default=None)


class Observability:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    is_question INTEGER NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    token_source TEXT NOT NULL,
                    cost_usd REAL,
                    model TEXT,
                    retrieved_chunks INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS spans (
                    trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                    span_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL,
                    status TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    PRIMARY KEY (trace_id, span_id)
                );
                CREATE INDEX IF NOT EXISTS traces_started_at_idx
                    ON traces(started_at DESC);
                CREATE INDEX IF NOT EXISTS spans_trace_id_idx
                    ON spans(trace_id);
                """
            )

    def start_trace(
        self, trace_id: str, method: str, path: str
    ) -> tuple[Trace, Token, Token]:
        trace = Trace(
            trace_id=trace_id,
            method=method,
            path=path,
            started_at=datetime.now(timezone.utc).isoformat(),
            is_question=path in {"/questions", "/ask"},
        )
        trace_token = _active_trace.set(trace)
        root_span_id = uuid.uuid4().hex[:16]
        trace.root_span_id = root_span_id
        span_token = _active_span.set(root_span_id)
        return trace, trace_token, span_token

    @contextmanager
    def span(self, name: str, attributes: dict | None = None) -> Iterator[Span]:
        trace = _active_trace.get()
        started = time.perf_counter()
        span = Span(
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=_active_span.get(),
            name=name,
            started_at=datetime.now(timezone.utc).isoformat(),
            started=started,
            attributes=dict(attributes or {}),
        )
        token = _active_span.set(span.span_id)
        try:
            yield span
        except BaseException as exc:
            span.status = "error"
            span.attributes["error_type"] = type(exc).__name__
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            _active_span.reset(token)
            if trace is not None:
                trace.spans.append({
                    "span_id": span.span_id,
                    "parent_span_id": span.parent_span_id,
                    "name": span.name,
                    "started_at": span.started_at,
                    "duration_ms": duration_ms,
                    "status": span.status,
                    "attributes": span.attributes,
                })

    def set_question_metrics(
        self,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        token_source: str,
        cost_usd: float | None,
        model: str,
        retrieved_chunks: int,
    ) -> None:
        trace = _active_trace.get()
        if trace is None:
            return
        trace.input_tokens = input_tokens
        trace.output_tokens = output_tokens
        trace.token_source = token_source
        trace.cost_usd = cost_usd
        trace.model = model
        trace.retrieved_chunks = retrieved_chunks

    def finish_trace(
        self,
        trace: Trace,
        status_code: int,
        duration_ms: float,
        context_token: Token,
        root_span_token: Token,
    ) -> None:
        trace.spans.append({
            "span_id": trace.root_span_id,
            "parent_span_id": None,
            "name": "http_request",
            "started_at": trace.started_at,
            "duration_ms": duration_ms,
            "status": "error" if status_code >= 400 else "ok",
            "attributes": {
                "method": trace.method,
                "path": trace.path,
                "status_code": status_code,
            },
        })
        try:
            with self._write_lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO traces (
                        trace_id, started_at, method, path, status_code, duration_ms,
                        is_question, input_tokens, output_tokens, token_source,
                        cost_usd, model, retrieved_chunks
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.trace_id,
                        trace.started_at,
                        trace.method,
                        trace.path,
                        status_code,
                        duration_ms,
                        int(trace.is_question),
                        trace.input_tokens,
                        trace.output_tokens,
                        trace.token_source,
                        trace.cost_usd,
                        trace.model,
                        trace.retrieved_chunks,
                    ),
                )
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO spans (
                        trace_id, span_id, parent_span_id, name, started_at,
                        duration_ms, status, attributes_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            trace.trace_id,
                            span["span_id"],
                            span["parent_span_id"],
                            span["name"],
                            span["started_at"],
                            span["duration_ms"],
                            span["status"],
                            json.dumps(span["attributes"], separators=(",", ":")),
                        )
                        for span in trace.spans
                    ],
                )
                connection.execute(
                    """
                    DELETE FROM traces WHERE trace_id IN (
                        SELECT trace_id FROM traces
                        ORDER BY started_at DESC LIMIT -1 OFFSET 10000
                    )
                    """
                )
        finally:
            _active_span.reset(root_span_token)
            _active_trace.reset(context_token)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, math.ceil(percentile * len(ordered)) - 1)
        return round(ordered[index], 2)

    def report(self, recent_limit: int = 30) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT duration_ms, status_code, is_question, input_tokens,
                       output_tokens, token_source, cost_usd
                FROM traces
                """
            ).fetchall()
            recent = connection.execute(
                """
                SELECT trace_id, started_at, method, path, status_code, duration_ms,
                       is_question, input_tokens, output_tokens, token_source,
                       cost_usd, model, retrieved_chunks
                FROM traces ORDER BY started_at DESC LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()

            traces = []
            for row in recent:
                item = dict(row)
                item["spans"] = [
                    {
                        "span_id": span["span_id"],
                        "parent_span_id": span["parent_span_id"],
                        "name": span["name"],
                        "duration_ms": round(span["duration_ms"], 2),
                        "status": span["status"],
                        "attributes": json.loads(span["attributes_json"]),
                    }
                    for span in connection.execute(
                        """
                        SELECT span_id, parent_span_id, name, duration_ms,
                               status, attributes_json
                        FROM spans WHERE trace_id = ? ORDER BY started_at
                        """,
                        (row["trace_id"],),
                    )
                ]
                traces.append(item)

        durations = [row["duration_ms"] for row in rows]
        questions = [row for row in rows if row["is_question"]]
        question_failures = sum(row["status_code"] >= 400 for row in questions)
        known_costs = [row["cost_usd"] for row in questions if row["cost_usd"] is not None]
        failed = sum(row["status_code"] >= 400 for row in rows)
        question_count = len(questions)
        return {
            "request_count": len(rows),
            "question_count": question_count,
            "error_rate": round(failed / len(rows), 4) if rows else 0,
            "question_error_rate": (
                round(question_failures / len(questions), 4) if questions else 0
            ),
            "latency_ms": {
                "p50": self._percentile(durations, 0.50),
                "p95": self._percentile(durations, 0.95),
            },
            "tokens": {
                "input": sum(row["input_tokens"] or 0 for row in questions),
                "output": sum(row["output_tokens"] or 0 for row in questions),
                "estimated_questions": sum(row["token_source"] == "estimated" for row in questions),
            },
            "cost": {
                "known_total_usd": round(sum(known_costs), 8),
                "known_average_per_question_usd": (
                    round(sum(known_costs) / len(known_costs), 8)
                    if known_costs else None
                ),
                "questions_with_known_cost": len(known_costs),
            },
            "traces": traces,
        }
