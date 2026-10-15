// Разбор строк квоты — порт функций верхнего уровня resource_splitter.py.
import { ITEM_I18N, LANGS, hasItem, normalizeText, toCanonicalItemName, trItem, type Lang } from "./i18n";
import { pyInt, strip } from "./py";

// "27 ящ. - 7.92-мм"
const LOOSE_LINE_RE = /^\s*(\d+)\s*(ящ|шт)\.?\s*[-–—]\s*(.+?)\s*$/iu;
// "27 - №.2 Loughcaster (Ящик)" — без единицы; дефис отделён пробелом слева,
// чтобы не съедать CSV-строки вида "40-мм (Ящик),18".
const LOOSE_NOUNIT_RE = /^\s*(\d+)\s+[-–—]\s*(.+?)\s*$/u;
const WAREHOUSE_HEADER_RE = /X:\s*[\d.]+\s+Y:\s*[\d.]+/u;

export const CRATE_SUFFIXES = [" (Ящик)", " (Crate)", " (Caisse)"] as const;
const PACK_TOKENS = new Set(["ящик", "crate", "caisse"]);

/** Токены имени для нечёткого сопоставления. */
function looseTokens(s: string): string[] {
  s = normalizeText(s).replace(/`/g, "'").replace(/ё/g, "е").replace(/№/g, "no ");
  return s.match(/[a-zа-я0-9]+/g) ?? [];
}

type TokenSet = { key: string; tokens: Set<string> };
function tokenSet(name: string): TokenSet {
  const tokens = new Set(looseTokens(name).filter((t) => !PACK_TOKENS.has(t)));
  return { key: [...tokens].sort().join("\u0001"), tokens };
}

interface LoosePool {
  byKey: Map<string, Set<string>>;
  entries: Array<{ tokens: Set<string>; keys: Set<string> }>;
}
let LOOSE_INDEX: [LoosePool, LoosePool] | null = null;

function buildLooseIndex(): [LoosePool, LoosePool] {
  const crated: LoosePool = { byKey: new Map(), entries: [] };
  const uncrated: LoosePool = { byKey: new Map(), entries: [] };
  for (const [key, tr] of Object.entries(ITEM_I18N)) {
    const pool = key.endsWith("(Ящик)") ? crated : uncrated;
    for (const variant of [key, ...LANGS.map((l) => tr[l])]) {
      if (!variant) continue;
      const ts = tokenSet(variant);
      if (!ts.tokens.size) continue;
      let keys = pool.byKey.get(ts.key);
      if (!keys) {
        keys = new Set();
        pool.byKey.set(ts.key, keys);
        pool.entries.push({ tokens: ts.tokens, keys });
      }
      keys.add(key);
    }
  }
  return [crated, uncrated];
}

/**
 * Имя без суффикса "(Ящик)" -> каноническое. unit 'ящ' — сначала ящичные
 * варианты, 'шт' — штучные. 1) точно через i18n; 2) совпадение множества
 * токенов; 3) вхождение токенов. Неоднозначность -> null.
 */
export function resolveLooseName(name: string, unit: string): string | null {
  const toks = tokenSet(name);
  const crated = CRATE_SUFFIXES.map((suf) => `${name}${suf}`);
  const variants = unit === "ящ" ? [...crated, name] : [name, ...crated];
  for (const v of variants) {
    const canon = toCanonicalItemName(v);
    if (hasItem(canon)) return canon;
  }

  if (!LOOSE_INDEX) LOOSE_INDEX = buildLooseIndex();
  if (!toks.tokens.size) return null;
  const pools = unit === "ящ" ? [LOOSE_INDEX[0], LOOSE_INDEX[1]] : [LOOSE_INDEX[1], LOOSE_INDEX[0]];
  for (const matchExact of [true, false]) {
    for (const pool of pools) {
      let hits: Set<string>;
      if (matchExact) {
        hits = pool.byKey.get(toks.key) ?? new Set();
      } else {
        hits = new Set();
        for (const e of pool.entries) {
          let subset = true;
          for (const t of toks.tokens) {
            if (!e.tokens.has(t)) {
              subset = false;
              break;
            }
          }
          if (subset) for (const k of e.keys) hits.add(k);
        }
      }
      if (hits.size === 1) return hits.values().next().value as string;
      if (hits.size > 1) return null;
    }
  }
  return null;
}

/** "N ящ. - Имя" (ящичные, суффикс убирается) или "N шт. - Имя". */
export function formatQuotaLine(name: string, cnt: number, lang: Lang): string {
  const localized = trItem(name, lang);
  for (const suf of CRATE_SUFFIXES) {
    if (localized.endsWith(suf)) return `${cnt} ящ. - ${localized.slice(0, -suf.length)}`;
  }
  return `${cnt} шт. - ${localized}`;
}

/**
 * Универсальный парсер строки квоты: "Имя,число", свободный формат
 * "27 ящ. - 7.92-мм" / "3 шт. - O'Brien V.101 Freeman" и "27 - Имя".
 * Возвращает [count, name] или null; строки с count <= 0 игнорируются.
 */
export function parseCsvLine(line: string): [number, string] | null {
  if (!line || !strip(line)) return null;
  const s = strip(line);
  if (WAREHOUSE_HEADER_RE.test(s)) return null;

  let m = LOOSE_LINE_RE.exec(s);
  if (m) {
    const count = parseInt(m[1], 10);
    const unit = m[2].toLowerCase();
    const raw = m[3];
    if (count <= 0) return null;
    return [count, resolveLooseName(raw, unit) ?? raw];
  }
  m = LOOSE_NOUNIT_RE.exec(s);
  if (m && !s.includes(",")) {
    const count = parseInt(m[1], 10);
    const raw = m[2];
    if (count <= 0) return null;
    return [count, resolveLooseName(raw, "ящ") ?? raw];
  }

  const lastComma = s.lastIndexOf(",");
  if (lastComma === -1) return null;
  const name = strip(s.slice(0, lastComma));
  const count = pyInt(s.slice(lastComma + 1));
  if (!name) return null;
  if (count === null || count <= 0) return null;
  let canon = toCanonicalItemName(name);
  if (!hasItem(canon)) {
    const loose = resolveLooseName(name, "ящ");
    if (loose) canon = loose;
  }
  return [count, canon];
}

// ---------------- квота Лётного отделения ----------------

export type Coke = "with_sulfur" | "no_sulfur";
export type Fuel = "sulfur" | "coal";
export interface AvSettings {
  coke: Coke;
  fuel: Fuel;
  scrap: number; // 0..100, % обработанных через металлолом
}
export const AV_FACTORY_DEFAULTS: AvSettings = { coke: "with_sulfur", fuel: "sulfur", scrap: 100 };

const TRAILING_SETTINGS_RE = /^([\s\S]*?)\s*\[([^\]]*)\]\s*$/u;

/** Содержимое блока [...]: "coke=..., fuel=..., scrap=N" поверх дефолтов. */
function parseAvSettings(settingsRaw: string, defaults: AvSettings): AvSettings {
  const settings: AvSettings = { ...defaults };
  if (settingsRaw) {
    for (let pair of settingsRaw.split(",")) {
      pair = strip(pair);
      const eq = pair.indexOf("=");
      if (eq === -1) continue;
      const k = strip(pair.slice(0, eq)).toLowerCase();
      const v = strip(pair.slice(eq + 1));
      if (k === "coke" && (v === "with_sulfur" || v === "no_sulfur")) settings.coke = v;
      else if (k === "fuel" && (v === "sulfur" || v === "coal")) settings.fuel = v;
      else if (k === "scrap") {
        const n = pyInt(v);
        if (n !== null) settings.scrap = Math.max(0, Math.min(100, n));
      }
    }
  }
  return settings;
}

/**
 * "Имя[ [coke=..., fuel=..., scrap=N]],число" -> [count, name, settings].
 * Также свободный формат "N ящ./шт. - Имя[ [...]]" и "N - Имя[ [...]]",
 * который выдаёт «Рассчитать квоту».
 */
export function parseAviationQuotaLine(
  line: string,
  defaults: AvSettings,
): [number, string, AvSettings] | null {
  if (!line || !strip(line)) return null;
  const s = strip(line);

  // Свободный формат: блок настроек [...] в конце отделяем заранее,
  // чтобы запятые внутри него не мешали распознаванию. Проверка на "]"
  // в конце: s уже обрезана по-питоновски, так что совпадение с Python
  // точное (JS-шный \s, в отличие от питоновского, считает пробелом U+FEFF),
  // а на строках из сплошных "[" регулярка не уходит в квадратичный перебор.
  const m0 = s.endsWith("]") ? TRAILING_SETTINGS_RE.exec(s) : null;
  const body = m0 ? m0[1] : s;
  const looseSettingsRaw = m0 ? m0[2] : "";
  let loose: [number, string, string] | null = null;
  let lm = LOOSE_LINE_RE.exec(body);
  if (lm) {
    loose = [parseInt(lm[1], 10), lm[2].toLowerCase(), lm[3]];
  } else {
    lm = LOOSE_NOUNIT_RE.exec(body);
    if (lm && !body.includes(",")) loose = [parseInt(lm[1], 10), "ящ", lm[2]];
  }
  if (loose) {
    const [looseCount, unit, rawName] = loose;
    if (looseCount <= 0) return null;
    let looseName = resolveLooseName(rawName, unit) ?? rawName;
    looseName = toCanonicalItemName(looseName);
    looseName = strip(looseName.replace(/\s*\(Ящик\)\s*$/u, ""));
    return [looseCount, looseName, parseAvSettings(looseSettingsRaw, defaults)];
  }

  const lastComma = s.lastIndexOf(",");
  if (lastComma === -1) return null;
  const namePart = strip(s.slice(0, lastComma));
  const count = pyInt(s.slice(lastComma + 1));
  if (!namePart) return null;
  if (count === null || count <= 0) return null;

  const m = /^([\s\S]+?)(?:\s*\[([^\]]*)\])?\s*$/u.exec(namePart);
  if (!m) return null;
  let name = strip(m[1]);
  const settingsRaw = m[2] ?? "";

  name = toCanonicalItemName(name);
  name = strip(name.replace(/\s*\(Ящик\)\s*$/u, ""));

  return [count, name, parseAvSettings(settingsRaw, defaults)];
}

/** Обратно в CSV; если всё совпадает с дефолтами — без [...]. */
export function serializeAviationQuotaLine(
  count: number,
  name: string,
  settings: AvSettings,
  defaults: AvSettings,
): string {
  const parts: string[] = [];
  if (settings.coke !== defaults.coke) parts.push(`coke=${settings.coke}`);
  if (settings.fuel !== defaults.fuel) parts.push(`fuel=${settings.fuel}`);
  if (settings.scrap !== defaults.scrap) parts.push(`scrap=${settings.scrap}`);
  if (!parts.length) return `${name},${count}`;
  return `${name} [${parts.join(", ")}],${count}`;
}
