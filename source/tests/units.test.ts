// Режим «поровну условные единицы»: подразделения выравниваются по сумме
// ресурсов с весами на человека, а не по каждому ресурсу отдельно.
import { describe, expect, it } from "vitest";
import { AV_FACTORY_DEFAULTS } from "../src/core/quotaParse";
import {
  AVIATION_DEFAULT,
  calculateDistribution,
  OMTO_DEFAULT,
  UNIT_RESOURCES,
  type SplitterInput,
} from "../src/core/splitter";

const QUOTA = [
  "150-мм (Ящик),45",
  "Bonesaw MK.3 (Ящик),27",
  "Газовая граната (Ящик),36",
  "Осколочный минометный снаряд (Ящик),54",
  "Бетономешалка (Ящик),10",
  "Дробь (Ящик),18",
  "Mammon 91-b (Ящик),27",
].join("\n");

function makeInput(over: Partial<SplitterInput> = {}): SplitterInput {
  return {
    lang: "ru",
    quotaText: QUOTA,
    divisions: [
      { name: "А", people: 3 },
      { name: "Б", people: 2 },
      { name: "В", people: 4 },
    ],
    unitName: "",
    storageName: "",
    storagePass: "",
    weekdayIndex: 0,
    today: { year: 2026, month: 10, day: 15 },
    omtoName: "",
    omtoCount: 0,
    omtoNames: [],
    modsText: "",
    equipmentText: "",
    aviationCount: 0,
    aviationNames: [],
    aviationText: "",
    omtoList: [...OMTO_DEFAULT],
    aviationList: [...AVIATION_DEFAULT],
    avDefaults: { ...AV_FACTORY_DEFAULTS },
    enforceMul4: false,
    freeEmats: false,
    freeHemats: false,
    freeRmats: false,
    timeBudgetMs: Infinity,
    ...over,
  };
}

const weights = (w: Record<string, number>) => Object.fromEntries(UNIT_RESOURCES.map((r) => [r, w[r] ?? 0]));

/** Расход каждого ресурса по подразделениям из раздела «Ресурсы потрачены». */
function spent(output: string): Array<Record<string, number>> {
  const lines = output.split("\n");
  const start = lines.findIndex((l) => l.includes("Затрачено ресурсов"));
  const out: Array<Record<string, number>> = [];
  for (const l of lines.slice(start + 1)) {
    const m = /^ {2}(\S[^:]*): ([\d.]+)$/.exec(l);
    if (/^\S.*:$/.test(l)) out.push({});
    else if (m) out[out.length - 1][m[1]] = Number(m[2]);
  }
  return out;
}

/** Разброс нагрузки на человека: (max − min) / среднее. */
function spread(perPerson: number[]): number {
  const avg = perPerson.reduce((a, b) => a + b, 0) / perPerson.length;
  return (Math.max(...perPerson) - Math.min(...perPerson)) / avg;
}

function unitsPerPerson(output: string, w: Record<string, number>, people: number[]): number[] {
  return spent(output).map((d, i) => Object.entries(d).reduce((s, [r, v]) => s + (w[r] ?? 0) * v, 0) / people[i]);
}

describe("распределение по условным единицам", () => {
  const people = [3, 2, 4];

  it("без весов — вывод как раньше, без строки условных единиц", () => {
    const a = calculateDistribution(makeInput()).output;
    const b = calculateDistribution(makeInput({ unitWeights: null })).output;
    expect(b).toBe(a);
    expect(a).not.toContain("Условные единицы");
  });

  it("строка условных единиц у каждого подразделения", () => {
    const out = calculateDistribution(makeInput({ unitWeights: weights({ Бмат: 1, Емат: 2, Хемат: 3, Рмат: 4 }) })).output;
    expect(out.match(/ {2}Условные единицы: [\d.]+ \(на человека: [\d.]+\)/g)).toHaveLength(3);
  });

  it("сумма с весами на человека ровнее, чем в режиме «каждый ресурс»", () => {
    const w = { Бмат: 1, Емат: 3, Хемат: 6, Рмат: 10 };
    const byUnits = calculateDistribution(makeInput({ unitWeights: weights(w) })).output;
    const byRes = calculateDistribution(makeInput()).output;
    const su = spread(unitsPerPerson(byUnits, w, people));
    const sr = spread(unitsPerPerson(byRes, w, people));
    expect(su).toBeLessThanOrEqual(sr);
    expect(su).toBeLessThan(0.1);
  });

  it("веса меняют распределение", () => {
    const a = calculateDistribution(makeInput({ unitWeights: weights({ Бмат: 1, Рмат: 1 }) })).output;
    const b = calculateDistribution(makeInput({ unitWeights: weights({ Бмат: 1, Рмат: 20 }) })).output;
    expect(a).not.toBe(b);
  });

  it("все веса нулевые — считается как все по 1", () => {
    const zero = calculateDistribution(makeInput({ unitWeights: weights({}) })).output;
    const ones = calculateDistribution(makeInput({ unitWeights: weights({ Бмат: 1, Емат: 1, Хемат: 1, Рмат: 1, "Редкий металл": 1 }) })).output;
    expect(zero).toBe(ones);
  });

  it("ничего не теряется: итоговый расход тот же, что в обычном режиме", () => {
    const total = (out: string) =>
      spent(out).reduce<Record<string, number>>((acc, d) => {
        for (const [r, v] of Object.entries(d)) acc[r] = (acc[r] ?? 0) + v;
        return acc;
      }, {});
    const byUnits = calculateDistribution(makeInput({ unitWeights: weights({ Бмат: 1, Рмат: 5 }) })).output;
    const byRes = calculateDistribution(makeInput()).output;
    // расход ресурса зависит от того, как ящики легли в очереди (скидка),
    // поэтому сравниваем число ящиков каждой позиции
    const boxes = (out: string) => {
      const m: Record<string, number> = {};
      for (const [, n, name] of out.matchAll(/^ {4}(\d+) – (.+)$/gm)) m[name] = (m[name] ?? 0) + Number(n);
      return m;
    };
    expect(boxes(byUnits)).toEqual(boxes(byRes));
    expect(Object.keys(total(byUnits)).sort()).toEqual(Object.keys(total(byRes)).sort());
  });
});
