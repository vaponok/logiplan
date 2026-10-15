// Расчёт распределения в фоновом потоке, чтобы окно не подвисало.
import { calculateDistribution, type SplitterInput, type SplitterResult } from "../core/splitter";

export type CalcRequest = { id: number; input: SplitterInput };
export type CalcResponse = { id: number; ok: true; result: SplitterResult } | { id: number; ok: false; error: string };

self.onmessage = (e: MessageEvent<CalcRequest>) => {
  const { id, input } = e.data;
  let msg: CalcResponse;
  try {
    msg = { id, ok: true, result: calculateDistribution(input) };
  } catch (err) {
    msg = { id, ok: false, error: err instanceof Error ? err.message : String(err) };
  }
  (self as unknown as Worker).postMessage(msg);
};
