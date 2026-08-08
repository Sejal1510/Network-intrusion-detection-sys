import smtplib
from datetime import datetime, timezone
from typing import ClassVar

import pytest

from nids.api.alerts import Alert
from nids.api.bus import InMemoryBus
from nids.api.config import ServingConfig
from nids.api.metrics import create_metrics
from nids.api.notifications import build_channels
from nids.api.notifications.dispatcher import dispatch_alert, run_notification_dispatcher
from nids.api.notifications.email_channel import EmailNotificationChannel
from nids.api.notifications.publish import schedule_alert_publish
from nids.api.notifications.slack import SlackNotificationChannel


def _alert(level: str = "critical") -> Alert:
    return Alert(
        alert_id="alert-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        level=level,
        title=f"{level.capitalize()} risk detected",
        message="Critical risk activity detected (score 95/100).",
        risk_score=95.0,
        attack_category="dos",
        mitre=None,
        source="api",
    )


class _RecordingChannel:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent: list[Alert] = []

    def send(self, alert: Alert) -> None:
        if self.fail:
            raise RuntimeError("channel unavailable")
        self.sent.append(alert)


# --- SlackNotificationChannel ---------------------------------------------


def test_slack_channel_posts_formatted_text(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("nids.api.notifications.slack.requests.post", fake_post)

    channel = SlackNotificationChannel("https://hooks.slack.example/T000/B000/xxx")
    channel.send(_alert())

    assert captured["url"] == "https://hooks.slack.example/T000/B000/xxx"
    assert "Critical risk activity detected" in captured["json"]["text"]
    assert captured["timeout"] == 5.0


def test_slack_channel_raises_on_http_error(monkeypatch):
    class FailingResponse:
        def raise_for_status(self):
            raise RuntimeError("500 Server Error")

    monkeypatch.setattr(
        "nids.api.notifications.slack.requests.post", lambda *a, **kw: FailingResponse()
    )

    channel = SlackNotificationChannel("https://hooks.slack.example/T000/B000/xxx")
    with pytest.raises(RuntimeError):
        channel.send(_alert())


# --- EmailNotificationChannel ----------------------------------------------


class _FakeSMTP:
    instances: ClassVar[list["_FakeSMTP"]] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_args = None
        self.sent_message = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_message = message


def test_email_channel_sends_via_smtp(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    channel = EmailNotificationChannel(
        host="smtp.example.com",
        port=587,
        from_addr="nids@example.com",
        to_addrs=("soc@example.com", "oncall@example.com"),
        username="nids",
        password="secret",
    )
    channel.send(_alert())

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.started_tls is True
    assert smtp.login_args == ("nids", "secret")
    assert smtp.sent_message["To"] == "soc@example.com, oncall@example.com"
    assert "Critical risk detected" in smtp.sent_message["Subject"]


def test_email_channel_skips_login_when_no_username(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    channel = EmailNotificationChannel(
        host="smtp.example.com", port=25, from_addr="nids@example.com", to_addrs=("soc@example.com",)
    )
    channel.send(_alert())

    assert _FakeSMTP.instances[0].login_args is None


def test_email_channel_skips_starttls_when_disabled(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    channel = EmailNotificationChannel(
        host="smtp.example.com",
        port=25,
        from_addr="nids@example.com",
        to_addrs=("soc@example.com",),
        use_tls=False,
    )
    channel.send(_alert())

    assert _FakeSMTP.instances[0].started_tls is False


# --- build_channels ----------------------------------------------------------


def test_build_channels_empty_when_nothing_configured():
    config = ServingConfig(run_id="test-run")
    assert build_channels(config) == []


def test_build_channels_includes_slack_when_webhook_set():
    config = ServingConfig(run_id="test-run", slack_webhook_url="https://hooks.slack.example/x")
    channels = build_channels(config)
    assert len(channels) == 1
    assert isinstance(channels[0], SlackNotificationChannel)


def test_build_channels_includes_email_only_when_fully_configured():
    incomplete = ServingConfig(run_id="test-run", smtp_host="smtp.example.com")
    assert build_channels(incomplete) == []

    complete = ServingConfig(
        run_id="test-run",
        smtp_host="smtp.example.com",
        smtp_from_addr="nids@example.com",
        smtp_to_addrs=("soc@example.com",),
    )
    channels = build_channels(complete)
    assert len(channels) == 1
    assert isinstance(channels[0], EmailNotificationChannel)


def test_build_channels_includes_both_when_both_configured():
    config = ServingConfig(
        run_id="test-run",
        slack_webhook_url="https://hooks.slack.example/x",
        smtp_host="smtp.example.com",
        smtp_from_addr="nids@example.com",
        smtp_to_addrs=("soc@example.com",),
    )
    assert len(build_channels(config)) == 2


# --- dispatcher --------------------------------------------------------------


async def test_dispatch_alert_calls_every_channel():
    ok_a, ok_b = _RecordingChannel(), _RecordingChannel()
    await dispatch_alert(_alert(), [ok_a, ok_b])

    assert ok_a.sent == [_alert()]
    assert ok_b.sent == [_alert()]


async def test_dispatch_alert_one_channel_failing_does_not_stop_others():
    failing, ok = _RecordingChannel(fail=True), _RecordingChannel()
    await dispatch_alert(_alert(), [failing, ok])

    assert ok.sent == [_alert()]


async def test_dispatch_alert_records_metrics_for_success_and_failure():
    metrics = create_metrics()
    failing, ok = _RecordingChannel(fail=True), _RecordingChannel()

    await dispatch_alert(_alert(), [failing, ok], metrics)

    assert metrics.notifications_sent_total.labels(channel="_RecordingChannel", status="success")._value.get() == 1
    assert metrics.notifications_sent_total.labels(channel="_RecordingChannel", status="failure")._value.get() == 1


async def test_run_notification_dispatcher_consumes_published_alerts():
    bus = InMemoryBus()
    channel = _RecordingChannel()

    import asyncio

    from nids.api.notifications.publish import _publish_alert

    task = asyncio.create_task(run_notification_dispatcher(bus, [channel]))
    try:
        # Give the dispatcher a chance to subscribe before publishing --
        # InMemoryBus is real Pub/Sub: a publish before subscribe is lost.
        await asyncio.sleep(0.05)
        await _publish_alert(bus, _alert())
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(channel.sent) == 1
    assert channel.sent[0].alert_id == "alert-1"


# --- schedule_alert_publish / end-to-end via a real event loop --------------


async def test_schedule_alert_publish_delivers_to_subscriber():
    import asyncio

    bus = InMemoryBus()
    loop = asyncio.get_running_loop()

    async def collect_one():
        async for message in bus.subscribe("notifications"):
            return message

    subscriber = asyncio.create_task(collect_one())
    await asyncio.sleep(0.05)

    schedule_alert_publish(bus, loop, _alert())

    message = await asyncio.wait_for(subscriber, timeout=1.0)
    assert message["alert_id"] == "alert-1"
