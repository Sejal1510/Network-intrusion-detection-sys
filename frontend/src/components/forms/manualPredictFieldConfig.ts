/**
 * Declarative field list for the Manual Predict form -- field-for-field,
 * nids.data.schema.FEATURE_COLUMNS (41 fields, on-disk order). Grouped
 * for readability only; the group boundaries carry no meaning to the API.
 */

export type FieldKind = "select" | "text-suggest" | "number"

export interface FieldConfig {
  name: string
  label: string
  group: string
  kind: FieldKind
  defaultValue: string | number
  options?: string[]
}

const PROTOCOL_TYPES = ["tcp", "udp", "icmp"]
const FLAGS = ["SF", "S0", "S1", "S2", "S3", "REJ", "RSTR", "RSTO", "RSTOS0", "SH", "OTH"]
const COMMON_SERVICES = [
  "http",
  "ftp",
  "ftp_data",
  "smtp",
  "telnet",
  "ssh",
  "domain_u",
  "private",
  "finger",
  "eco_i",
  "ecr_i",
  "other",
  "pop_3",
  "auth",
  "urp_i",
]

const BASIC: FieldConfig[] = [
  { name: "duration", label: "Duration (s)", group: "Basic", kind: "number", defaultValue: 0 },
  {
    name: "protocol_type",
    label: "Protocol",
    group: "Basic",
    kind: "select",
    defaultValue: "tcp",
    options: PROTOCOL_TYPES,
  },
  {
    name: "service",
    label: "Service",
    group: "Basic",
    kind: "text-suggest",
    defaultValue: "http",
    options: COMMON_SERVICES,
  },
  {
    name: "flag",
    label: "Flag",
    group: "Basic",
    kind: "select",
    defaultValue: "SF",
    options: FLAGS,
  },
  { name: "src_bytes", label: "Source bytes", group: "Basic", kind: "number", defaultValue: 181 },
  { name: "dst_bytes", label: "Destination bytes", group: "Basic", kind: "number", defaultValue: 5450 },
]

const CONTENT: [string, string, number][] = [
  ["land", "Land (src == dst)", 0],
  ["wrong_fragment", "Wrong fragments", 0],
  ["urgent", "Urgent packets", 0],
  ["hot", "Hot indicators", 0],
  ["num_failed_logins", "Failed logins", 0],
  ["logged_in", "Logged in", 1],
  ["num_compromised", "Compromised conditions", 0],
  ["root_shell", "Root shell obtained", 0],
  ["su_attempted", "su attempted", 0],
  ["num_root", "Root accesses", 0],
  ["num_file_creations", "File creations", 0],
  ["num_shells", "Shell prompts", 0],
  ["num_access_files", "Access-control file ops", 0],
  ["num_outbound_cmds", "Outbound commands (ftp)", 0],
  ["is_host_login", "Is host login", 0],
  ["is_guest_login", "Is guest login", 0],
]

const TRAFFIC: [string, string, number][] = [
  ["count", "Connections to same host (2s)", 8],
  ["srv_count", "Connections to same service (2s)", 8],
  ["serror_rate", "SYN error rate", 0],
  ["srv_serror_rate", "Service SYN error rate", 0],
  ["rerror_rate", "REJ error rate", 0],
  ["srv_rerror_rate", "Service REJ error rate", 0],
  ["same_srv_rate", "Same service rate", 1],
  ["diff_srv_rate", "Different service rate", 0],
  ["srv_diff_host_rate", "Service diff-host rate", 0],
]

const HOST: [string, string, number][] = [
  ["dst_host_count", "Dst host count", 9],
  ["dst_host_srv_count", "Dst host srv count", 9],
  ["dst_host_same_srv_rate", "Dst host same-srv rate", 1],
  ["dst_host_diff_srv_rate", "Dst host diff-srv rate", 0],
  ["dst_host_same_src_port_rate", "Dst host same-src-port rate", 0.11],
  ["dst_host_srv_diff_host_rate", "Dst host srv diff-host rate", 0],
  ["dst_host_serror_rate", "Dst host SYN error rate", 0],
  ["dst_host_srv_serror_rate", "Dst host srv SYN error rate", 0],
  ["dst_host_rerror_rate", "Dst host REJ error rate", 0],
  ["dst_host_srv_rerror_rate", "Dst host srv REJ error rate", 0],
]

function numericFields(group: string, rows: [string, string, number][]): FieldConfig[] {
  return rows.map(([name, label, defaultValue]) => ({
    name,
    label,
    group,
    kind: "number" as const,
    defaultValue,
  }))
}

export const MANUAL_PREDICT_FIELDS: FieldConfig[] = [
  ...BASIC,
  ...numericFields("Content", CONTENT),
  ...numericFields("Traffic (2s window)", TRAFFIC),
  ...numericFields("Host-based traffic", HOST),
]

export const MANUAL_PREDICT_GROUPS = [
  "Basic",
  "Content",
  "Traffic (2s window)",
  "Host-based traffic",
]
