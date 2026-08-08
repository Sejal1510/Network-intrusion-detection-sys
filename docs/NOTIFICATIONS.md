# Notification Integrations: Slack + Email

**Status: Milestone 12.** Closes `nids.api.alerts.NotificationChannel` —
a documented, unimplemented `Protocol` since Milestone 5 — by giving it
two real implementations and a dispatcher that calls them whenever an
alert crosses a configurable minimum severity. Chosen over threat-intel
enrichment (real value needs a live external API, fragile for an
offline/local demo) and further auth hardening (diminishing returns
right after Milestone 11) because it's the one gap that turns this
platform from "detects and logs" into "detects and acts" — the most
demoable capability left, and the lowest-risk to build: the `Alert`
dataclass and the `NotificationChannel` seam already existed, unchanged
by this milestone.

## Channels

`src/nids/api/notifications/`:

- `slack.py` — `SlackNotificationChannel`, posts to a Slack **incoming
  webhook** URL (`requests`, already a dependency — no new one). No
  Slack API token/OAuth scope involved.
- `email_channel.py` — `EmailNotificationChannel`, sends over SMTP
  (`smtplib`/`email`, stdlib only — no new dependency). Connects fresh
  per `send()` call rather than holding a long-lived connection; alerts
  are infrequent enough (severity-gated, see below) that connection
  reuse isn't worth the added reconnect-on-failure state.

Both implement `nids.api.alerts.NotificationChannel` (`send(alert:
Alert) -> None`) — a future Teams channel (or any other) is another
class implementing the same one-method interface, nothing else changes.

`nids.api.notifications.build_channels(config)` constructs whichever
channels `ServingConfig` has enough fields set for — Slack iff
`slack_webhook_url` is set; email iff `smtp_host`/`smtp_from_addr` and at
least one `smtp_to_addrs` entry are all set. Neither configured means an
empty list and the dispatcher never starts (see below) — zero behavior
change from before this milestone, same "unset = feature off" convention
`database_url`/`redis_url` already use.

| Config field | CLI flag | Env var |
|---|---|---|
| `slack_webhook_url` | `--slack-webhook-url` | `NIDS_SLACK_WEBHOOK_URL` |
| `smtp_host` | `--smtp-host` | `NIDS_SMTP_HOST` |
| `smtp_port` (587) | `--smtp-port` | `NIDS_SMTP_PORT` |
| `smtp_username` | `--smtp-username` | `NIDS_SMTP_USERNAME` |
| `smtp_password` | `--smtp-password` | `NIDS_SMTP_PASSWORD` |
| `smtp_from_addr` | `--smtp-from` | `NIDS_SMTP_FROM` |
| `smtp_to_addrs` | `--notify-email-to` (repeatable) | `NIDS_SMTP_TO` (comma-separated) |
| `smtp_use_tls` (on) | `--smtp-no-tls` | `NIDS_SMTP_USE_TLS=false` |
| `notification_min_severity` (`high`) | `--notification-min-severity` | `NIDS_NOTIFICATION_MIN_SEVERITY` |

## Severity gating

`nids.api.alerts.meets_min_severity(level, minimum)` — a second,
separate gate from `generate_alert`'s own `alert_threshold`. Not every
alert (dashboard/SOC-worthy) should page someone (human-interruptive):
`notification_min_severity` defaults to `"high"` so a freshly-configured
Slack/email channel isn't drowned in "low"/"medium" noise the moment
it's turned on.

## Dispatch: fire-and-forget, off the hot path

`generate_alert` runs inside `nids.api.pipeline.finish_record`, shared by
the synchronous `/predict` route, `/predict/batch`, and the async live
worker (`nids.api.worker`). Calling a Slack/SMTP endpoint *inline* there
would couple `/predict`'s response latency (and success) to an external
service's availability — a real risk, not a hypothetical one.

Instead, `finish_record` takes an optional `notify: Callable[[Alert],
None]` callback (same shape as its existing `ExplainPolicy` callable
pattern), invoked only when an alert is generated **and** meets
`notification_min_severity`. `pipeline.py` itself stays free of any
bus/asyncio import — it doesn't know or care what "notify" means; that's
decided entirely by the caller:

- `nids.api.app._notify` (used by `/predict`, `/predict/batch`) and
  `nids.api.worker.process_flow_message` both call
  `nids.api.notifications.publish.schedule_alert_publish(bus, loop,
  alert)`, which schedules a `MessageBus.publish("notifications", ...)`
  via `asyncio.run_coroutine_threadsafe` and **never awaits the result**.
  Safe from `/predict`'s synchronous route body (FastAPI runs it in a
  threadpool thread, not the event loop's own — `/predict` stays
  synchronous on purpose, since model inference is CPU-bound and making
  the route `async def` would block the loop instead of freeing it) and
  equally safe from the live worker's already-async path.
- `nids.api.notifications.dispatcher.run_notification_dispatcher` is the
  sole subscriber to the `"notifications"` bus channel, started as a
  background `asyncio` task in `nids.api.app._lifespan` — but only if at
  least one channel is configured. Publishing to a channel with zero
  subscribers is a documented no-op on both `MessageBus` implementations
  (`nids.api.bus`), so nothing needs to guard the *publish* side too.
- The dispatcher calls every channel's `send()` independently: one
  channel failing (a downed webhook, an SMTP auth error) is logged and
  counted (`nids_notifications_sent_total{channel,status}`), never
  raised, never stops the others.

**Runs in-process for both the `InMemoryBus` and `RedisBus` tiers** —
unlike the live worker, which Streams/consumer-groups make unsafe to
also run in-process under `RedisBus` (a second in-process consumer would
compete for the same group), `"notifications"` is plain Pub/Sub: every
subscriber gets every message, so there's no competing-consumer problem
here. The tradeoff this *does* introduce: if this API is ever run as
multiple replicas behind `RedisBus`, every replica's in-process
dispatcher subscribes independently, so every alert notifies once **per
replica**. Not a concern for this project's documented single-instance
deployment ([`docs/DEPLOYMENT.md`](DEPLOYMENT.md)), but a real limitation
worth knowing before ever running multiple replicas with notifications
configured — a future dedicated `python -m nids.api.notifications`
process (mirroring the live worker's own-process pattern) would fix it.

## Metrics

`nids_notifications_sent_total{channel, status}` (Counter) — `channel`
is the implementation's class name (`SlackNotificationChannel`,
`EmailNotificationChannel`), `status` is `success`/`failure`. See
[`docs/OBSERVABILITY.md`](OBSERVABILITY.md).

## Verified live, not just via pytest

A real server (`python -m nids.api`, trained run `rf-binary-verify`)
configured with a real `--slack-webhook-url` pointed at a local stdlib
`http.server` standing in for Slack (no real Slack workspace/credentials
available in this environment — the same honest substitution used for
Milestone 11's live checks). A real `POST /predict` and a real `POST
/predict/batch` (3 rows) both produced real outbound HTTP requests,
received on a separate process over a real socket, formatted exactly as
`SlackNotificationChannel.send` builds them; `GET /metrics` afterward
showed `nids_notifications_sent_total{channel="SlackNotificationChannel",
status="success"} 4` — one per triggered alert, no mocking involved
end-to-end except the destination URL.

## What's intentionally not here yet

- **No Teams channel.** Same interface, same seam — not built because
  two channels (Slack, email) already prove the pattern; a third is a
  small, low-risk follow-on, not new design.
- **No per-user notification preferences.** Channels are deployment-wide
  config (one Slack webhook, one SMTP recipient list), not something an
  individual analyst configures from the dashboard — no UI for this
  exists, and building one is a separate, larger scope decision.
- **No retry/backoff on a failed send.** A failure is logged, counted,
  and dropped — the alert itself is already durably in the database (if
  persistence is configured) and visible on `/history/alerts`
  regardless of whether the notification succeeded; the channel is a
  best-effort convenience layer on top, not the record of truth.
- **Multi-replica `RedisBus` duplicate notifications** — see the
  dispatch section above.
