import { useRef, useState } from "react"

export function CsvDropzone({
  onFileSelected,
  disabled,
}: {
  onFileSelected: (file: File) => void
  disabled?: boolean
}) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (file) onFileSelected(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setIsDragging(false)
        handleFiles(e.dataTransfer.files)
      }}
      aria-disabled={disabled}
      className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center text-sm transition-colors ${
        isDragging
          ? "border-[var(--sequential-450)] bg-[var(--gridline)]"
          : "border-[var(--border-hairline)]"
      } ${disabled ? "pointer-events-none opacity-50" : ""}`}
    >
      <p className="text-[var(--text-secondary)]">
        Drag and drop a CSV file here, or click to choose one.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
        disabled={disabled}
      />
    </div>
  )
}
