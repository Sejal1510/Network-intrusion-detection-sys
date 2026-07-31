"""Column schema and label taxonomy for the NSL-KDD dataset.

Reference: Tavallaee, M., Bagheri, E., Lu, W., & Ghorbani, A. (2009).
"A Detailed Analysis of the KDD CUP 99 Data Set." IEEE CISDA.
"""

from __future__ import annotations

FEATURE_COLUMNS: list[str] = [
    "duration",
    "protocol_type",
    "service",
    "flag",
    "src_bytes",
    "dst_bytes",
    "land",
    "wrong_fragment",
    "urgent",
    "hot",
    "num_failed_logins",
    "logged_in",
    "num_compromised",
    "root_shell",
    "su_attempted",
    "num_root",
    "num_file_creations",
    "num_shells",
    "num_access_files",
    "num_outbound_cmds",
    "is_host_login",
    "is_guest_login",
    "count",
    "srv_count",
    "serror_rate",
    "srv_serror_rate",
    "rerror_rate",
    "srv_rerror_rate",
    "same_srv_rate",
    "diff_srv_rate",
    "srv_diff_host_rate",
    "dst_host_count",
    "dst_host_srv_count",
    "dst_host_same_srv_rate",
    "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate",
    "dst_host_srv_diff_host_rate",
    "dst_host_serror_rate",
    "dst_host_srv_serror_rate",
    "dst_host_rerror_rate",
    "dst_host_srv_rerror_rate",
]
"""The 41 KDD/NSL-KDD connection features, in on-disk order."""

LABEL_COLUMN = "attack_type"
DIFFICULTY_COLUMN = "difficulty"

# On-disk row order: 41 features, then attack_type, then difficulty.
ALL_COLUMNS: list[str] = [*FEATURE_COLUMNS, LABEL_COLUMN, DIFFICULTY_COLUMN]

CATEGORICAL_COLUMNS: list[str] = ["protocol_type", "service", "flag"]

# Attack-type -> attack-category taxonomy used throughout the NSL-KDD literature.
# NSL-KDD's test split intentionally contains attack types absent from the train
# split (to evaluate generalization to unseen attacks), so this mapping is a
# superset of what appears in any single file.
ATTACK_CATEGORY: dict[str, str] = {
    "normal": "normal",
    # DoS
    "back": "dos",
    "land": "dos",
    "neptune": "dos",
    "pod": "dos",
    "smurf": "dos",
    "teardrop": "dos",
    "apache2": "dos",
    "udpstorm": "dos",
    "processtable": "dos",
    "mailbomb": "dos",
    "worm": "dos",
    # Probe
    "satan": "probe",
    "ipsweep": "probe",
    "nmap": "probe",
    "portsweep": "probe",
    "mscan": "probe",
    "saint": "probe",
    # R2L (remote to local)
    "guess_passwd": "r2l",
    "ftp_write": "r2l",
    "imap": "r2l",
    "phf": "r2l",
    "multihop": "r2l",
    "warezmaster": "r2l",
    "warezclient": "r2l",
    "spy": "r2l",
    "xlock": "r2l",
    "xsnoop": "r2l",
    "snmpguess": "r2l",
    "snmpgetattack": "r2l",
    "httptunnel": "r2l",
    "sendmail": "r2l",
    "named": "r2l",
    # U2R (user to root)
    "buffer_overflow": "u2r",
    "loadmodule": "u2r",
    "rootkit": "u2r",
    "perl": "u2r",
    "sqlattack": "u2r",
    "xterm": "u2r",
    "ps": "u2r",
}
