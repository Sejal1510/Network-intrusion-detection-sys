import { useRef, useState } from "react"
import { validateCsvFile } from "@/lib/csv"

export function CsvDropzone({
  onFileSelected,
  onInvalidFile,
  disabled,
}: {
  onFileSelected: (file: File) => void
  /** A file was dropped/picked but failed validateCsvFile -- onFileSelected is never called for it. */
  onInvalidFile?: (message: string) => void
  disabled?: boolean
}) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    const error = validateCsvFile(file)
    if (error) {
      onInvalidFile?.(error)
      return
    }
    onFileSelected(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          inputRef.current?.click()
        } else if (e.key === " " || e.key === "Spacebar") {
          // Match native <button> semantics: Space activates on keyup, not
          // keydown -- but still prevent the default scroll here.
          e.preventDefault()
        }
      }}
      onKeyUp={(e) => {
        if (e.key === " " || e.key === "Spacebar") {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
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
