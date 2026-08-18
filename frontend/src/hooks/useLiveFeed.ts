import { useEffect, useRef, useState } from "react"
import { apiWebSocketUrl } from "@/api/client"
import { requestWsTicket } from "@/api/endpoints/auth"
import { listPredictions } from "@/api/endpoints/history"
import type { LiveFeedMessage, MitreMapping, PredictResponse, Severity } from "@/api/types"
import type { ConnectionStatus } from "@/components/layout/ConnectionStatusIndicator"

export interface LiveFeedEntry {
  id: string
  created_at: string
  prediction: string | number
  severity: Severity
  risk_score: number
  attack_category: string | null
  mitre: MitreMapping | null
  alert_id: string | null
}

const MAX_BUFFER = 500
const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30_000

function toEntry(response: PredictResponse): LiveFeedEntry {
  return {
    id: response.alert_id ?? crypto.randomUUID(),
    created_at: new Date().toISOString(),
    prediction: response.prediction,
    severity: response.severity,
    risk_score: response.risk_score.score,
    attack_category: response.attack_category,
    mitre: response.mitre,
    alert_id: response.alert_id,
  }
}

function backoffDelay(attempt: number): number {
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt)
  return exponential * (0.5 + Math.random() * 0.5)
}

export interface UseLiveFeedResult {
  status: ConnectionStatus
  entries: LiveFeedEntry[]
}

/**
 * Wraps the native WebSocket for /ws/live: reconnects with exponential
 * backoff+jitter (mirroring src/nids/agent/client.py's AgentClient), and
 * backfills the gap via GET /history/predictions on every reconnect since
 * /ws/live is Pub/Sub-only with no replay (see docs/LIVE_MONITORING.md).
 *
 * Auth: mints a fresh, ~60s-lived ws-ticket (POST /auth/ws-ticket, needs
 * the caller's own dashboard login) immediately before every connect and
 * reconnect, rather than pairing as an anonymous device the way this hook
 * used to (see docs/AUTH.md) -- a dead session simply fails to mint a new
 * ticket, so a logged-out/expired user's reconnect attempts fail closed
 * instead of silently continuing to stream.
 */
export function useLiveFeed(): UseLiveFeedResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const [entries, setEntries] = useState<LiveFeedEntry[]>([])

  const entriesRef = useRef<LiveFeedEntry[]>([])
  const lastMessageAtRef = useRef<string | null>(null)
  const hasConnectedBeforeRef = useRef(false)
  const attemptRef = useRef(0)
  const closedByUsRef = useRef(false)
  const socketRef = useRef<WebSocket | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    closedByUsRef.current = false

    function pushEntries(newEntries: LiveFeedEntry[]) {
      if (newEntries.length === 0) return
      const seen = new Set(entriesRef.current.map((e) => e.id))
      const deduped = newEntries.filter((e) => !seen.has(e.id))
      const merged = [...deduped, ...entriesRef.current].slice(0, MAX_BUFFER)
      entriesRef.current = merged
      setEntries(merged)
      lastMessageAtRef.current = merged[0]?.created_at ?? lastMessageAtRef.current
    }

    async function backfillGap() {
      const since = lastMessageAtRef.current
      if (!since) return
      try {
        const page = await listPredictions({ start_date: since, limit: 100 })
        const backfilled: LiveFeedEntry[] = page.items.map((item) => ({
          id: item.id,
          created_at: item.created_at,
          prediction: item.prediction,
          severity: item.severity,
          risk_score: item.risk_score,
          attack_category: item.attack_category,
          mitre: item.mitre,
          alert_id: null,
        }))
        pushEntries(backfilled)
      } catch {
        // best-effort: a failed backfill just means a possible gap, not a fatal error
      }
    }

    async function connect() {
      if (closedByUsRef.current) return
      setStatus(hasConnectedBeforeRef.current ? "reconnecting" : "connecting")

      let ticket: string
      try {
        ;({ ticket } = await requestWsTicket())
      } catch {
        setStatus("offline")
        return
      }
      if (closedByUsRef.current) return

      const socket = new WebSocket(apiWebSocketUrl(`/ws/live?ticket=${encodeURIComponent(ticket)}`))
      socketRef.current = socket

      socket.onopen = () => {
        attemptRef.current = 0
        setStatus("live")
        if (hasConnectedBeforeRef.current) void backfillGap()
        hasConnectedBeforeRef.current = true
      }

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as LiveFeedMessage
          if (message.type === "prediction") pushEntries([toEntry(message.data)])
        } catch {
          // ignore malformed frames
        }
      }

      socket.onclose = () => {
        if (closedByUsRef.current) return
        setStatus("reconnecting")
        const delay = backoffDelay(attemptRef.current)
        attemptRef.current += 1
        timeoutRef.current = setTimeout(() => void connect(), delay)
      }

      socket.onerror = () => {
        socket.close()
      }
    }

    void connect()

    return () => {
      closedByUsRef.current = true
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      socketRef.current?.close()
    }
  }, [])

  return { status, entries }
}
