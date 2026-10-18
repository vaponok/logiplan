// Порт legacy/i18n.py. Канонический идентификатор предмета — русское имя
// (ключ resources.json); язык влияет только на то, что видит пользователь.
// именованный импорт: в сборку попадают только используемые части JSON
import { aviationResources, defaultLang, items, langs, resources, ui, weekdays } from "../data/i18n.json";
import { EXTRA_UI_STRINGS } from "./i18nExtra";
import { pyFormat, splitWs, strip } from "./py";

export type Lang = "ru" | "en" | "fr";
type Tr = Partial<Record<Lang, string>>;

export const LANGS: readonly Lang[] = langs as Lang[];
export const DEFAULT_LANG: Lang = defaultLang as Lang;

/** Переводы предметов. В JSON нет повторов: русское имя — это ключ,
 *  французское, совпадающее с английским, опущено (см. tools/export_data.py). */
export const ITEM_I18N: Record<string, Tr> = items as Record<string, Tr>;
const UI_STRINGS: Record<string, Tr> = { ...(ui as Record<string, Tr>), ...EXTRA_UI_STRINGS };
const RESOURCE_LABELS: Record<string, Tr> = resources as Record<string, Tr>;
const AVIATION_RESOURCE_LABELS: Record<string, Tr> = aviationResources as Record<string, Tr>;
export const WEEKDAYS: Record<Lang, string[]> = weekdays as Record<Lang, string[]>;

export function isLang(x: unknown): x is Lang {
  return typeof x === "string" && (LANGS as readonly string[]).includes(x);
}

/** i18n.normalize_text: умные кавычки -> ASCII, схлопнуть пробелы, lower(). */
export function normalizeText(s: string): string {
  if (!s) return s;
  s = s.replace(/’/g, "'").replace(/‘/g, "'");
  s = s.replace(/“/g, '"').replace(/”/g, '"');
  s = s.replace(/„/g, '"');
  s = splitWs(s).join(" ");
  return strip(s).toLowerCase();
}

const REVERSE_ITEM = new Map<string, string>();
for (const [ru, tr] of Object.entries(ITEM_I18N)) {
  REVERSE_ITEM.set(normalizeText(ru), ru);
  for (const lang of LANGS) {
    const val = tr[lang];
    if (val) REVERSE_ITEM.set(normalizeText(val), ru);
  }
}

export function hasItem(name: string): boolean {
  return Object.prototype.hasOwnProperty.call(ITEM_I18N, name);
}

/** Имя предмета на любом из трёх языков -> канонический русский ключ. */
export function toCanonicalItemName(name: string): string {
  if (!name) return name;
  if (hasItem(name)) return name;
  return REVERSE_ITEM.get(normalizeText(name)) ?? name;
}

/** Отображаемое имя предмета на языке lang. */
export function trItem(name: string, lang: Lang): string {
  const canon = toCanonicalItemName(name);
  const entry = hasItem(canon) ? ITEM_I18N[canon] : undefined;
  if (!entry) return name;
  return entry[lang] ?? (lang === "fr" ? entry.en : undefined) ?? canon;
}

/** Перевод статичной UI-строки; незнакомый ключ -> сам ключ. */
export function tr(key: string, lang: Lang, fmt?: Record<string, unknown>): string {
  const entry = UI_STRINGS[key];
  if (!entry) return key;
  const text = entry[lang] ?? entry[DEFAULT_LANG] ?? key;
  if (fmt && Object.keys(fmt).length) {
    try {
      return pyFormat(text, fmt);
    } catch {
      return text;
    }
  }
  return text;
}

export function trResource(key: string, lang: Lang): string {
  return RESOURCE_LABELS[key]?.[lang] ?? key;
}

export function trAviationResource(key: string, lang: Lang): string {
  return AVIATION_RESOURCE_LABELS[key]?.[lang] ?? key;
}
