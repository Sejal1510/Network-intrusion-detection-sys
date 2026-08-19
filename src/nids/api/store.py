"""Persistence: SQLAlchemy-backed prediction/alert history, entirely
opt-in (see `nids.api.config.ServingConfig.database_url`) -- `None` (the
default) means zero DB writes and zero behavior change from Milestone 4.

Reuses SQLite the same way `nids.training`'s MLflow tracking already does
(`TrainingConfig.tracking_uri` defaults to `sqlite:///mlflow.db`); moving
to Postgres later is a `DATABASE_URL` change, not an application rewrite
-- see `docs/DATABASE.md` for the full justification.

Stores the dataclasses `nids.api.inference`/`explain`/`risk`/`mitre`/
`alerts` already produce -- this module adds no new domain logic, only a
place to put what already exists. Repository functions return plain,
already-detached dataclasses (`PredictionRecordView`/`AlertRecordView`),
never raw ORM instances, so callers never touch a closed SQLAlchemy
session by accident.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, joinedload, mapped_column, relationship
from sqlalchemy.types import JSON

from nids.api.alerts import Alert
from nids.api.explain import Explanation
from nids.api.inference import PredictionResult
from nids.api.mitre import MitreMapping
from nids.api.risk import RiskScore
from nids.api.threat_intel import EnrichmentResult


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class PredictionRecord(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    run_id: Mapped[str] = mapped_column(String)
    anomaly_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    label_column: Mapped[str] = mapped_column(String)
    prediction: Mapped[str] = mapped_column(String)
    probabilities: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    attack_category: Mapped[str | None] = mapped_column(String, nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_factors: Mapped[dict[str, float]] = mapped_column(JSON)
    mitre: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_record: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String, default="api")
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Only ever set for source="api" is impossible by construction -- NSL-KDD
    # (nids.data.schema.FEATURE_COLUMNS) has no IP field at all, so /predict
    # and /predict/batch never have one to pass. Set for source="agent" when
    # nids.flows.aggregator.FlowAggregator captured it (see its docstring).
    # Dedicated columns (not just fields inside raw_record, which also
    # carries them) so nids.api.threat_intel's enrichment lookup can query
    # by IP without parsing the JSON blob.
    src_ip: Mapped[str | None] = mapped_column(String, nullable=True)
    dst_ip: Mapped[str | None] = mapped_column(String, nullable=True)

    explanation: Mapped[ExplanationRecord | None] = relationship(
        back_populates="prediction", uselist=False, cascade="all, delete-orphan"
    )
    alerts: Mapped[list[AlertRecord]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class ExplanationRecord(Base):
    __tablename__ = "explanations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id"), unique=True)
    base_value: Mapped[float] = mapped_column(Float)
    top_features: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(String)

    prediction: Mapped[PredictionRecord] = relationship(back_populates="explanation")


class AlertRecord(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # == Alert.alert_id
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    level: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    risk_score: Mapped[float] = mapped_column(Float)
    attack_category: Mapped[str | None] = mapped_column(String, nullable=True)
    mitre: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String)
    device_id: Mapped[str | None] = mapped_column(String, nullable=True)

    prediction: Mapped[PredictionRecord] = relationship(back_populates="alerts")


class DeviceRecord(Base):
    """A paired live-capture agent (see `nids.api.agent_auth`,
    `nids.agent`). Only `credential_hash` is ever stored -- never the raw
    bearer token a device presents on connect."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String)
    credential_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    paired_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(default=False)


class AuditEventRecord(Base):
    """A security-relevant action: alert acknowledgement, successful/failed
    device pairing exchange (see `nids.api.history`, `nids.api.ingest`).
    `actor` is the client IP address that made the request -- there is no
    real user auth anywhere in this backend yet (see docs/API.md), so IP
    is the only identity this system can honestly record; a future auth
    layer replaces this column's meaning, not its shape. Rate-limit
    *rejections* (`nids.api.rate_limit`) are deliberately never written
    here -- they go to structured logs instead, so abuse noise can't grow
    this table unbounded."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    event_type: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)


class IocEnrichmentRecord(Base):
    """A cached threat-intel verdict for one (indicator, provider) pair
    (`nids.api.threat_intel`). This table *is* the enrichment cache, not
    a separate structure alongside it -- unique on (indicator, provider)
    so the same IP recurring across many predictions/alerts reuses one
    row instead of accumulating a new one per occurrence, which is the
    entire point of "prevent repeated external lookups." Deliberately not
    foreign-keyed to `predictions`/`alerts`: an indicator's reputation is
    a fact about the IP, not about any one flow that happened to involve
    it, and a lookup by `GET /history/predictions/{id}/enrichment` reads
    this table by IP value at request time rather than following a join."""

    __tablename__ = "ioc_enrichments"
    __table_args__ = (UniqueConstraint("indicator", "provider", name="uq_ioc_enrichment_indicator_provider"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    indicator: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    verdict: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON)
    looked_up_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class UserRecord(Base):
    """A login identity for the dashboard (see `nids.api.user_auth`).
    Only `password_hash` is ever stored -- never the raw password, same
    guarantee `DeviceRecord.credential_hash` already gives device
    credentials. `role` is a plain string (`"analyst"`/`"admin"`), not a
    normalized lookup table -- matching this codebase's existing
    preference for simple string enums (`severity`, `level`, `source`)
    over a third table for two fixed values."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class SessionRecord(Base):
    """A logged-in session token (see `nids.api.user_auth`) -- mirrors
    `DeviceRecord`'s `credential_hash`-only-ever-stored convention
    exactly. Uses a `revoked` flag rather than deleting the row on
    logout, matching `DeviceRecord.revoked`'s style: `authenticate_session`
    gets the identical hash-lookup-plus-flag-check shape
    `authenticate_device` already has, instead of a second "gone" concept
    (row absence) alongside it."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(default=False)


# ---------------------------------------------------------------------------
# Read models -- plain dataclasses, safe to use after the session that
# produced them has closed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExplanationView:
    base_value: float
    top_features: list[dict[str, Any]]
    summary: str


@dataclass(frozen=True)
class PredictionRecordView:
    id: str
    created_at: datetime
    run_id: str
    anomaly_run_id: str | None
    label_column: str
    prediction: str
    probabilities: dict[str, float] | None
    confidence: float | None
    attack_category: str | None
    anomaly_score: float | None
    is_anomaly: bool | None
    severity: str
    risk_score: float
    risk_factors: dict[str, float]
    mitre: dict[str, Any] | None
    raw_record: dict[str, Any]
    source: str
    device_id: str | None
    src_ip: str | None
    dst_ip: str | None
    explanation: ExplanationView | None


@dataclass(frozen=True)
class AlertRecordView:
    id: str
    prediction_id: str
    created_at: datetime
    level: str
    title: str
    message: str
    risk_score: float
    attack_category: str | None
    mitre: dict[str, Any] | None
    acknowledged: bool
    source: str
    device_id: str | None


@dataclass(frozen=True)
class IocEnrichmentView:
    id: str
    indicator: str
    provider: str
    verdict: str
    confidence: float
    raw_response: dict[str, Any]
    looked_up_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class DeviceRecordView:
    id: str
    name: str
    user_id: str | None
    paired_at: datetime
    last_seen_at: datetime | None
    revoked: bool


@dataclass(frozen=True)
class AuditEventView:
    id: str
    created_at: datetime
    event_type: str
    actor: str
    target_id: str | None
    detail: str | None


@dataclass(frozen=True)
class UserRecordView:
    """Deliberately excludes `password_hash` -- a read model safe to hand
    to any route/response by construction, never by remembering to strip
    it. `nids.api.user_auth` reaches the hash only through the private
    `_get_user_credentials_by_username` escape hatch below, for the one
    moment it's needed to verify a login attempt."""

    id: str
    username: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class SessionRecordView:
    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    revoked: bool


@dataclass(frozen=True)
class Page:
    items: list[Any]
    total: int
    limit: int
    offset: int


def _prediction_to_view(record: PredictionRecord) -> PredictionRecordView:
    explanation = (
        ExplanationView(
            base_value=record.explanation.base_value,
            top_features=record.explanation.top_features,
            summary=record.explanation.summary,
        )
        if record.explanation is not None
        else None
    )
    return PredictionRecordView(
        id=record.id,
        created_at=record.created_at,
        run_id=record.run_id,
        anomaly_run_id=record.anomaly_run_id,
        label_column=record.label_column,
        prediction=record.prediction,
        probabilities=record.probabilities,
        confidence=record.confidence,
        attack_category=record.attack_category,
        anomaly_score=record.anomaly_score,
        is_anomaly=record.is_anomaly,
        severity=record.severity,
        risk_score=record.risk_score,
        risk_factors=record.risk_factors,
        mitre=record.mitre,
        raw_record=record.raw_record,
        source=record.source,
        device_id=record.device_id,
        src_ip=record.src_ip,
        dst_ip=record.dst_ip,
        explanation=explanation,
    )


def _alert_to_view(record: AlertRecord) -> AlertRecordView:
    return AlertRecordView(
        id=record.id,
        prediction_id=record.prediction_id,
        created_at=record.created_at,
        level=record.level,
        title=record.title,
        message=record.message,
        risk_score=record.risk_score,
        attack_category=record.attack_category,
        mitre=record.mitre,
        device_id=record.device_id,
        acknowledged=record.acknowledged,
        source=record.source,
    )


def _device_to_view(record: DeviceRecord) -> DeviceRecordView:
    return DeviceRecordView(
        id=record.id,
        name=record.name,
        user_id=record.user_id,
        paired_at=record.paired_at,
        last_seen_at=record.last_seen_at,
        revoked=record.revoked,
    )


def _audit_event_to_view(record: AuditEventRecord) -> AuditEventView:
    return AuditEventView(
        id=record.id,
        created_at=record.created_at,
        event_type=record.event_type,
        actor=record.actor,
        target_id=record.target_id,
        detail=record.detail,
    )


def _user_to_view(record: UserRecord) -> UserRecordView:
    return UserRecordView(
        id=record.id, username=record.username, role=record.role, created_at=record.created_at
    )


def _session_to_view(record: SessionRecord) -> SessionRecordView:
    return SessionRecordView(
        id=record.id,
        user_id=record.user_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        revoked=record.revoked,
    )


def _mitre_to_dict(mitre: MitreMapping | None) -> dict[str, Any] | None:
    if mitre is None:
        return None
    return {
        "tactic": mitre.tactic,
        "techniques": [dataclasses.asdict(t) for t in mitre.techniques],
    }


# ---------------------------------------------------------------------------
# Engine setup
# ---------------------------------------------------------------------------


def create_db_engine(database_url: str) -> Engine:
    """Create the engine and ensure every table exists.

    `Base.metadata.create_all` (not Alembic) is deliberate for now -- there
    is no production data yet to migrate; see docs/DATABASE.md for when
    to introduce migration tooling instead.
    """
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def save_prediction(
    engine: Engine,
    result: PredictionResult,
    risk_score: RiskScore,
    mitre: MitreMapping | None,
    raw_record: dict[str, Any],
    run_id: str,
    label_column: str,
    anomaly_run_id: str | None = None,
    explanation: Explanation | None = None,
    source: str = "api",
    device_id: str | None = None,
    src_ip: str | None = None,
    dst_ip: str | None = None,
) -> str:
    """Persist one prediction (and its explanation, if given). Returns the
    new prediction's id."""
    record = PredictionRecord(
        run_id=run_id,
        anomaly_run_id=anomaly_run_id,
        label_column=label_column,
        prediction=str(result.prediction),
        probabilities=result.probabilities,
        confidence=result.confidence,
        attack_category=result.attack_category,
        anomaly_score=result.anomaly_score,
        is_anomaly=result.is_anomaly,
        severity=result.severity,
        risk_score=risk_score.score,
        risk_factors=risk_score.factors,
        mitre=_mitre_to_dict(mitre),
        raw_record=raw_record,
        source=source,
        device_id=device_id,
        src_ip=src_ip,
        dst_ip=dst_ip,
    )
    if explanation is not None:
        record.explanation = ExplanationRecord(
            base_value=explanation.base_value,
            top_features=[dataclasses.asdict(f) for f in explanation.top_features],
            summary=explanation.summary,
        )

    with Session(engine) as session:
        session.add(record)
        session.commit()
        return record.id


def save_alert(engine: Engine, prediction_id: str, alert: Alert, device_id: str | None = None) -> str:
    record = AlertRecord(
        id=alert.alert_id,
        prediction_id=prediction_id,
        created_at=alert.created_at,
        level=alert.level,
        title=alert.title,
        message=alert.message,
        risk_score=alert.risk_score,
        attack_category=alert.attack_category,
        mitre=_mitre_to_dict(alert.mitre),
        acknowledged=False,
        source=alert.source,
        device_id=device_id,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        return record.id


def upsert_enrichment(engine: Engine, result: EnrichmentResult, ttl_seconds: int) -> None:
    """Insert a fresh `ioc_enrichments` row for `(result.indicator,
    result.provider)`, or overwrite the existing one -- callers (see
    `nids.api.threat_intel.dispatcher`) only ever reach this after already
    deciding a lookup was needed (no fresh cached row), so "overwrite" is
    always the right behavior, never "keep the older one."""
    expires_at = result.looked_up_at + timedelta(seconds=ttl_seconds)
    with Session(engine) as session:
        existing = session.scalars(
            select(IocEnrichmentRecord).where(
                IocEnrichmentRecord.indicator == result.indicator,
                IocEnrichmentRecord.provider == result.provider,
            )
        ).one_or_none()
        if existing is not None:
            existing.verdict = result.verdict
            existing.confidence = result.confidence
            existing.raw_response = result.raw_response
            existing.looked_up_at = result.looked_up_at
            existing.expires_at = expires_at
        else:
            session.add(
                IocEnrichmentRecord(
                    indicator=result.indicator,
                    provider=result.provider,
                    verdict=result.verdict,
                    confidence=result.confidence,
                    raw_response=result.raw_response,
                    looked_up_at=result.looked_up_at,
                    expires_at=expires_at,
                )
            )
        session.commit()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_prediction(engine: Engine, prediction_id: str) -> PredictionRecordView | None:
    with Session(engine) as session:
        stmt = (
            select(PredictionRecord)
            .options(joinedload(PredictionRecord.explanation))
            .where(PredictionRecord.id == prediction_id)
        )
        record = session.scalars(stmt).unique().one_or_none()
        return _prediction_to_view(record) if record is not None else None


def get_alert(engine: Engine, alert_id: str) -> AlertRecordView | None:
    with Session(engine) as session:
        record = session.get(AlertRecord, alert_id)
        return _alert_to_view(record) if record is not None else None


def _enrichment_to_view(record: IocEnrichmentRecord) -> IocEnrichmentView:
    return IocEnrichmentView(
        id=record.id,
        indicator=record.indicator,
        provider=record.provider,
        verdict=record.verdict,
        confidence=record.confidence,
        raw_response=record.raw_response,
        looked_up_at=record.looked_up_at,
        expires_at=record.expires_at,
    )


def get_cached_enrichment(engine: Engine, indicator: str, provider: str) -> IocEnrichmentView | None:
    """Whatever's cached for `(indicator, provider)`, regardless of
    whether it's still fresh -- freshness (`expires_at` vs. now) is the
    caller's decision (see `nids.api.threat_intel.dispatcher`, which
    skips a re-lookup only when this *is* still fresh)."""
    with Session(engine) as session:
        record = session.scalars(
            select(IocEnrichmentRecord).where(
                IocEnrichmentRecord.indicator == indicator, IocEnrichmentRecord.provider == provider
            )
        ).one_or_none()
        return _enrichment_to_view(record) if record is not None else None


def list_enrichments_for_indicators(engine: Engine, indicators: list[str]) -> list[IocEnrichmentView]:
    """Every cached provider result (fresh or stale -- see
    `get_cached_enrichment`'s docstring for why staleness isn't filtered
    here either) for any of `indicators`. `nids.api.history`'s enrichment
    routes call this with a prediction's non-null `src_ip`/`dst_ip`."""
    if not indicators:
        return []
    with Session(engine) as session:
        records = session.scalars(
            select(IocEnrichmentRecord).where(IocEnrichmentRecord.indicator.in_(indicators))
        ).all()
        return [_enrichment_to_view(r) for r in records]


def list_predictions(
    engine: Engine,
    severity: str | None = None,
    attack_category: str | None = None,
    min_risk_score: float | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    device_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> Page:
    with Session(engine) as session:
        stmt = select(PredictionRecord)
        if severity is not None:
            stmt = stmt.where(PredictionRecord.severity == severity)
        if attack_category is not None:
            stmt = stmt.where(PredictionRecord.attack_category == attack_category)
        if min_risk_score is not None:
            stmt = stmt.where(PredictionRecord.risk_score >= min_risk_score)
        if start_date is not None:
            stmt = stmt.where(PredictionRecord.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(PredictionRecord.created_at <= end_date)
        if device_id is not None:
            stmt = stmt.where(PredictionRecord.device_id == device_id)

        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(PredictionRecord.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return Page(items=[_prediction_to_view(r) for r in rows], total=total, limit=limit, offset=offset)


def list_alerts(
    engine: Engine,
    level: str | None = None,
    acknowledged: bool | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    device_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> Page:
    with Session(engine) as session:
        stmt = select(AlertRecord)
        if level is not None:
            stmt = stmt.where(AlertRecord.level == level)
        if acknowledged is not None:
            stmt = stmt.where(AlertRecord.acknowledged == acknowledged)
        if start_date is not None:
            stmt = stmt.where(AlertRecord.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(AlertRecord.created_at <= end_date)
        if device_id is not None:
            stmt = stmt.where(AlertRecord.device_id == device_id)

        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(AlertRecord.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return Page(items=[_alert_to_view(r) for r in rows], total=total, limit=limit, offset=offset)


def acknowledge_alert(engine: Engine, alert_id: str) -> AlertRecordView | None:
    """Idempotent: acknowledging an already-acknowledged alert is a no-op
    that still returns its current (acknowledged) state."""
    with Session(engine) as session:
        record = session.get(AlertRecord, alert_id)
        if record is None:
            return None
        record.acknowledged = True
        session.commit()
        return _alert_to_view(record)


# ---------------------------------------------------------------------------
# Devices (see nids.api.agent_auth)
# ---------------------------------------------------------------------------


def register_device(
    engine: Engine, name: str, credential_hash: str, user_id: str | None = None
) -> DeviceRecordView:
    record = DeviceRecord(name=name, credential_hash=credential_hash, user_id=user_id)
    with Session(engine) as session:
        session.add(record)
        session.commit()
        return _device_to_view(record)


def get_device_by_credential_hash(engine: Engine, credential_hash: str) -> DeviceRecordView | None:
    with Session(engine) as session:
        record = session.scalars(
            select(DeviceRecord).where(DeviceRecord.credential_hash == credential_hash)
        ).one_or_none()
        return _device_to_view(record) if record is not None else None


def touch_device_last_seen(engine: Engine, device_id: str) -> None:
    with Session(engine) as session:
        record = session.get(DeviceRecord, device_id)
        if record is not None:
            record.last_seen_at = datetime.now(timezone.utc)
            session.commit()


def revoke_device(engine: Engine, device_id: str) -> DeviceRecordView | None:
    with Session(engine) as session:
        record = session.get(DeviceRecord, device_id)
        if record is None:
            return None
        record.revoked = True
        session.commit()
        return _device_to_view(record)


def list_devices(engine: Engine, limit: int = 20, offset: int = 0) -> Page:
    with Session(engine) as session:
        stmt = select(DeviceRecord)
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(DeviceRecord.paired_at.desc()).limit(limit).offset(offset)
        ).all()
        return Page(items=[_device_to_view(r) for r in rows], total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Audit trail (see AuditEventRecord above)
# ---------------------------------------------------------------------------


def record_audit_event(
    engine: Engine,
    event_type: str,
    actor: str,
    target_id: str | None = None,
    detail: str | None = None,
) -> AuditEventView:
    record = AuditEventRecord(event_type=event_type, actor=actor, target_id=target_id, detail=detail)
    with Session(engine) as session:
        session.add(record)
        session.commit()
        return _audit_event_to_view(record)


def list_audit_events(
    engine: Engine,
    event_type: str | None = None,
    actor: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> Page:
    with Session(engine) as session:
        stmt = select(AuditEventRecord)
        if event_type is not None:
            stmt = stmt.where(AuditEventRecord.event_type == event_type)
        if actor is not None:
            stmt = stmt.where(AuditEventRecord.actor == actor)
        if start_date is not None:
            stmt = stmt.where(AuditEventRecord.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(AuditEventRecord.created_at <= end_date)

        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(AuditEventRecord.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return Page(items=[_audit_event_to_view(r) for r in rows], total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# Users & sessions (see nids.api.user_auth)
# ---------------------------------------------------------------------------


def create_user(engine: Engine, username: str, password_hash: str, role: str) -> UserRecordView:
    record = UserRecord(username=username, password_hash=password_hash, role=role)
    with Session(engine) as session:
        session.add(record)
        session.commit()
        return _user_to_view(record)


def get_user_by_username(engine: Engine, username: str) -> UserRecordView | None:
    with Session(engine) as session:
        record = session.scalars(
            select(UserRecord).where(UserRecord.username == username)
        ).one_or_none()
        return _user_to_view(record) if record is not None else None


def get_user_by_id(engine: Engine, user_id: str) -> UserRecordView | None:
    with Session(engine) as session:
        record = session.get(UserRecord, user_id)
        return _user_to_view(record) if record is not None else None


def list_users(engine: Engine, limit: int = 20, offset: int = 0) -> Page:
    with Session(engine) as session:
        stmt = select(UserRecord)
        total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = session.scalars(
            stmt.order_by(UserRecord.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return Page(items=[_user_to_view(r) for r in rows], total=total, limit=limit, offset=offset)


def set_user_role(engine: Engine, user_id: str, role: str) -> UserRecordView | None:
    with Session(engine) as session:
        record = session.get(UserRecord, user_id)
        if record is None:
            return None
        record.role = role
        session.commit()
        return _user_to_view(record)


def _get_user_credentials_by_username(engine: Engine, username: str) -> tuple[str, UserRecordView] | None:
    """The one place `password_hash` briefly exists outside `UserRecord`
    itself -- used only by `nids.api.user_auth.authenticate_user` to
    verify a login attempt, immediately discarded after. Every other
    caller gets `UserRecordView`, which has no hash field at all."""
    with Session(engine) as session:
        record = session.scalars(
            select(UserRecord).where(UserRecord.username == username)
        ).one_or_none()
        if record is None:
            return None
        return record.password_hash, _user_to_view(record)


def create_session(engine: Engine, user_id: str, token_hash: str, expires_at: datetime) -> SessionRecordView:
    record = SessionRecord(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    with Session(engine) as session:
        session.add(record)
        session.commit()
        return _session_to_view(record)


def get_session_by_token_hash(engine: Engine, token_hash: str) -> SessionRecordView | None:
    with Session(engine) as session:
        record = session.scalars(
            select(SessionRecord).where(SessionRecord.token_hash == token_hash)
        ).one_or_none()
        return _session_to_view(record) if record is not None else None


def revoke_session_by_token_hash(engine: Engine, token_hash: str) -> None:
    with Session(engine) as session:
        record = session.scalars(
            select(SessionRecord).where(SessionRecord.token_hash == token_hash)
        ).one_or_none()
        if record is not None:
            record.revoked = True
            session.commit()
