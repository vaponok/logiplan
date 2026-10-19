// Расчётная часть ResourceSplitter (legacy/resource_splitter.py) без UI:
// на входе — состояние формы, на выходе — текст результата и список
// нераспознанных позиций. Порядок операций и формат вывода повторяют
// Python-версию; сверка — tests/golden.test.ts.
import resourceDbJson from "../data/resources.json";
import { aviationDefault, mtoModifications, notFactory, omtoDefault } from "../data/items.json";
import { allocate, DISCOUNT_G, makeChunks, discountedSum, resourcePairs } from "./allocator";
import type { ResourceDb, ResourceEntry } from "./allocator";
import { netSulfur, totalCost, type Recipe } from "./calculator";
import { hasItem, ITEM_I18N, normalizeText, tr, trAviationResource, trItem, trResource, WEEKDAYS, type Lang } from "./i18n";
import { cmpStr, cmpTuple, floatRepr, floorDiv, pyRoundTo, rstrip, splitlines, strip } from "./py";
import {
  formatQuotaLine,
  parseAviationQuotaLine,
  parseCsvLine,
  serializeAviationQuotaLine,
  type AvSettings,
} from "./quotaParse";

export const RESOURCE_DB = resourceDbJson as ResourceDb;
export const MTO_MODIFICATIONS: readonly string[] = mtoModifications;
export const OMTO_DEFAULT: readonly string[] = omtoDefault;
export const AVIATION_DEFAULT: readonly string[] = aviationDefault;
/** Позиции, которые раньше были заводскими, а теперь нет (tools/data_updates.py). */
export const NOT_FACTORY: readonly string[] = notFactory;

/** Список завода без позиций, которые больше не заводские: из сохранённых
 *  настроек и из старой версии они иначе так и остались бы в нём. */
export function withoutNotFactory(list: string[]): string[] {
  const drop = new Set(NOT_FACTORY.map(normalizeText));
  return list.filter((n) => !drop.has(normalizeText(n)));
}

const has = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);
/** db.get(name) с питоновской «истинностью»: пустой dict — как отсутствие. */
function entryOf(name: string): ResourceEntry | undefined {
  if (!has(RESOURCE_DB, name)) return undefined;
  const e = RESOURCE_DB[name];
  return e && Object.keys(e).length ? e : undefined;
}
const entryOrEmpty = (name: string): ResourceEntry => (has(RESOURCE_DB, name) ? RESOURCE_DB[name] : {});
/** Имя из квоты Лётки известно: есть в resources.json или в i18n (в т.ч. ящичный вариант). */
const isKnownAviationName = (name: string): boolean =>
  !!entryOf(name) || hasItem(name) || hasItem(`${name} (Ящик)`);

/** k.lower() -> k (последний выигрывает, как dict comprehension). */
const NORMALIZED = new Map<string, string>();
for (const k of Object.keys(RESOURCE_DB)) NORMALIZED.set(k.toLowerCase(), k);

const FREE_EXCEPTIONS = new Set(["рмат (ящик)", "емат (ящик)", "хемат (ящик)"]);

export interface Division {
  name: string;
  people: number;
}

export interface SplitterFlags {
  enforceMul4: boolean;
  freeEmats: boolean;
  freeHemats: boolean;
  freeRmats: boolean;
}

export interface SplitterInput extends SplitterFlags {
  lang: Lang;
  quotaText: string;
  divisions: Division[];
  unitName: string;
  storageName: string;
  storagePass: string;
  weekdayIndex: number;
  /** «Сегодня» для расчёта даты плана (локальная дата). */
  today: { year: number; month: number; day: number };
  omtoName: string;
  omtoCount: number;
  omtoNames: string[];
  modsText: string;
  equipmentText: string;
  aviationCount: number;
  aviationNames: string[];
  aviationText: string;
  omtoList: string[];
  aviationList: string[];
  avDefaults: AvSettings;
  /** Бюджет локального поиска распределителя, мс. */
  timeBudgetMs?: number;
  /**
   * Режим «поровну условные единицы»: вес единицы каждого ресурса (Бмат,
   * Емат, …). Подразделения выравниваются по сумме ресурсов с этими весами
   * на человека, а не по каждому ресурсу отдельно. null / не задано —
   * старый режим (поровну каждый ресурс).
   */
  unitWeights?: Record<string, number> | null;
}

/** Все ресурсы, у которых может быть вес в режиме условных единиц. */
export const UNIT_RESOURCES = ["Бмат", "Емат", "Хемат", "Рмат", "Редкий металл"] as const;
const UNITS_KEY = "\u0000units";

/** Веса режима условных единиц; null — режим выключен. Все нули -> все 1. */
function unitWeightMap(w: Record<string, number> | null | undefined): Map<string, number> | null {
  if (!w) return null;
  const m = new Map<string, number>();
  for (const r of UNIT_RESOURCES) {
    const v = w[r];
    m.set(r, Number.isFinite(v) && v > 0 ? v : 0);
  }
  if (![...m.values()].some((v) => v > 0)) for (const r of UNIT_RESOURCES) m.set(r, 1);
  return m;
}

/** Сумма ресурсов в условных единицах (ресурс без веса в списке — вес 1). */
function toUnits(vec: Iterable<[string, number]>, weights: Map<string, number>): number {
  let s = 0;
  for (const [r, v] of vec) s += (weights.get(r) ?? 1) * v;
  return s;
}

export type UndefinedKind = "aviation" | "factory" | "unknown";
export interface UndefinedLine {
  text: string;
  kind: UndefinedKind;
}

export interface SplitterResult {
  output: string;
  /** null — список «неизвестных позиций» не меняется (как в Python при раннем выходе). */
  undefinedLines: UndefinedLine[] | null;
  allocatorIterations?: number;
  allocatorConverged?: boolean;
}

// ---------------- признак «ресурс платный» ----------------

const WORD = "0-9A-Za-zА-Яа-яЁё";
const tokenRe = (tokens: string[]) =>
  new RegExp(tokens.map((t) => `(?<![${WORD}])${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![${WORD}])`).join("|"), "iu");
const EMAT_RE = tokenRe(["emat", "емат", "emats", "ематы"]);
const HEMAT_RE = tokenRe(["hemat", "хемат", "xemat", "hemats", "хематы"]);
const RMAT_RE = tokenRe(["rmat", "рмат", "rmats", "рматы"]);

export function makeShouldCountResourceCost(flags: SplitterFlags) {
  const cache = new Map<string, boolean>();
  return (itemName: string, resourceName: string): boolean => {
    if (!resourceName) return true;
    const key = `${itemName}\u0001${resourceName}`;
    const hit = cache.get(key);
    if (hit !== undefined) return hit;
    let result = true;
    const itemNorm = strip(itemName || "").toLowerCase();
    const resNorm = strip(resourceName).toLowerCase();
    if (FREE_EXCEPTIONS.has(itemNorm)) result = true;
    else if (EMAT_RE.test(resNorm)) result = !flags.freeEmats;
    else if (HEMAT_RE.test(resNorm)) result = !flags.freeHemats;
    else if (RMAT_RE.test(resNorm)) result = !flags.freeRmats;
    cache.set(key, result);
    return result;
  };
}

// ---------------- распределение ----------------

type Loads = Map<string, number>;
const add = (m: Map<string, number>, k: string, v: number) => m.set(k, (m.get(k) ?? 0) + v);
const sumValues = (m: Map<string, number>) => {
  let s = 0;
  for (const v of m.values()) s += v;
  return s;
};

class Distributor {
  readonly n: number;
  readonly distribution: Array<Map<string, number>>;
  readonly usedActual: Loads[];
  readonly usedNominal: Loads[];

  constructor(
    readonly divisions: number[],
    readonly shouldCount: (name: string, r: string) => boolean,
    readonly enforceMul4: boolean,
    readonly timeBudgetMs: number,
    /** Режим условных единиц: веса ресурсов; null — поровну каждый ресурс. */
    readonly weights: Map<string, number> | null = null,
  ) {
    this.n = divisions.length;
    this.distribution = Array.from({ length: this.n }, () => new Map());
    this.usedActual = Array.from({ length: this.n }, () => new Map());
    this.usedNominal = Array.from({ length: this.n }, () => new Map());
  }

  iterations = 0;
  converged = true;

  combinedLoadForResource(i: number, r: string): number {
    const actual = this.usedActual[i].get(r) ?? 0;
    const nominal = this.usedNominal[i].get(r) ?? 0;
    if (nominal > 0 && actual === 0) return nominal;
    return actual;
  }

  /** Ключи used_actual ∪ used_nominal в детерминированном порядке. */
  resourceKeys(i: number): string[] {
    const keys = new Set<string>([...this.usedActual[i].keys(), ...this.usedNominal[i].keys()]);
    return [...keys].sort(cmpStr);
  }

  combinedLoadTotal(i: number): number {
    let s = 0;
    for (const r of this.resourceKeys(i)) s += (this.weights?.get(r) ?? 1) * this.combinedLoadForResource(i, r);
    return s;
  }

  perPersonLoad(i: number): number {
    return this.divisions[i] ? this.combinedLoadTotal(i) / this.divisions[i] : Infinity;
  }

  boxCount(i: number): number {
    return sumValues(this.distribution[i]);
  }

  groupItemsPerPerson(i: number, group: number | undefined): number {
    if (group === undefined || group === null) return 0;
    let total = 0;
    for (const [iname, cnt] of this.distribution[i]) {
      if (entryOrEmpty(iname).group === group) total += cnt;
    }
    const people = this.divisions[i] ? this.divisions[i] : 1;
    return total / people;
  }

  minLoadIndex(): number {
    let best: number[] | null = null;
    for (let i = 0; i < this.n; i++) {
      const t = [this.perPersonLoad(i), this.boxCount(i), i];
      if (!best || cmpTuple(t, best) < 0) best = t;
    }
    return best![2];
  }

  perform(itemEntries: Array<[string, number]>, avgPerPerson: Map<string, number>) {
    const delayed: Array<[string, number, string]> = [];
    const regular: Array<[string, number]> = [];
    for (const [name, cnt] of itemEntries) {
      const entry = entryOrEmpty(name);
      const dist = entry.distribution ?? "per_person";
      if (dist === "balance_fill") continue;
      if ((dist === "per_person" && entry.group === 8) || entry.only_one_per_division) {
        delayed.push([name, cnt, dist]);
        continue;
      }
      regular.push([name, cnt]);
    }

    this.distributeDelayed(delayed);

    let chunks = makeChunks(regular, RESOURCE_DB, this.shouldCount, this.enforceMul4);
    if (chunks.length) {
      // В Python порядок ключей preload брался из set() и менялся от запуска
      // к запуску; здесь он фиксирован (по имени ресурса).
      let preload = Array.from({ length: this.n }, (_, i) => {
        const d = new Map<string, number>();
        for (const r of this.resourceKeys(i)) d.set(r, this.combinedLoadForResource(i, r));
        return d;
      });
      // Условные единицы: у чанков и уже выданного один «ресурс» — сумма с
      // весами; тот же поиск выравнивает её на человека.
      const w = this.weights;
      if (w) {
        chunks = chunks.map((ch) => ({ ...ch, vec: new Map([[UNITS_KEY, toUnits(ch.vec, w)]]) }));
        preload = preload.map((d) => new Map([[UNITS_KEY, toUnits(d, w)]]));
      }
      const res = allocate(chunks, this.divisions, preload, this.timeBudgetMs);
      this.iterations = res.iterations;
      this.converged = res.converged;

      const placed = new Map<number, Map<string, number>>();
      chunks.forEach((ch, k) => {
        const di = res.assign[k];
        let m = placed.get(di);
        if (!m) placed.set(di, (m = new Map()));
        add(m, ch.name, ch.boxes);
      });
      for (const [i, itemsHere] of placed) {
        for (const [name, cnt] of itemsHere) {
          add(this.distribution[i], name, cnt);
          const entry = entryOrEmpty(name);
          const g = DISCOUNT_G[entry.distribution ?? "per_person"];
          for (const [r, c] of resourcePairs(entry)) {
            add(this.usedNominal[i], r, c * cnt);
            if (!this.shouldCount(name, r)) continue;
            add(this.usedActual[i], r, g ? discountedSum(c, cnt, g) : c * cnt);
          }
        }
      }
    }

    this.distributeBalance(itemEntries, avgPerPerson);
  }

  distributeDelayed(delayed: Array<[string, number, string]>) {
    const assignedPp = new Map<number, number>();
    const assignedOnce = new Set<number>();
    for (const [name, cnt, dtype] of delayed) {
      const entry = entryOrEmpty(name);
      const pairs = resourcePairs(entry);
      if (dtype === "per_person") {
        const group = entry.group;
        if (group === 8) {
          const boxes = Math.ceil(cnt / 5) * 5;
          let bestI: number | null = null;
          let bestScore: number[] | null = null;
          for (let i = 0; i < this.n; i++) {
            const score = [this.groupItemsPerPerson(i, group), this.perPersonLoad(i), this.boxCount(i)];
            if (!bestScore || cmpTuple(score, bestScore) < 0) {
              bestScore = score;
              bestI = i;
            }
          }
          if (bestI !== null) {
            add(this.distribution[bestI], name, boxes);
            for (const [r, c] of pairs) {
              add(this.usedNominal[bestI], r, c * boxes);
              if (!this.shouldCount(name, r)) continue;
              add(this.usedActual[bestI], r, discountedSum(c, boxes, 5));
            }
          }
        } else {
          const chunks = [...new Array(Math.floor(cnt / 5)).fill(5), ...(cnt % 5 ? [cnt % 5] : [])];
          let limit = 1;
          for (const chunk of chunks) {
            let placed = false;
            while (!placed) {
              const candidates: Array<[number[], number]> = [];
              for (let i = 0; i < this.n; i++) {
                if ((assignedPp.get(i) ?? 0) < limit) {
                  candidates.push([[this.groupItemsPerPerson(i, entry.group), this.perPersonLoad(i), this.boxCount(i), i], i]);
                }
              }
              if (candidates.length) {
                candidates.sort((a, b) => cmpTuple(a[0], b[0]));
                const chosen = candidates[0][1];
                add(this.distribution[chosen], name, chunk);
                for (const [r, c] of pairs) {
                  add(this.usedNominal[chosen], r, c * chunk);
                  if (!this.shouldCount(name, r)) continue;
                  add(this.usedActual[chosen], r, discountedSum(c, chunk, 5));
                }
                assignedPp.set(chosen, (assignedPp.get(chosen) ?? 0) + 1);
                placed = true;
              } else {
                limit += 1;
                if (!this.n) break; // в Python здесь был бы вечный цикл
              }
            }
          }
        }
      } else {
        // only_one_per_division
        for (let k = 0; k < cnt; k++) {
          let placed = false;
          let best: [number[], number] | null = null;
          for (let j = 0; j < this.n; j++) {
            if (assignedOnce.has(j)) continue;
            const score = [this.groupItemsPerPerson(j, entry.group), this.perPersonLoad(j), this.boxCount(j)];
            if (!best || cmpTuple(score, best[0]) < 0) best = [score, j];
          }
          if (best) {
            const chosen = best[1];
            add(this.distribution[chosen], name, 1);
            for (const [r, c] of pairs) {
              add(this.usedNominal[chosen], r, c);
              add(this.usedActual[chosen], r, c);
            }
            assignedOnce.add(chosen);
            placed = true;
          }
          if (!placed && this.n) {
            const i = this.minLoadIndex();
            add(this.distribution[i], name, 1);
            for (const [r, c] of pairs) {
              add(this.usedNominal[i], r, c);
              add(this.usedActual[i], r, c);
            }
          }
        }
      }
    }
  }

  distributeBalance(itemEntries: Array<[string, number]>, avgPerPerson: Map<string, number>) {
    const counts = new Map<string, number>();
    for (const [name, cnt] of itemEntries) add(counts, name, cnt);
    for (const [name, cnt] of counts) {
      const entry = entryOrEmpty(name);
      if (entry.distribution !== "balance_fill") continue;
      const pairs = resourcePairs(entry);
      const w = this.weights;
      const avgUnits = w ? toUnits(avgPerPerson, w) : 0;
      for (let k = 0; k < cnt; k++) {
        let bestI: number | null = null;
        let bestScore: number[] | null = null;
        for (let i = 0; i < this.n; i++) {
          let deficit = 0;
          if (w) {
            deficit = Math.max(0, avgUnits * this.divisions[i] - this.combinedLoadTotal(i));
          } else {
            for (const [r] of pairs) {
              const ideal = (avgPerPerson.get(r) ?? 0) * this.divisions[i];
              const actualLoad = this.combinedLoadForResource(i, r);
              deficit += Math.max(0, ideal - actualLoad);
            }
          }
          const score = [deficit, -this.boxCount(i)];
          if (!bestScore || cmpTuple(score, bestScore) > 0) {
            bestScore = score;
            bestI = i;
          }
        }
        if (bestI === null) {
          if (!this.n) break;
          bestI = this.minLoadIndex();
        }
        add(this.distribution[bestI], name, 1);
        for (const [r, c] of pairs) {
          add(this.usedNominal[bestI], r, c);
          if (this.shouldCount(name, r)) add(this.usedActual[bestI], r, c);
        }
      }
    }
  }
}

// ---------------- авиа-калькулятор ----------------

const BASE_KEYS = ["coal", "scrap", "components", "sulfur", "rare_mats"] as const;
type BaseKey = (typeof BASE_KEYS)[number];
type BaseTotals = Record<BaseKey, number>;
const zeroBase = (): BaseTotals => ({ coal: 0, scrap: 0, components: 0, sulfur: 0, rare_mats: 0 });

function aviationBaseCost(recipe: Recipe | undefined, count: number, s: AvSettings): BaseTotals | null {
  if (!recipe || !Object.keys(recipe).length || count <= 0) return null;
  const scaled: Recipe = {};
  for (const k of ["steel", "m1", "m2", "m3", "m4", "m5", "proc", "rare", "build"] as const) {
    scaled[k] = Math.trunc(Number(recipe[k] ?? 0)) * count;
  }
  const bc = totalCost(scaled, s.coke, s.fuel, s.scrap / 100.0);
  return { coal: bc.coal, scrap: bc.scrap, components: bc.components, sulfur: netSulfur(bc), rare_mats: bc.rare_mats };
}

function addBase(total: BaseTotals, b: BaseTotals | null) {
  if (!b) return;
  for (const k of BASE_KEYS) total[k] += b[k];
}

// ---------------- нормализация имён для «неизвестных позиций» ----------------

const UNIT_PAREN_RE = /^(?:(?:шт(?:\.|))|штука|ящ(?:\.|ик)?|box|crate|короб(?:к)?)$/iu;
const UNIT_TAIL_RE = /(?:\s|^)(?:шт(?:\.|)|штука|ящ(?:\.|ик)?|box|crate|короб(?:к)?)\s*$/iu;

function normalizeOmtoName(s: string): string {
  if (!s) return "";
  s = normalizeText(s);
  let out = s;
  for (const m of s.matchAll(/\(([^)]*)\)/gu)) {
    const inside = strip(m[1]).toLowerCase();
    if (UNIT_PAREN_RE.test(inside)) out = out.split(m[0]).join(" ");
  }
  s = out.replace(UNIT_TAIL_RE, "");
  s = s.replace(/["'.,:;!?]+/gu, " ");
  return strip(s.replace(/\s+/gu, " "));
}

// ---------------- даты ----------------

/** Ближайший (строго в будущем) день недели target (0 — понедельник), "%d.%m.%Y". */
export function nextWeekday(target: number, today: { year: number; month: number; day: number }): string {
  const d = new Date(today.year, today.month - 1, today.day);
  const weekday = (d.getDay() + 6) % 7;
  let ahead = target - weekday;
  if (ahead <= 0) ahead += 7;
  const t = new Date(today.year, today.month - 1, today.day + ahead);
  const pad = (x: number) => String(x).padStart(2, "0");
  return `${pad(t.getDate())}.${pad(t.getMonth() + 1)}.${t.getFullYear()}`;
}

export function todayLocal(): { year: number; month: number; day: number } {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate() };
}

// ---------------- главный расчёт ----------------

const STEP_MAP: Record<string, number> = { per_4: 4, per_9: 9, per_person: 5, per_person_one: 1 };

function personNames(names: string[], count: number, lang: Lang): string[] {
  return Array.from({ length: count }, (_, i) => strip(names[i] ?? "") || tr("person_default_name", lang, { i: i + 1 }));
}

export function calculateDistribution(inp: SplitterInput): SplitterResult {
  const lang = inp.lang;
  const divisions = inp.divisions.map((d) => d.people);
  const totalPeople = divisions.reduce((a, b) => a + b, 0);
  const shouldCount = makeShouldCountResourceCost(inp);

  // _collect_quota_entries: дубликаты сливаются до округления
  const merged = new Map<string, number>();
  const undefinedRaw: string[] = [];
  for (const line of splitlines(inp.quotaText)) {
    const parsed = parseCsvLine(line);
    if (!parsed) continue;
    const [cnt, raw] = parsed;
    const name = NORMALIZED.get(raw.toLowerCase());
    if (name !== undefined) add(merged, name, cnt);
    else undefinedRaw.push(raw);
  }
  const itemEntries0 = [...merged];

  const hasFactoryOrAviation = [inp.modsText, inp.equipmentText, inp.aviationText].some((t) => strip(t));
  if (!itemEntries0.length && !hasFactoryOrAviation) {
    return { output: tr("no_valid_entries_error", lang), undefinedLines: null };
  }

  // авиа-предметы в основной квоте -> «Ресурсы на завод»
  const aviationInMain: Array<[number, string, AvSettings, Recipe | undefined]> = [];
  for (const line of splitlines(inp.quotaText)) {
    const parsed = parseAviationQuotaLine(line, inp.avDefaults);
    if (!parsed) continue;
    const [count, name, settings] = parsed;
    const entry = entryOf(name);
    if (entry && entry.is_aviation) aviationInMain.push([count, name, settings, entry.recipe as Recipe | undefined]);
  }

  const itemEntries: Array<[string, number]> = [];
  for (const [name, cnt0] of itemEntries0) {
    const entry = entryOrEmpty(name);
    if (entry.is_aviation) continue;
    const dist = entry.distribution ?? "per_person";
    if (entry.group === 8) {
      itemEntries.push([name, cnt0]);
      continue;
    }
    let step: number | undefined = STEP_MAP[dist];
    if (dist === "per_4" && !inp.enforceMul4) step = undefined;
    const cnt = step && step > 1 ? Math.ceil(cnt0 / step) * step : cnt0;
    itemEntries.push([name, cnt]);
  }

  // _calculate_totals -> среднее на человека для balance_fill
  const totalResources = new Map<string, number>();
  for (const [name, cnt] of itemEntries) {
    const entry = entryOf(name);
    if (!entry || entry.is_aviation) continue;
    const scheme = entry.distribution ?? "per_person";
    if (entry.resource == null || entry.cost_per_box == null) continue;
    for (const [r, c] of resourcePairs(entry)) {
      if (!shouldCount(name, r)) continue;
      const used = scheme === "per_9" ? discountedSum(c, cnt, 9) : scheme === "per_person" ? discountedSum(c, cnt, 5) : c * cnt;
      add(totalResources, r, used);
    }
  }
  const avgPerPerson = new Map<string, number>();
  if (totalPeople) for (const [r, t] of totalResources) avgPerPerson.set(r, t / totalPeople);

  const dist = new Distributor(divisions, shouldCount, inp.enforceMul4, inp.timeBudgetMs ?? 500, unitWeightMap(inp.unitWeights));
  dist.perform(itemEntries, avgPerPerson);

  const totalsFromUsed = new Map<string, number>();
  for (let i = 0; i < dist.n; i++) for (const [r, v] of dist.usedActual[i]) add(totalsFromUsed, r, v);

  const lines: string[] = [tr("totals_header", lang)];
  for (const [r, v] of totalsFromUsed) lines.push(`  ${trResource(r, lang)}: ${floatRepr(v)}`);
  lines.push("", tr("avg_per_person_header", lang));
  if (totalPeople) {
    for (const [r, v] of totalsFromUsed) lines.push(`  ${trResource(r, lang)}: ${floatRepr(pyRoundTo(v / totalPeople, 2))}`);
  }
  lines.push("");

  // базовые ресурсы за самолёты в основной квоте — пропорционально людям
  const perDivBase: BaseTotals[] = divisions.map(() => zeroBase());
  if (aviationInMain.length && totalPeople > 0) {
    const totalBase = zeroBase();
    for (const [count, , settings, recipe] of aviationInMain) addBase(totalBase, aviationBaseCost(recipe, count, settings));
    for (const key of BASE_KEYS) {
      const total = totalBase[key];
      let remaining = total;
      const shares = divisions.map((p) => {
        const share = floorDiv(total * p, totalPeople);
        remaining -= share;
        return share;
      });
      let idx = 0;
      while (remaining > 0) {
        shares[idx] += 1;
        remaining -= 1;
        idx = (idx + 1) % divisions.length;
      }
      shares.forEach((s, i) => (perDivBase[i][key] = s));
    }
  }

  lines.push(...formatDistributionOutput(inp, dist, perDivBase));

  const undefinedLines: UndefinedLine[] = undefinedRaw.map((raw) => {
    if (isSpecialAviation(raw, inp)) return { text: raw + tr("undefined_aviation_suffix", lang), kind: "aviation" };
    if (isOmtoRaw(raw, inp)) return { text: raw + tr("undefined_factory_suffix", lang), kind: "factory" };
    return { text: raw, kind: "unknown" };
  });
  // нераспознанные строки квоты Лётки — тоже в «Неизвестные позиции»
  for (const line of splitlines(inp.aviationText)) {
    const parsed = parseAviationQuotaLine(line, inp.avDefaults);
    if (parsed && !isKnownAviationName(parsed[1])) undefinedLines.push({ text: parsed[1], kind: "unknown" });
  }

  return {
    output: lines.join("\n"),
    undefinedLines,
    allocatorIterations: dist.iterations,
    allocatorConverged: dist.converged,
  };
}

function formatDistributionOutput(inp: SplitterInput, dist: Distributor, perDivBase: BaseTotals[]): string[] {
  const lang = inp.lang;
  const lines: string[] = [];
  const targetDate = nextWeekday(inp.weekdayIndex, inp.today);
  lines.push(`@${inp.unitName}`, "", tr("logistics_plan_header", lang, { date: targetDate }));
  lines.push(tr("main_storage_line", lang, { storage: inp.storageName }));
  lines.push(tr("storage_password_line", lang, { code: inp.storagePass }), "");

  const groupOf = (name: string) => RESOURCE_DB[name].group ?? 999;
  for (let i = 0; i < dist.n; i++) {
    lines.push(inp.divisions[i].name);
    const sorted = [...dist.distribution[i]].sort((a, b) => groupOf(a[0]) - groupOf(b[0]));
    for (const [name, cnt] of sorted) lines.push(`    ${cnt} – ${trItem(name, lang)}`);
    const base = perDivBase[i];
    if (base && BASE_KEYS.some((k) => base[k])) {
      lines.push(tr("factory_resources_header", lang));
      for (const key of BASE_KEYS) if (base[key] > 0) lines.push(`      ${trAviationResource(key, lang)}: ${base[key]}`);
    }
    lines.push("");
  }

  const omto = strip(inp.omtoName);
  if (inp.omtoCount > 0) {
    lines.push(omto ? `=== ${omto} ===` : tr("mto_section_marker", lang));
    lines.push(...buildMtoModificationsOutput(inp));
    lines.push(...buildMtoEquipmentOutput(inp));
  } else {
    if (strip(inp.modsText)) {
      lines.push(omto ? tr("mods_section_header", lang, { name: omto }) : tr("factory_mods_header", lang));
      for (const line of splitlines(inp.modsText)) lines.push(`  ${rstrip(line)}`);
      lines.push("");
    }
    if (strip(inp.equipmentText)) {
      lines.push(omto ? tr("equipment_section_header", lang, { name: omto }) : tr("factory_equipment_header", lang));
      for (const line of splitlines(inp.equipmentText)) lines.push(`  ${rstrip(line)}`);
      lines.push("");
    }
  }

  lines.push(...buildAviationOutput(inp));
  lines.push(tr("resources_spent_header", lang));
  for (let i = 0; i < dist.n; i++) {
    const nm = inp.divisions[i].name;
    lines.push(`${strip(nm) ? nm : tr("division_label", lang, { i: i + 1 })}:`);
    for (const [r, v] of dist.usedActual[i]) lines.push(`  ${trResource(r, lang)}: ${floatRepr(v)}`);
    if (dist.weights) {
      // то, что выравнивалось: ресурсы с весами (бесплатные — по номиналу)
      const units = dist.combinedLoadTotal(i);
      const fmt = (x: number) => String(Math.round(x * 10) / 10);
      lines.push(`  ${tr("units_line", lang, { v: fmt(units), pp: fmt(units / (dist.divisions[i] || 1)) })}`);
    }
  }
  return lines;
}

function argminFirst(xs: number[]): number {
  let idx = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i] < xs[idx]) idx = i;
  return idx;
}

function buildMtoEquipmentOutput(inp: SplitterInput): string[] {
  const lang = inp.lang;
  if (!strip(inp.equipmentText)) return [];
  const n = inp.omtoCount;
  const names = personNames(inp.omtoNames, n, lang);
  if (n === 0 || !names.length) return [];

  const withPrice: Array<[string, number, number]> = [];
  const noPrice: Array<[string, number]> = [];
  for (const line of splitlines(inp.equipmentText)) {
    const parsed = parseCsvLine(line);
    if (!parsed) continue;
    const [cnt, name] = parsed;
    const entry = entryOf(name);
    if (entry && entry.cost_per_box != null) {
      const costs = entry.cost_per_box;
      const costSum = Array.isArray(costs) ? costs.reduce((a, c) => a + (c || 0), 0) : costs || 0;
      withPrice.push([name, cnt, costSum]);
    } else {
      noPrice.push([name, cnt]);
    }
  }

  const perPerson = Array.from({ length: n }, () => new Map<string, number>());
  const loadWith = new Array<number>(n).fill(0);
  const loadNo = new Array<number>(n).fill(0);
  withPrice.sort((a, b) => b[2] - a[2]);
  for (const [name, cnt, cost] of withPrice) {
    for (let left = cnt; left > 0; left--) {
      const idx = argminFirst(loadWith);
      add(perPerson[idx], name, 1);
      loadWith[idx] += cost;
    }
  }
  for (const [name, cnt] of noPrice) {
    for (let left = cnt; left > 0; left--) {
      const idx = argminFirst(loadNo);
      add(perPerson[idx], name, 1);
      loadNo[idx] += 1;
    }
  }

  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    if (!perPerson[i].size) continue;
    out.push(tr("equipment_section_header", lang, { name: names[i] }));
    for (const [name, cnt] of perPerson[i]) out.push(`  ${formatQuotaLine(name, cnt, lang)}`);
  }
  if (out.length) out.push("");
  return out;
}

function buildMtoModificationsOutput(inp: SplitterInput): string[] {
  const lang = inp.lang;
  if (!strip(inp.modsText)) return [];
  const n = inp.omtoCount;
  const names = personNames(inp.omtoNames, n, lang);
  if (n === 0 || !names.length) return [];

  const positions: Array<[string, number]> = [];
  let total = 0;
  for (const line of splitlines(inp.modsText)) {
    const parsed = parseCsvLine(line);
    if (!parsed) continue;
    const [cnt, name] = parsed;
    positions.push([name, cnt]);
    total += cnt;
  }
  if (!positions.length) return [];

  const avg = n ? total / n : 0;
  const perPerson = Array.from({ length: n }, () => new Map<string, number>());
  const loads = new Array<number>(n).fill(0);
  positions.sort((a, b) => b[1] - a[1]);
  for (const [name, cnt] of positions) {
    const minIdx = argminFirst(loads);
    const after = loads[minIdx] + cnt;
    if (cnt <= avg + 1 || after <= avg + cnt / 2) {
      // повтор позиции у того же человека складывается с уже выданным
      add(perPerson[minIdx], name, cnt);
      loads[minIdx] += cnt;
    } else {
      const base = Math.floor(cnt / n);
      const rem = cnt - base * n;
      for (let i = 0; i < n; i++) {
        const portion = base + (i < rem ? 1 : 0);
        if (portion > 0) {
          add(perPerson[i], name, portion);
          loads[i] += portion;
        }
      }
    }
  }

  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    if (!perPerson[i].size) continue;
    out.push(tr("mods_section_header", lang, { name: names[i] }));
    for (const [name, cnt] of perPerson[i]) out.push(`  ${formatQuotaLine(name, cnt, lang)}`);
  }
  if (out.length) out.push("");
  return out;
}

function buildAviationOutput(inp: SplitterInput): string[] {
  const lang = inp.lang;
  if (!strip(inp.aviationText)) return [];
  const n = inp.aviationCount;
  const pilots = personNames(inp.aviationNames, n, lang);
  if (n === 0 || !pilots.length) {
    return [tr("aviation_section_header", lang), tr("aviation_zero_pilots", lang), ""];
  }

  const aviOrders: Array<[number, string, AvSettings, Recipe | undefined]> = [];
  const commonOrders: Array<[number, string]> = [];
  for (const line of splitlines(inp.aviationText)) {
    const parsed = parseAviationQuotaLine(line, inp.avDefaults);
    if (!parsed) continue;
    const [count, name, settings] = parsed;
    const entry = entryOf(name);
    if (entry && entry.is_aviation) aviOrders.push([count, name, settings, entry.recipe as Recipe | undefined]);
    else if (entry) commonOrders.push([count, name]);
    // нет в resources.json, но предмет известен i18n — обычный заказ
    else if (hasItem(name)) commonOrders.push([count, name]);
    else if (hasItem(`${name} (Ящик)`)) commonOrders.push([count, `${name} (Ящик)`]);
    // иначе — в «Неизвестные позиции» (см. calculateDistribution)
  }

  const totalBase = zeroBase();
  for (const [count, , settings, recipe] of aviOrders) addBase(totalBase, aviationBaseCost(recipe, count, settings));
  const perPilotBase = Array.from({ length: n }, () => zeroBase());
  for (const key of BASE_KEYS) {
    const total = totalBase[key];
    const base = floorDiv(total, n);
    const remainder = total - base * n;
    for (let i = 0; i < n; i++) perPilotBase[i][key] = base + (i < remainder ? 1 : 0);
  }
  const perPilotCommon: Array<Array<[number, string]>> = Array.from({ length: n }, () => []);
  for (const [totalCount, name] of commonOrders) {
    const base = floorDiv(totalCount, n);
    const remainder = totalCount - base * n;
    for (let i = 0; i < n; i++) {
      const cnt = base + (i < remainder ? 1 : 0);
      if (cnt > 0) perPilotCommon[i].push([cnt, name]);
    }
  }

  const out = [tr("aviation_section_header", lang)];
  for (let i = 0; i < n; i++) {
    out.push(`  ${pilots[i]}:`);
    for (const [cnt, name] of perPilotCommon[i]) out.push(`    ${cnt} - ${trItem(name, lang)}`);
    for (const key of BASE_KEYS) {
      const v = perPilotBase[i][key];
      if (v > 0) out.push(`    ${trAviationResource(key, lang)}: ${v}`);
    }
  }
  out.push("");
  return out;
}

function isSpecialAviation(raw: string, inp: SplitterInput): boolean {
  if (!raw) return false;
  const rn = normalizeText(raw);
  if (inp.aviationList.some((n) => n && normalizeText(n) === rn)) return true;
  const text = strip(inp.aviationText || "");
  if (text) {
    for (const line of splitlines(text)) {
      if (!line) continue;
      const parsed = parseCsvLine(line);
      const namePart = parsed ? parsed[1] : strip(line);
      if (normalizeText(namePart) === rn) return true;
    }
  }
  return false;
}

function isOmtoRaw(raw: string, inp: SplitterInput): boolean {
  if (!raw) return false;
  const rn = normalizeOmtoName(raw);
  for (const n of inp.omtoList) {
    const s = n ? normalizeText(n) : "";
    if (s && normalizeOmtoName(s) === rn) return true;
  }
  for (const t of [inp.modsText, inp.equipmentText]) {
    const text = strip(t || "");
    if (!text) continue;
    for (const line of splitlines(text)) {
      if (!line) continue;
      const parsed = parseCsvLine(line);
      const namePart = parsed ? parsed[1] : strip(line);
      if (normalizeOmtoName(namePart) === rn) return true;
    }
  }
  return false;
}

// ---------------- «Рассчитать квоту» ----------------

export interface QuotaSplit {
  main: string;
  mods: string;
  equipment: string;
  aviation: string;
}

/** Вычитает склад из необходимого и раскладывает по 4 полям квоты. */
export function calculateQuota(
  storageText: string,
  requiredText: string,
  omtoList: string[],
  aviationList: string[],
  lang: Lang,
): QuotaSplit {
  const sumLines = (text: string) => {
    const m = new Map<string, number>();
    for (const line of splitlines(text)) {
      const parsed = parseCsvLine(line);
      if (parsed) add(m, parsed[1], parsed[0]);
    }
    return m;
  };
  const required = sumLines(requiredText);
  const storage = sumLines(storageText);
  const result: Array<[string, number]> = [];
  for (const [name, need] of required) {
    const diff = need - (storage.get(name) ?? 0);
    if (diff > 0) result.push([name, diff]);
  }

  const omtoSet = new Set(omtoList.filter(Boolean).map(normalizeText));
  const aviationSet = new Set(aviationList.filter(Boolean).map(normalizeText));
  const modsSet = new Set(MTO_MODIFICATIONS);
  const main: string[] = [];
  const mods: string[] = [];
  const equipment: string[] = [];
  const aviation: string[] = [];
  result.sort((a, b) => b[1] - a[1]);
  for (const [name, cnt] of result) {
    const nl = normalizeText(name);
    const line = formatQuotaLine(name, cnt, lang);
    if (aviationSet.has(nl)) aviation.push(line);
    else if (omtoSet.has(nl)) (modsSet.has(name) ? mods : equipment).push(line);
    else main.push(line);
  }
  return { main: main.join("\n"), mods: mods.join("\n"), equipment: equipment.join("\n"), aviation: aviation.join("\n") };
}

// ---------------- диалог цен самолётов ----------------

export interface AviationOrder {
  lineIndex: number;
  count: number;
  name: string;
  settings: AvSettings;
}

/** Авиа-заказы из квоты Лётки (только is_aviation). */
export function aviationOrders(aviationText: string, defaults: AvSettings): AviationOrder[] {
  const out: AviationOrder[] = [];
  splitlines(aviationText).forEach((line, idx) => {
    const parsed = parseAviationQuotaLine(line, defaults);
    if (!parsed) return;
    const [count, name, settings] = parsed;
    const entry = entryOf(name);
    if (!entry || !entry.is_aviation) return;
    out.push({ lineIndex: idx, count, name, settings });
  });
  return out;
}

/** Переписывает строки квоты Лётки под новые дефолты/кастомные настройки. */
export function applyAviationSettings(
  aviationText: string,
  orders: AviationOrder[],
  newDefaults: AvSettings,
  perLine: Map<number, AvSettings>,
  lang: Lang,
): string {
  const lines = splitlines(aviationText);
  for (const o of orders) {
    const s = perLine.get(o.lineIndex) ?? { ...newDefaults };
    lines[o.lineIndex] = serializeAviationQuotaLine(o.count, trItem(o.name, lang), s, newDefaults);
  }
  return lines.join("\n");
}

// ---------------- редактор списков МТО / Лётки ----------------

/** Все предметы для редактора: известные предметы ∪ текущий список, по lower(). */
export function allItemNames(extra: string[]): string[] {
  const names = new Set<string>();
  for (const v of Object.keys(ITEM_I18N)) names.add(v);
  for (const v of extra) names.add(v);
  return [...names].sort((a, b) => cmpStr(a.toLowerCase(), b.toLowerCase()));
}

export function sortedByLower(list: string[]): string[] {
  return [...list].sort((a, b) => cmpStr(a.toLowerCase(), b.toLowerCase()));
}

export const WEEKDAY_NAMES = WEEKDAYS;
