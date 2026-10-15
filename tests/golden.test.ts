// Сверка TypeScript-ядра с эталонами, снятыми с Python-версии
// (tools/golden/gen_golden.py). Любое расхождение — ошибка переноса.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { totalCost, netSulfur } from "../src/core/calculator";
import { parseAviationQuotaLine, parseCsvLine, serializeAviationQuotaLine, type AvSettings } from "../src/core/quotaParse";
import { calculateDistribution, calculateQuota, type SplitterInput } from "../src/core/splitter";
import type { Lang } from "../src/core/i18n";

const golden = <T>(name: string): T =>
  JSON.parse(readFileSync(new URL(`./golden/${name}`, import.meta.url), "utf-8")) as T;

describe("parse_csv_line", () => {
  const cases = golden<Array<{ line: string; result: [number, string] | null }>>("parse_csv.json");
  it(`совпадает с Python на ${cases.length} строках`, () => {
    const bad = cases.filter((c) => JSON.stringify(parseCsvLine(c.line)) !== JSON.stringify(c.result));
    expect(bad.slice(0, 5).map((c) => ({ ...c, ts: parseCsvLine(c.line) }))).toEqual([]);
  });
});

describe("parse_aviation_quota_line", () => {
  const cases = golden<Array<{ line: string; defaults: AvSettings; result: [number, string, AvSettings, string] | null }>>(
    "parse_aviation.json",
  );
  it(`совпадает с Python на ${cases.length} строках`, () => {
    const run = (c: (typeof cases)[number]) => {
      const r = parseAviationQuotaLine(c.line, c.defaults);
      return r ? [r[0], r[1], r[2], serializeAviationQuotaLine(r[0], r[1], r[2], c.defaults)] : null;
    };
    const bad = cases.filter((c) => JSON.stringify(run(c)) !== JSON.stringify(c.result));
    expect(bad.slice(0, 5).map((c) => ({ ...c, ts: run(c) }))).toEqual([]);
  });
});

describe("calculator.total_cost", () => {
  const cases = golden<
    Array<{ recipe: Record<string, number>; coke: string; fuel: string; scrap: number; result: Record<string, number> }>
  >("calculator.json");
  it(`совпадает с Python на ${cases.length} рецептах`, () => {
    for (const c of cases) {
      const bc = totalCost(c.recipe, c.coke, c.fuel, c.scrap);
      expect({ ...bc, net_sulfur: netSulfur(bc) }).toEqual(c.result);
    }
  });
});

describe("Рассчитать квоту", () => {
  const cases = golden<
    Array<{
      storage: string;
      required: string;
      omtoList: string[];
      aviationList: string[];
      lang: Lang;
      result: { main: string; mods: string; equipment: string; aviation: string };
    }>
  >("calc_quota.json");
  it(`совпадает с Python на ${cases.length} случаях`, () => {
    for (const c of cases) {
      expect(calculateQuota(c.storage, c.required, c.omtoList, c.aviationList, c.lang)).toEqual(c.result);
    }
  });
});

describe("Распределитель", () => {
  const cases = golden<Array<{ input: SplitterInput; output: string; undefined: string | null; pySeconds: number }>>(
    "splitter.json",
  );
  cases.forEach((c, k) => {
    it(`случай ${k + 1}: ${c.input.divisions.length} подр., ${c.input.quotaText.split("\n").length} строк`, () => {
      const r = calculateDistribution({ ...c.input, timeBudgetMs: Infinity });
      expect(r.output).toBe(c.output);
      expect(r.undefinedLines === null ? null : r.undefinedLines.map((u) => u.text).join("\n")).toBe(c.undefined);
    });
  });
});
