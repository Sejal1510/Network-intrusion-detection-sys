"""`FlowAggregator`: turns a stream of `PacketEvent`s into raw records
satisfying `nids.data.schema.FEATURE_COLUMNS` -- the exact contract every
other input path (batch CSV, and eventually this project's own) already
targets. Pure and IO-free: it doesn't sniff packets or open files, so it
never needs root privileges or a real NIC to test.

**Honest, documented limitation**: several NSL-KDD features are
host/application-layer semantics from the original 1998 DARPA audit logs
(`hot`, `num_failed_logins`, `logged_in`, `num_compromised`, `root_shell`,
`su_attempted`, `num_root`, `num_file_creations`, `num_shells`,
`num_access_files`, `num_outbound_cmds`, `is_host_login`,
`is_guest_login`) that are not recoverable from network packets alone --
no packet-capture engineering can populate them. This is not a new
weakness: `docs/DATASET.md`'s "Known limitations" already flags several
of these same fields as near-constant/low-signal. They are fixed at `0`
here, documented, not silently guessed.

**This project's own windowing rules** (network-observable features):
`count`/`srv_count`/`serror_rate`/`srv_serror_rate`/`rerror_rate`/
`srv_rerror_rate`/`same_srv_rate`/`diff_srv_rate`/`srv_diff_host_rate` are
computed over connections that *ended* within the last `time_window`
seconds (default 2.0s, matching NSL-KDD's own convention) to the same
destination host; the `dst_host_*` features use the same definitions over
a per-destination-host window of the last `history_size` connections
(default 100) instead of a time window. This is a reasonable,
consistently-applied approximation of the original KDD Cup derivation
(which different published reproductions already implement slightly
differently), not a claimed bit-exact replication.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from nids.flows.schema import PacketEvent

# Well-known ports -> NSL-KDD-style service name. Anything unmapped falls
# back to "private" -- an authentic NSL-KDD vocabulary value (its own
# bucket for non-privileged/unrecognized ports), not an invented one.
# FeatureEngineer's OneHotEncoder(handle_unknown="ignore") already
# tolerates any service value never seen during training (see
# docs/FEATURE_PIPELINE.md) -- this map doesn't need to be exhaustive.
_SERVICE_MAP: dict[int, str] = {
    20: "ftp_data",
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "domain",
    67: "domain_u",
    68: "domain_u",
    79: "finger",
    80: "http",
    110: "pop_3",
    111: "sunrpc",
    113: "auth",
    119: "nntp",
    123: "ntp_u",
    143: "imap4",
    161: "snmp",
    179: "bgp",
    443: "http_443",
    445: "netbios_ssn",
    3306: "sql_net",
    3389: "http_443",
    8080: "http",
}
_DEFAULT_SERVICE = "private"

_S_ERROR = "s_error"
_R_ERROR = "r_error"
_NO_ERROR = "none"

_S_ERROR_FLAGS = frozenset({"S0", "S1"})
_R_ERROR_FLAGS = frozenset({"REJ", "RSTO", "RSTR"})


def _service_for(port: int) -> str:
    return _SERVICE_MAP.get(port, _DEFAULT_SERVICE)


def _error_bucket(flag: str) -> str:
    if flag in _S_ERROR_FLAGS:
        return _S_ERROR
    if flag in _R_ERROR_FLAGS:
        return _R_ERROR
    return _NO_ERROR


@dataclass
class _ConnectionState:
    protocol: str
    orig_src_ip: str
    orig_src_port: int
    orig_dst_ip: str
    orig_dst_port: int
    start_time: float
    last_time: float
    src_bytes: int = 0
    dst_bytes: int = 0
    wrong_fragment: int = 0
    urgent: int = 0
    saw_syn: bool = False
    saw_synack: bool = False
    saw_fin_orig: bool = False
    saw_fin_resp: bool = False
    saw_rst: bool = False
    rst_by_originator: bool = False


@dataclass(frozen=True)
class _CompletedConnection:
    end_time: float
    dst_ip: str
    dst_port: int
    service: str
    src_port: int
    error_bucket: str


def _rate(entries: list[_CompletedConnection], matches: int) -> float:
    return matches / len(entries) if entries else 0.0


def _count_matching(entries: list[_CompletedConnection], **fields: object) -> int:
    return sum(
        1 for e in entries if all(getattr(e, key) == value for key, value in fields.items())
    )


class FlowAggregator:
    """Fed one `PacketEvent` at a time (`process_packet`); periodically
    call `flush_idle(now)` (e.g. every second or two from the capture
    loop) to emit records for connections that have gone quiet -- most
    connections, especially UDP/ICMP and any TCP connection that isn't
    cleanly torn down, only ever complete this way."""

    def __init__(self, time_window: float = 2.0, history_size: int = 100, idle_timeout: float = 2.0):
        self._time_window = time_window
        self._idle_timeout = idle_timeout
        self._history_size = history_size

        self._connections: dict[tuple, _ConnectionState] = {}
        self._recent: deque[_CompletedConnection] = deque()
        self._host_history: dict[str, deque[_CompletedConnection]] = {}
        self._service_history: dict[str, deque[_CompletedConnection]] = {}

    def process_packet(self, pkt: PacketEvent) -> dict | None:
        fwd_key = (pkt.src_ip, pkt.src_port, pkt.dst_ip, pkt.dst_port, pkt.protocol)
        rev_key = (pkt.dst_ip, pkt.dst_port, pkt.src_ip, pkt.src_port, pkt.protocol)

        if fwd_key in self._connections:
            key, state, forward = fwd_key, self._connections[fwd_key], True
        elif rev_key in self._connections:
            key, state, forward = rev_key, self._connections[rev_key], False
        else:
            key = fwd_key
            state = _ConnectionState(
                protocol=pkt.protocol,
                orig_src_ip=pkt.src_ip,
                orig_src_port=pkt.src_port,
                orig_dst_ip=pkt.dst_ip,
                orig_dst_port=pkt.dst_port,
                start_time=pkt.timestamp,
                last_time=pkt.timestamp,
            )
            self._connections[key] = state
            forward = True

        state.last_time = pkt.timestamp
        if forward:
            state.src_bytes += pkt.length
        else:
            state.dst_bytes += pkt.length
        if pkt.fragmented:
            state.wrong_fragment += 1
        if "U" in pkt.tcp_flags:
            state.urgent += 1

        if pkt.protocol == "tcp":
            is_syn = "S" in pkt.tcp_flags and "A" not in pkt.tcp_flags
            is_synack = "S" in pkt.tcp_flags and "A" in pkt.tcp_flags
            is_fin = "F" in pkt.tcp_flags
            is_rst = "R" in pkt.tcp_flags

            if forward and is_syn:
                state.saw_syn = True
            if not forward and is_synack:
                state.saw_synack = True
            if forward and is_fin:
                state.saw_fin_orig = True
            if not forward and is_fin:
                state.saw_fin_resp = True
            if is_rst:
                state.saw_rst = True
                state.rst_by_originator = forward

            if state.saw_rst or (state.saw_syn and (state.saw_fin_orig or state.saw_fin_resp)):
                del self._connections[key]
                return self._finalize(state)

        return None

    def flush_idle(self, now: float) -> list[dict]:
        """Finalize every connection that hasn't seen a packet in
        `idle_timeout` seconds. Call periodically -- most flows,
        especially UDP/ICMP, only ever complete this way."""
        stale_keys = [
            key
            for key, state in self._connections.items()
            if now - state.last_time >= self._idle_timeout
        ]
        records = []
        for key in stale_keys:
            state = self._connections.pop(key)
            records.append(self._finalize(state))
        return records

    def _classify_flag(self, state: _ConnectionState) -> str:
        if state.protocol != "tcp":
            if state.src_bytes > 0 and state.dst_bytes > 0:
                return "SF"
            return "S0"  # sent, no reply -- reused loosely for non-TCP protocols

        if not state.saw_syn:
            return "OTH"  # mid-stream capture, no SYN observed
        if state.saw_rst and not state.saw_synack:
            return "REJ"
        if state.saw_rst and state.saw_synack:
            return "RSTO" if state.rst_by_originator else "RSTR"
        if state.saw_synack and (state.saw_fin_orig or state.saw_fin_resp):
            return "SF"
        if state.saw_synack:
            return "S1"  # established, still open when we gave up
        if state.saw_fin_orig:
            return "SH"  # SYN then FIN, no reply
        return "S0"  # SYN sent, no reply at all

    def _finalize(self, state: _ConnectionState) -> dict:
        host = state.orig_dst_ip
        service = _service_for(state.orig_dst_port)
        src_port = state.orig_src_port
        flag = self._classify_flag(state)
        error_bucket = _error_bucket(flag)
        current = _CompletedConnection(
            end_time=state.last_time,
            dst_ip=host,
            dst_port=state.orig_dst_port,
            service=service,
            src_port=src_port,
            error_bucket=error_bucket,
        )

        self._trim_time_window(current.end_time)

        # -- same-host, last `time_window` seconds --
        host_recent = [c for c in self._recent if c.dst_ip == host]
        count_window = [*host_recent, current]
        count = len(count_window)
        srv_window = [c for c in count_window if c.service == service]
        srv_count = len(srv_window)
        same_srv_rate = srv_count / count if count else 0.0

        service_recent_any_host = [c for c in self._recent if c.service == service]
        srv_diff_any_host_window = [*service_recent_any_host, current]

        # -- last `history_size` connections to the same destination host --
        host_hist = list(self._host_history.get(host, deque()))
        host_hist_window = [*host_hist, current]
        dst_host_count = len(host_hist_window)
        dst_host_srv_window = [c for c in host_hist_window if c.service == service]
        dst_host_srv_count = len(dst_host_srv_window)
        dst_host_same_srv_rate = dst_host_srv_count / dst_host_count if dst_host_count else 0.0

        svc_hist = list(self._service_history.get(service, deque()))
        svc_hist_window = [*svc_hist, current]

        record = {
            "duration": state.last_time - state.start_time,
            "protocol_type": state.protocol,
            "service": service,
            "flag": flag,
            "src_bytes": state.src_bytes,
            "dst_bytes": state.dst_bytes,
            "land": 1 if (state.orig_src_ip == host and src_port == state.orig_dst_port) else 0,
            "wrong_fragment": state.wrong_fragment,
            "urgent": state.urgent,
            "hot": 0,
            "num_failed_logins": 0,
            "logged_in": 0,
            "num_compromised": 0,
            "root_shell": 0,
            "su_attempted": 0,
            "num_root": 0,
            "num_file_creations": 0,
            "num_shells": 0,
            "num_access_files": 0,
            "num_outbound_cmds": 0,
            "is_host_login": 0,
            "is_guest_login": 0,
            "count": count,
            "srv_count": srv_count,
            "serror_rate": _rate(count_window, _count_matching(count_window, error_bucket=_S_ERROR)),
            "srv_serror_rate": _rate(srv_window, _count_matching(srv_window, error_bucket=_S_ERROR)),
            "rerror_rate": _rate(count_window, _count_matching(count_window, error_bucket=_R_ERROR)),
            "srv_rerror_rate": _rate(srv_window, _count_matching(srv_window, error_bucket=_R_ERROR)),
            "same_srv_rate": same_srv_rate,
            "diff_srv_rate": 1.0 - same_srv_rate,
            "srv_diff_host_rate": _rate(
                srv_diff_any_host_window,
                sum(1 for c in srv_diff_any_host_window if c.dst_ip != host),
            ),
            "dst_host_count": dst_host_count,
            "dst_host_srv_count": dst_host_srv_count,
            "dst_host_same_srv_rate": dst_host_same_srv_rate,
            "dst_host_diff_srv_rate": 1.0 - dst_host_same_srv_rate,
            "dst_host_same_src_port_rate": _rate(
                host_hist_window, sum(1 for c in host_hist_window if c.src_port == src_port)
            ),
            "dst_host_srv_diff_host_rate": _rate(
                svc_hist_window, sum(1 for c in svc_hist_window if c.dst_ip != host)
            ),
            "dst_host_serror_rate": _rate(
                host_hist_window, _count_matching(host_hist_window, error_bucket=_S_ERROR)
            ),
            "dst_host_srv_serror_rate": _rate(
                dst_host_srv_window, _count_matching(dst_host_srv_window, error_bucket=_S_ERROR)
            ),
            "dst_host_rerror_rate": _rate(
                host_hist_window, _count_matching(host_hist_window, error_bucket=_R_ERROR)
            ),
            "dst_host_srv_rerror_rate": _rate(
                dst_host_srv_window, _count_matching(dst_host_srv_window, error_bucket=_R_ERROR)
            ),
        }

        self._record_history(current)
        return record

    def _trim_time_window(self, now: float) -> None:
        while self._recent and now - self._recent[0].end_time > self._time_window:
            self._recent.popleft()

    def _record_history(self, entry: _CompletedConnection) -> None:
        self._recent.append(entry)
        self._host_history.setdefault(entry.dst_ip, deque(maxlen=self._history_size)).append(entry)
        self._service_history.setdefault(entry.service, deque(maxlen=self._history_size)).append(entry)
