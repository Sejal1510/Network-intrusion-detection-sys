import Papa from "papaparse"
import type { PredictResponse } from "@/api/types"

export function parseCsvFile(file: File): Promise<Record<string, string>[]> {
  return new Promise((resolve, reject) => {
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => resolve(results.data),
      error: (error: Error) => reject(error),
    })
  })
}

export interface ZippedRow {
  row: Record<string, string>
  result: PredictResponse
}

/**
 * Pairs row `i` of the uploaded CSV with `results[i]` from
 * /predict/batch. Safe only because that endpoint scores rows in
 * upload order (see docs/API.md and src/nids/api/app.py's
 * predict_batch_csv) -- PredictResponse itself carries no raw_record to
 * join on, unlike a persisted PredictionHistoryItem.
 */
export function zipCsvWithResults(rows: Record<string, string>[], results: PredictResponse[]): ZippedRow[] {
  return results.map((result, i) => ({ row: rows[i] ?? {}, result }))
}
