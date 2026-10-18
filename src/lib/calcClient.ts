// Клиент фонового расчёта; если Worker недоступен — считает в основном потоке.
import { calculateDistribution, type SplitterInput, type SplitterResult } from "../core/splitter";
import { CORE_URL, type CalcResponse } from "../core/calcHost";

let worker: Worker | null = null;
let seq = 0;
const waiting = new Map<number, { resolve: (r: SplitterResult) => void; reject: (e: Error) => void }>();

function getWorker(): Worker | null {
  if (worker) return worker;
  try {
    worker = new Worker(CORE_URL, { type: "module" });
    worker.onmessage = (e: MessageEvent<CalcResponse>) => {
      const w = waiting.get(e.data.id);
      if (!w) return;
      waiting.delete(e.data.id);
      if (e.data.ok) w.resolve(e.data.result);
      else w.reject(new Error(e.data.error));
    };
    worker.onerror = (e) => {
      for (const w of waiting.values()) w.reject(new Error(e.message || "worker error"));
      waiting.clear();
      worker = null;
    };
  } catch {
    worker = null;
  }
  return worker;
}

export function calculateInBackground(input: SplitterInput): Promise<SplitterResult> {
  const w = getWorker();
  if (!w) return Promise.resolve().then(() => calculateDistribution(input));
  const id = ++seq;
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    w.postMessage({ id, input });
  });
}
