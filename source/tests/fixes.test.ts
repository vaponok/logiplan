// Регрессионные тесты на исправленные ошибки (не эталонные):
// 1) свободный формат строк в квоте Лётки; 2) повтор модификации у
// одного человека МТО складывается; 3) предметы Лётки без записи в
// resources.json — обычный заказ или «Неизвестные позиции».
import { describe, expect, it } from "vitest";
import { AV_FACTORY_DEFAULTS, parseAviationQuotaLine, type AvSettings } from "../src/core/quotaParse";
import {
  applyAviationSettings,
  aviationOrders,
  AVIATION_DEFAULT,
  calculateDistribution,
  calculateQuota,
  OMTO_DEFAULT,
  type SplitterInput,
} from "../src/core/splitter";

const DEF: AvSettings = { ...AV_FACTORY_DEFAULTS };

function makeInput(over: Partial<SplitterInput> = {}): SplitterInput {
  return {
    lang: "ru",
    quotaText: "Бинты (Ящик),8",
    divisions: [
      { name: "Отряд А", people: 3 },
      { name: "Отряд Б", people: 2 },
    ],
    unitName: "Тест",
    storageName: "Склад",
    storagePass: "1234",
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
    avDefaults: { ...DEF },
    enforceMul4: false,
    freeEmats: false,
    freeHemats: false,
    freeRmats: false,
    timeBudgetMs: Infinity,
    ...over,
  };
}

/** Строки раздела «Лётное отделение:» до первой пустой строки. */
function aviationSection(output: string): string[] {
  const lines = output.split("\n");
  const start = lines.indexOf("Лётное отделение:");
  if (start === -1) return [];
  const end = lines.indexOf("", start);
  return lines.slice(start, end === -1 ? undefined : end);
}

describe("FIX 1: свободный формат в квоте Лётки", () => {
  it("N шт. - Имя", () => {
    expect(parseAviationQuotaLine("2 шт. - Tulka I1.9 White Raven", DEF)).toEqual([2, "Tulka I1.9 White Raven", DEF]);
  });

  it("N ящ. – Имя [настройки] — запятые внутри [...] не мешают", () => {
    expect(parseAviationQuotaLine("3 ящ. – Tulka I1.9 White Raven [scrap=50, coke=no_sulfur]", DEF)).toEqual([
      3,
      "Tulka I1.9 White Raven",
      { coke: "no_sulfur", fuel: "sulfur", scrap: 50 },
    ]);
  });

  it("настройки свободного формата разбираются как в CSV", () => {
    expect(parseAviationQuotaLine("1 шт. - Tulka P4 Welkinrive [fuel=coal, scrap=150, coke=bad, junk]", DEF)).toEqual([
      1,
      "Tulka P4 Welkinrive",
      { coke: "with_sulfur", fuel: "coal", scrap: 100 },
    ]);
    const custom: AvSettings = { coke: "no_sulfur", fuel: "coal", scrap: 25 };
    expect(parseAviationQuotaLine("1 шт. - Tulka P4 Welkinrive", custom)).toEqual([1, "Tulka P4 Welkinrive", custom]);
  });

  it("N - Имя (Ящик) без единицы", () => {
    expect(parseAviationQuotaLine("4 - Luminary Mk. II Harbinger (Ящик)", DEF)).toEqual([4, "Luminary Mk. II Harbinger", DEF]);
  });

  it("локализованное имя в свободном формате приводится к каноническому", () => {
    expect(parseAviationQuotaLine("2 ящ. - Tulka I1.9 White Raven (Crate)", DEF)).toEqual([2, "Tulka I1.9 White Raven", DEF]);
  });

  it("count <= 0 -> null", () => {
    expect(parseAviationQuotaLine("0 шт. - Tulka I1.9 White Raven", DEF)).toBeNull();
    expect(parseAviationQuotaLine("0 - Tulka I1.9 White Raven", DEF)).toBeNull();
    expect(parseAviationQuotaLine("0 ящ. - Tulka I1.9 White Raven [scrap=0]", DEF)).toBeNull();
  });

  it("CSV-строки разбираются как раньше", () => {
    expect(parseAviationQuotaLine("Luminary Mk. II Harbinger [coke=no_sulfur, scrap=50],1", DEF)).toEqual([
      1,
      "Luminary Mk. II Harbinger",
      { coke: "no_sulfur", fuel: "sulfur", scrap: 50 },
    ]);
    expect(parseAviationQuotaLine("Tulka P4 Welkinrive (Ящик) [scrap=0],3", DEF)).toEqual([
      3,
      "Tulka P4 Welkinrive",
      { coke: "with_sulfur", fuel: "sulfur", scrap: 0 },
    ]);
    // "N - Имя" с запятой — не свободный формат, остаётся CSV
    expect(parseAviationQuotaLine("3 - Tulka I1.9 White Raven,2", DEF)).toEqual([2, "3 - Tulka I1.9 White Raven", DEF]);
    expect(parseAviationQuotaLine("Tulka I1.9 White Raven", DEF)).toBeNull();
    expect(parseAviationQuotaLine("   ", DEF)).toBeNull();
  });

  it("«Рассчитать квоту» -> поле Лётки -> распределение даёт базовые ресурсы пилотам", () => {
    const q = calculateQuota("", "Tulka I1.9 White Raven,2\nБинты (Ящик),8", [...OMTO_DEFAULT], [...AVIATION_DEFAULT], "ru");
    expect(q.aviation).toBe("2 шт. - Tulka I1.9 White Raven");

    const names = ["Пилот 1", "Пилот 2"];
    const loose = calculateDistribution(makeInput({ aviationCount: 2, aviationNames: names, aviationText: q.aviation }));
    const csv = calculateDistribution(
      makeInput({ aviationCount: 2, aviationNames: names, aviationText: "Tulka I1.9 White Raven,2" }),
    );
    expect(loose.output).toBe(csv.output);

    const sec = aviationSection(loose.output);
    expect(sec[0]).toBe("Лётное отделение:");
    expect(sec).toContain("  Пилот 1:");
    expect(sec).toContain("  Пилот 2:");
    expect(sec.filter((l) => /^ {4}(Уголь|Металлолом|Компоненты|Сера|Редкие сплавы): \d+$/.test(l)).length).toBeGreaterThan(0);
    expect(sec.some((l) => /^ {4}Металлолом: \d+$/.test(l))).toBe(true);
    expect(loose.undefinedLines).toEqual([]);
  });

  it("авиа-предмет свободным форматом в основной квоте -> «Ресурсы на завод»", () => {
    const loose = calculateDistribution(makeInput({ quotaText: "2 шт. - Tulka I1.9 White Raven\nБинты (Ящик),8" }));
    const csv = calculateDistribution(makeInput({ quotaText: "Tulka I1.9 White Raven,2\nБинты (Ящик),8" }));
    expect(loose.output).toBe(csv.output);
    expect(loose.output.split("\n")).toContain("    Ресурсы на завод:");
    expect(loose.output).toMatch(/^ {6}Металлолом: \d+$/m);
  });

  it("aviationOrders видит строки свободного формата, applyAviationSettings переписывает их в CSV", () => {
    const text = "2 шт. - Tulka I1.9 White Raven\nБинты (Ящик),3\n1 ящ. - Luminary Mk. II Harbinger [coke=no_sulfur]";
    const orders = aviationOrders(text, DEF);
    expect(orders).toEqual([
      { lineIndex: 0, count: 2, name: "Tulka I1.9 White Raven", settings: DEF },
      { lineIndex: 2, count: 1, name: "Luminary Mk. II Harbinger", settings: { ...DEF, coke: "no_sulfur" } },
    ]);
    const perLine = new Map<number, AvSettings>([[2, { ...DEF, coke: "no_sulfur" }]]);
    expect(applyAviationSettings(text, orders, DEF, perLine, "ru")).toBe(
      "Tulka I1.9 White Raven,2\nБинты (Ящик),3\nLuminary Mk. II Harbinger [coke=no_sulfur],1",
    );
  });
});

describe("FIX 2: повтор модификации у одного человека МТО", () => {
  it("две строки одной модификации (3 и 4) у одного человека -> 7", () => {
    const r = calculateDistribution(
      makeInput({
        omtoCount: 1,
        omtoNames: ["Иван"],
        modsText: "O’Brien V.101 Freeman,3\nO’Brien V.101 Freeman,4",
      }),
    );
    const lines = r.output.split("\n");
    const at = lines.indexOf("Иван — Модификации:");
    expect(at).toBeGreaterThan(-1);
    expect(lines[at + 1]).toBe("  7 шт. - O’Brien V.101 Freeman");
    expect(lines[at + 2]).toBe("");
  });

  it("сложение не меняет порядок позиций", () => {
    const r = calculateDistribution(
      makeInput({
        omtoCount: 1,
        omtoNames: ["Иван"],
        modsText: "O’Brien V.101 Freeman,5\nO’Brien V.113 Gravekeeper,4\nO’Brien V.101 Freeman,2",
      }),
    );
    const lines = r.output.split("\n");
    const at = lines.indexOf("Иван — Модификации:");
    expect(lines.slice(at + 1, at + 3)).toEqual(["  7 шт. - O’Brien V.101 Freeman", "  4 шт. - O’Brien V.113 Gravekeeper"]);
  });
});

describe("FIX 3: предметы Лётки без записи в resources.json", () => {
  const pilots = { aviationCount: 2, aviationNames: ["Пилот 1", "Пилот 2"] };
  const expected = [
    "Лётное отделение:",
    "  Пилот 1:",
    "    2 - Одеяние авиатора (Ящик)",
    "  Пилот 2:",
    "    1 - Одеяние авиатора (Ящик)",
  ];

  it("«Одеяние авиатора (Ящик),3» на двух пилотов -> 2 и 1", () => {
    const r = calculateDistribution(makeInput({ ...pilots, aviationText: "Одеяние авиатора (Ящик),3" }));
    expect(aviationSection(r.output)).toEqual(expected);
    expect(r.undefinedLines).toEqual([]);
  });

  it("«3 ящ. - Одеяние авиатора» — то же самое", () => {
    const r = calculateDistribution(makeInput({ ...pilots, aviationText: "3 ящ. - Одеяние авиатора" }));
    expect(aviationSection(r.output)).toEqual(expected);
    expect(r.undefinedLines).toEqual([]);
  });

  it("на английском — локализованное имя в выводе", () => {
    const r = calculateDistribution(makeInput({ ...pilots, lang: "en", aviationText: "Одеяние авиатора (Ящик),3" }));
    const lines = r.output.split("\n");
    expect(lines).toContain("    2 - Aviator’s Raiment (Crate)");
    expect(lines).toContain("    1 - Aviator’s Raiment (Crate)");
  });

  it("неизвестная позиция Лётки -> «Неизвестные позиции», не в выводе пилотов", () => {
    const r = calculateDistribution(
      makeInput({ ...pilots, aviationText: "Неведомая штука,2\nTulka I1.9 White Raven,1\nНеведомая штука,1" }),
    );
    expect(r.undefinedLines).toEqual([
      { text: "Неведомая штука", kind: "unknown" },
      { text: "Неведомая штука", kind: "unknown" },
    ]);
    expect(aviationSection(r.output).some((l) => l.includes("Неведомая штука"))).toBe(false);
  });

  it("список неизвестных пополняется и при нуле пилотов, после позиций основной квоты", () => {
    const r = calculateDistribution(
      makeInput({ quotaText: "Бинты (Ящик),8\nЧто-то странное,3", aviationText: "Неведомая штука,2" }),
    );
    expect(r.undefinedLines).toEqual([
      { text: "Что-то странное", kind: "unknown" },
      { text: "Неведомая штука", kind: "unknown" },
    ]);
  });

  it("ранний выход (нет ни одной позиции) список не трогает", () => {
    const r = calculateDistribution(makeInput({ quotaText: "", aviationText: "" }));
    expect(r.undefinedLines).toBeNull();
  });
});

describe("Блок [...] в конце строки Лётки: краевые случаи", () => {
  it("U+FEFF после ] — не блок настроек (как в Python: \\s не включает BOM)", () => {
    const r = parseAviationQuotaLine("2 шт. - Tulka P4 Welkinrive [scrap=5]﻿", DEF);
    expect(r).not.toBeNull();
    expect(r![1]).not.toBe("Tulka P4 Welkinrive");
    expect(r![2]).toEqual(DEF);
  });

  it("строка из тысяч «[» разбирается быстро (без квадратичного перебора)", () => {
    const t0 = performance.now();
    parseAviationQuotaLine("[".repeat(20000), DEF);
    parseAviationQuotaLine("a" + " [".repeat(10000) + "x", DEF);
    expect(performance.now() - t0).toBeLessThan(150);
  });
});
