export function NumericField({
  name,
  value,
  onChange,
}: {
  name: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <input
      id={name}
      type="number"
      step="any"
      value={value}
      onChange={(e) => onChange(e.target.valueAsNumber)}
      className="w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1.5 text-sm tabular-nums"
    />
  )
}
