import { useEffect, useRef } from "react"
import { useReducedMotion } from "@/hooks/useReducedMotion"

interface Node {
  x: number
  y: number
  vx: number
  vy: number
  r: number
}

interface Packet {
  a: Node
  b: Node
  t: number
  speed: number
}

/**
 * The "Topology Mesh + Signal Field" hybrid background: a sparse, slowly
 * drifting node/edge canvas (Topology Mesh) plus a CSS grid/radar-sweep/
 * light-field layer (Signal Field) mounted once behind the whole app
 * shell (see AppShell.tsx). Deliberately hand-rolled instead of a
 * particles/charting dependency -- this is ~120 lines and the app has no
 * other canvas use case that would justify a library.
 *
 * Recede-by-occlusion is structural, not code here: every content
 * surface (`.card`, tables, panels) is fully opaque, so this layer is
 * only ever visible in page margins, the hero, and the gaps between
 * cards -- see index.css's `.bg-root`/`.card` rules.
 */
export function NetworkBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    let nodes: Node[] = []
    let packets: Packet[] = []
    let width = 0
    let height = 0
    let animationId: number | null = null
    let lastPacketAt = 0

    function colorTriple(varName: string): string {
      return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
    }

    function resize() {
      if (!canvas) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = canvas.clientWidth
      height = canvas.clientHeight
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    function seedNodes() {
      const count = Math.max(16, Math.min(28, Math.floor((width * height) / 52000)))
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.05,
        vy: (Math.random() - 0.5) * 0.05,
        r: 1.2 + Math.random() * 1.2,
      }))
      packets = []
    }

    function drawFrame(): [Node, Node][] {
      if (!ctx) return []
      const lineRgb = colorTriple("--bg-line-rgb")
      const nodeRgb = colorTriple("--bg-node-rgb")
      const packetRgb = colorTriple("--bg-packet-rgb")

      ctx.clearRect(0, 0, width, height)
      const edges: [Node, Node][] = []
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i]
          const b = nodes[j]
          const dist = Math.hypot(a.x - b.x, a.y - b.y)
          const maxDist = 175
          if (dist < maxDist) {
            const opacity = (1 - dist / maxDist) * 0.17
            ctx.strokeStyle = `rgba(${lineRgb},${opacity.toFixed(3)})`
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
            edges.push([a, b])
          }
        }
      }
      for (const n of nodes) {
        ctx.fillStyle = `rgba(${nodeRgb},0.5)`
        ctx.beginPath()
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx.fill()
      }
      packets = packets.filter((p) => p.t < 1)
      for (const p of packets) {
        const x = p.a.x + (p.b.x - p.a.x) * p.t
        const y = p.a.y + (p.b.y - p.a.y) * p.t
        ctx.fillStyle = `rgba(${packetRgb},${(1 - p.t * 0.4).toFixed(2)})`
        ctx.beginPath()
        ctx.arc(x, y, 2, 0, Math.PI * 2)
        ctx.fill()
      }
      return edges
    }

    function loop(timestamp: number) {
      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.x < 0 || n.x > width) n.vx *= -1
        if (n.y < 0 || n.y > height) n.vy *= -1
      }
      for (const p of packets) p.t += p.speed
      const edges = drawFrame()
      if (edges.length && packets.length < 2 && timestamp - lastPacketAt > 2600 + Math.random() * 1800) {
        const [a, b] = edges[Math.floor(Math.random() * edges.length)]
        packets.push({ a, b, t: 0, speed: 0.01 + Math.random() * 0.006 })
        lastPacketAt = timestamp
      }
      animationId = requestAnimationFrame(loop)
    }

    function start() {
      resize()
      seedNodes()
      if (reducedMotion) {
        drawFrame()
        return
      }
      if (animationId) cancelAnimationFrame(animationId)
      animationId = requestAnimationFrame(loop)
    }

    function stop() {
      if (animationId) cancelAnimationFrame(animationId)
      animationId = null
    }

    function onVisibilityChange() {
      if (document.hidden) stop()
      else if (!reducedMotion) start()
    }

    start()
    window.addEventListener("resize", start)
    document.addEventListener("visibilitychange", onVisibilityChange)

    return () => {
      stop()
      window.removeEventListener("resize", start)
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [reducedMotion])

  return (
    <div className="bg-root" aria-hidden="true">
      <div className="bg-base" />
      <div className="bg-grid" />
      <div className="bg-rings" />
      <div className="bg-sweep" />
      <div className="bg-blob bg-blob--a" />
      <div className="bg-blob bg-blob--b" />
      <canvas ref={canvasRef} className="bg-canvas" />
    </div>
  )
}
