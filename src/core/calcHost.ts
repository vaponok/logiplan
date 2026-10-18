// Фоновый расчёт без второй копии кода. Этот модуль собирается в общий
// чанк с логикой и данными (src/core, src/data — см. vite.config.ts), и тот же
// чанк запускается как Worker: окно берёт отсюда CORE_URL, а внутри Worker
// модуль отвечает на запросы. Поэтому в чанке не должно быть импортов
// интерфейса — это проверяет сборка.
import { calculateDistribution, type SplitterInput, type SplitterResult } from "./splitter";

export type CalcRequest = { id: number; input: SplitterInput };
export type CalcResponse = { id: number; ok: true; result: SplitterResult } | { id: number; ok: false; error: string };

/** Адрес чанка с логикой — его и запускает Worker. */
export const CORE_URL = import.meta.url;

if (typeof document === "undefined" && typeof postMessage === "function") {
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
}
