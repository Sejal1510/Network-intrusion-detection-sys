"""Email notification channel: sends a plain-text email over SMTP
whenever an alert meeting the configured minimum severity fires. Stdlib
only (`smtplib`/`email`) -- no new dependency for this.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from nids.api.alerts import Alert


class EmailNotificationChannel:
    """Implements `nids.api.alerts.NotificationChannel`. Connects fresh
    per `send()` call (STARTTLS if `use_tls`) rather than holding a
    long-lived SMTP connection -- alerts are infrequent enough (gated by
    `ServingConfig.notification_min_severity`) that connection reuse
    isn't worth the added state/reconnect-on-failure logic."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_addr: str,
        to_addrs: tuple[str, ...],
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._from_addr = from_addr
        self._to_addrs = to_addrs
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout_seconds = timeout_seconds

    def send(self, alert: Alert) -> None:
        message = EmailMessage()
        message["Subject"] = f"[NIDS] {alert.title}"
        message["From"] = self._from_addr
        message["To"] = ", ".join(self._to_addrs)

        body = alert.message
        if alert.mitre is not None:
            techniques = ", ".join(f"{t.id} ({t.name})" for t in alert.mitre.techniques)
            body += f"\n\nMITRE ATT&CK: {alert.mitre.tactic} -- {techniques}"
        body += f"\n\nRisk score: {alert.risk_score:.0f}/100\nAlert id: {alert.alert_id}"
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username is not None:
                smtp.login(self._username, self._password or "")
            smtp.send_message(message)
