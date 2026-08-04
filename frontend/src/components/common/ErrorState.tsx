export function ErrorState({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg border p-4 text-sm"
      style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
    >
      {message}
    </div>
  )
}
