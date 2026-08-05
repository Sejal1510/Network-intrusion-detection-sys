import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nids.api.logging_config import JsonFormatter, RequestLoggingMiddleware, setup_logging


def _make_record(level=logging.INFO, message="hello %s", args=("world",), exc_info=None):
    return logging.LogRecord(
        name="nids.api.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=exc_info,
    )


def test_json_formatter_produces_valid_json_with_level_logger_and_message():
    formatter = JsonFormatter()
    payload = json.loads(formatter.format(_make_record()))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "nids.api.test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_json_formatter_includes_exception_field_when_exc_info_present():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record(message="failed", args=(), exc_info=sys.exc_info())
    payload = json.loads(formatter.format(record))
    assert "boom" in payload["exception"]


@pytest.fixture(autouse=True)
def _reset_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_setup_logging_defaults_to_text_formatter():
    setup_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_configures_json_formatter_when_requested():
    setup_logging(json_format=True)
    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_setup_logging_sets_root_logger_level():
    setup_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_request_logging_middleware_logs_method_path_status_and_duration(caplog):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="nids.api.request"):
        response = client.get("/ping")

    assert response.status_code == 200
    # Filter to our own logger -- caplog.records isn't scoped to the
    # "logger=" argument above, it captures everything that reaches the
    # root logger's handlers (e.g. httpx's own "HTTP Request" INFO log
    # from TestClient), so an unfiltered length check is order-dependent
    # on what other loggers happen to be enabled this session.
    records = [r for r in caplog.records if r.name == "nids.api.request"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "GET" in message
    assert "/ping" in message
    assert "200" in message
