# Threat Intelligence Enrichment

**Status: Milestone 16.** Adds read-only IOC (indicator-of-compromise)
context to already-raised alerts by checking their `src_ip`/`dst_ip`
against two external reputation providers. Chosen over further auth
hardening and observability-UI surfacing after a full-codebase
reassessment (same pattern as prior milestones) because it was the last
of the four "Future endpoints" items named in [`docs/API.md`](API.md)
since Milestone 5 that hadn't been built — notifications (Milestone 12)
and rule-based detections (Milestone 14) already closed the other two;
multi-user auth/deployment closed as Milestone 11.

**Never influences detection.** `nids.api.risk`/`nids.api.alerts`/
`nids.api.rules` compute severity and fire alerts with zero awareness
this package exists. Enrichment only ever runs *after* an alert has
already been generated, and its only effect is extra context a dashboard
can display alongside — never instead of — the ML/rule verdict.

## Providers

`src/nids/api/threat_intel/`:

- `abuseipdb.py` — `AbuseIPDBProvider`, IP-reputation check against
  AbuseIPDB's `/v2/check` endpoint (`requests`, already a dependency —
  no new one). Its own `abuseConfidenceScore` (0-100) is used directly as
  `confidence`; bucketed into `malicious` (>=75), `suspicious` (>=25),
  `unknown` (never reported at all), else `benign`, with an explicit
  `benign` short-circuit when AbuseIPDB itself whitelists the address.
- `greynoise.py` — `GreyNoiseProvider`, GreyNoise's Community API tier
  (`/v3/community/{ip}`, no new dependency either). GreyNoise already
  returns a `classification` in almost exactly this vocabulary
  (`malicious`/`benign`/`unknown`, never `suspicious`) but no numeric
  confidence field, so `confidence` here is a fixed, documented mapping
  this codebase defines (90/10/0) rather than anything GreyNoise itself
  asserts a number for.

Both implement `nids.api.threat_intel.ThreatIntelProvider` (`lookup(indicator:
str) -> EnrichmentResult`) — a future third provider (e.g. VirusTotal) is
another class implementing the same one-method interface, nothing else
changes. `lookup` raises on any failure (network error, timeout, non-2xx,
malformed response) — "no exception" is the only success signal, mirroring
`nids.api.notifications.NotificationChannel`'s own contract.

`nids.api.threat_intel.build_providers(config)` constructs whichever
providers `ServingConfig` has an API key for — an app with neither key
set gets an empty list, and the enrichment dispatcher never starts (see
below): the same "unset = feature off, zero behavior change" convention
`nids.api.notifications.build_channels` already established.

| Config field | CLI flag | Env var |
|---|---|---|
| `abuseipdb_api_key` | `--abuseipdb-api-key` | `NIDS_ABUSEIPDB_API_KEY` |
| `greynoise_api_key` | `--greynoise-api-key` | `NIDS_GREYNOISE_API_KEY` |
| `enrichment_cache_ttl_seconds` (86400 = 24h) | `--enrichment-cache-ttl-seconds` | `NIDS_ENRICHMENT_CACHE_TTL_SECONDS` |

## Which indicators get looked up

`nids.api.threat_intel.extract_indicators(record)` pulls the deduped,
**routable IPv4** values out of a raw flow record's `src_ip`/`dst_ip` —
`is_routable_ipv4` explicitly excludes private (RFC1918), loopback,
link-local, multicast, reserved, and unspecified addresses, since
querying an external provider about e.g. `10.0.0.5` (a capture agent's
own LAN — the overwhelmingly common case for lab/demo traffic) would
just burn API quota on noise. IPv6 is out of scope for this milestone.

`src_ip`/`dst_ip` only ever exist when `nids.flows.aggregator.
FlowAggregator` produced the record (`source="agent"`, live capture) —
never for `source="api"` (`/predict`, `/predict/batch`), since NSL-KDD
has no IP field at all to have supplied one. `nids.api.pipeline.
persist_if_configured` threads them through into dedicated
`PredictionRecord.src_ip`/`.dst_ip` columns (not just inside the
`raw_record` JSON blob, which also carries them) so lookups by IP don't
need to parse JSON.

Enrichment is gated on an alert actually firing — it's investigative
context for something already flagged, not a check run against every
flow, the same "not every prediction, only the alert-worthy ones"
principle `nids.api.worker.explain_only_alert_worthy` already applies
for SHAP, applied here to conserve external provider rate limits instead
of compute.

## Caching

`ioc_enrichments` (`nids.api.store.IocEnrichmentRecord`) is the cache
itself, not a structure alongside one — unique on `(indicator, provider)`
so the same IP recurring across many predictions/alerts reuses one row
instead of accumulating a new one per occurrence. Deliberately not
foreign-keyed to `predictions`/`alerts`: an indicator's reputation is a
fact about the IP, not about any one flow that happened to involve it.
`nids.api.store.get_cached_enrichment` returns whatever's cached
regardless of freshness — the dispatcher (below) is the one place that
decides whether `expires_at` is still trusted, via
`enrichment_cache_ttl_seconds` (default 24h — IP reputation doesn't
meaningfully change minute-to-minute, so this defaults generously; the
point is avoiding repeated external lookups for the same indicator, not
real-time freshness).

## Dispatch: fire-and-forget, off the hot path

Mirrors [`docs/NOTIFICATIONS.md`](NOTIFICATIONS.md)'s dispatch shape
closely — same problem (a small set of interchangeable external
integrations, config-gated, individually non-fatal) has the same answer
twice:

- `nids.api.pipeline.finish_record` takes an optional `enrich:
  Callable[[list[str]], None]` callback (sibling of its existing
  `notify` callback), called at most once, only when at least one alert
  fired, with that record's routable indicators.
- `nids.api.app._enrich` (used by `/predict`, `/predict/batch`) and
  `nids.api.worker.process_flow_message` both call
  `nids.api.threat_intel.publish.schedule_enrichment_publish(bus, loop,
  indicators)`, which schedules a `MessageBus.publish("enrichment", ...)`
  via `asyncio.run_coroutine_threadsafe` and never awaits the result —
  safe from `/predict`'s synchronous threadpool thread and the live
  worker's own event-loop task alike.
- `nids.api.threat_intel.dispatcher.run_enrichment_dispatcher` is the
  sole subscriber to the `"enrichment"` bus channel, started as a
  background `asyncio` task in `nids.api.app._lifespan` — gated on
  *two* conditions rather than notifications' one: `threat_intel_providers`
  non-empty **and** a database configured (the cache needs somewhere to
  write to; notifications only publish outward and needs nothing
  persisted).

**One deliberate difference from the notification dispatcher:** each
provider call runs via `await asyncio.to_thread(provider.lookup,
indicator)`, not inline. The notification dispatcher blocking the shared
event loop for one `requests.post` is an accepted, low-volume tradeoff;
this dispatcher's caller is reached from *both* `/predict`'s threadpool
and the live worker's own event-loop task, and the live worker runs on
that exact loop — a blocking call here would delay every flow behind it,
not just this one. `asyncio.to_thread` needs no new dependency and keeps
every `ThreatIntelProvider` implementation a plain synchronous function.

One provider's failure (timeout, rate limit, outage) is logged and
counted, never raised, never stops the other provider or the indicator
loop — same reasoning `nids.api.notifications.dispatcher.dispatch_alert`
already documents.

## API

Both are login-required (`CurrentUserDep`), read-only, and return an
empty `items: []` list as a normal response — not an error — when a
prediction has no routable indicators at all or enrichment simply hasn't
completed yet:

- `GET /history/predictions/{prediction_id}/enrichment` — whatever's
  currently cached for that prediction's `src_ip`/`dst_ip`. 404 only if
  the prediction id doesn't exist.
- `GET /history/alerts/{alert_id}/enrichment` — thin convenience wrapper:
  resolves `alert.prediction_id`, then returns exactly what the route
  above would. An indicator's reputation is a property of the flow, not
  of the alert raised about it, so this never duplicates storage or
  logic — just the lookup path a dashboard already sitting on an alert
  row would otherwise need a second round trip for.

Response rows carry an `indicator_role` (`"src"`/`"dst"`), resolved
against *that* prediction's own `src_ip`/`dst_ip` at request time — the
cache row itself has no concept of role, since the same IP can be a
source in one flow and a destination in another. An indicator matching
both roles gets one row per role, never silently merged.

## Frontend

- `useAlertEnrichment(alertId, enabled)` (`frontend/src/hooks/
  useAlertEnrichment.ts`) — a `useQuery` that only runs once an alert
  row is expanded (`enabled`), and polls every 2s (`MAX_POLLS = 6`, ~12s)
  while `items` is still empty, since enrichment is dispatched
  asynchronously and may not exist yet the moment the row is opened.
  Stops polling as soon as results land, or after `MAX_POLLS` for alerts
  with no routable indicators at all (which will never produce a
  result).
- `ThreatIntelSection` (`frontend/src/components/common/
  ThreatIntelSection.tsx`) — renders one verdict pill per `(indicator,
  provider)` result, grouped by indicator, with explicit copy for the
  "checking" and "no indicators" states.
- `AlertSourceBadge` (`frontend/src/components/common/
  AlertSourceBadge.tsx`) — a small companion badge distinguishing
  ML-raised from signature/rule-raised alerts in the same expanded
  detail panel; added alongside this milestone's UI work since
  `AlertHistoryItem.source` was otherwise ambiguous once the detail
  panel started surfacing more per-alert metadata.
- `AlertRow` (`frontend/src/components/tables/AlertRow.tsx`) — alert rows
  are now expandable; expanding one reveals Detection (source badge +
  severity), MITRE ATT&CK, and the `ThreatIntelSection` above, side by
  side.

## Metrics

`nids_ioc_enrichment_lookups_total{provider, status}` (Counter) —
`status` is `success`/`failure`. Cache hits (no external call made) are
not counted here — this measures external provider usage, not cache
traffic. See [`docs/OBSERVABILITY.md`](OBSERVABILITY.md).

## Verified live, not just via pytest

A real `python -m nids.api` server, configured with `--enrichment-cache-ttl-seconds`
defaults and pointed at the persisted SQLite store, was exercised
directly: `GET /health` (200), a real `POST /predict` (200), `POST
/auth/login` (200), then `GET /history/alerts/{id}/enrichment` against a
real alert id (200, non-empty cached results), the same route against a
nonexistent alert id (404), and the same route again with no auth token
(401) — confirming the login-required gate and the not-found path both
behave independently of the happy path. `HEAD /health` (405) confirmed
routing wasn't accidentally loosened elsewhere while wiring the new
routes in.

## What's intentionally not here yet

- **No IPv6.** `is_routable_ipv4` treats any IPv6 literal as "not
  routable for us," not an error — a future milestone, not a bug.
- **No VirusTotal or other third provider.** Same interface, same seam
  as `nids.api.notifications`' own Slack/email precedent — two providers
  already prove the pattern; a third is a small, low-risk follow-on.
- **No cache eviction/pruning.** `ioc_enrichments` rows are overwritten
  in place on re-lookup (unique per indicator+provider) but never
  deleted — unbounded indicator churn over a very long-lived deployment
  would grow this table indefinitely. Not a concern at this project's
  current scale/deployment model.
- **No per-alert manual "re-check now."** A stale cached verdict is only
  refreshed the next time its TTL naturally expires and a new alert
  happens to reference the same indicator — there's no dashboard action
  to force an immediate re-lookup.
