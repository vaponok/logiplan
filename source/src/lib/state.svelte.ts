// Состояние приложения (Svelte 5 runes) + приведение загруженных данных.
import { isLang, type Lang } from "../core/i18n";
import { AV_FACTORY_DEFAULTS, type AvSettings } from "../core/quotaParse";
import { AVIATION_DEFAULT, OMTO_DEFAULT, withoutNotFactory, type Division, type UndefinedLine } from "../core/splitter";

export interface SplitterState {
  storageInput: string;
  requiredInput: string;
  unitName: string;
  storageName: string;
  storagePass: string;
  weekdayIndex: number;
  divisionCount: number;
  /** Не обрезается при уменьшении числа подразделений — имена вернутся. */
  divisions: Division[];
  quotaText: string;
  omtoName: string;
  omtoCount: number;
  omtoNames: string[];
  modsText: string;
  equipmentText: string;
  aviationCount: number;
  aviationNames: string[];
  aviationText: string;
  enforceMul4: boolean;
  freeEmats: boolean;
  freeHemats: boolean;
  freeRmats: boolean;
  omtoList: string[];
  aviationList: string[];
  omtoEditorOpen: boolean;
  aviationEditorOpen: boolean;
  /** Разделы «Завод», «МТО» и «Лётное отделение» развёрнуты. */
  factoryOpen: boolean;
  omtoOpen: boolean;
  aviationOpen: boolean;
  avDefaults: AvSettings;
}

export interface Warehouse {
  id: string;
  name: string;
  /** Регион (src/data/depots.json) или пусто. */
  hex: string;
  /** Тип склада: storage, seaport, aircraft или пусто. */
  depotType: string;
  /** Город, по которому назван склад. */
  depot: string;
  /** 6 цифр или пусто. */
  password: string;
  /** Момент истечения, мс с 1970 (UTC). */
  expire: number;
}

export const defaultSplitter = (): SplitterState => ({
  storageInput: "",
  requiredInput: "",
  unitName: "",
  storageName: "",
  storagePass: "",
  weekdayIndex: 4,
  divisionCount: 3,
  divisions: [],
  quotaText: "",
  omtoName: "",
  omtoCount: 0,
  omtoNames: [],
  modsText: "",
  equipmentText: "",
  aviationCount: 0,
  aviationNames: [],
  aviationText: "",
  enforceMul4: true,
  freeEmats: false,
  freeHemats: false,
  freeRmats: false,
  omtoList: [...OMTO_DEFAULT],
  aviationList: [...AVIATION_DEFAULT],
  omtoEditorOpen: false,
  aviationEditorOpen: false,
  factoryOpen: true,
  omtoOpen: true,
  aviationOpen: true,
  avDefaults: { ...AV_FACTORY_DEFAULTS },
});

export const app = $state({ lang: "ru" as Lang, tab: 0 });
export const splitter = $state<SplitterState>(defaultSplitter());
export const quotaWriter = $state({ notes: "", qty: 1, page: 0 });
export const timers = $state({ warehouses: [] as Warehouse[] });
/** Результат последнего расчёта — не сохраняется, как и в старой версии. */
export const results = $state({ output: "", undefinedLines: [] as UndefinedLine[], busy: false });

// ---------------- приведение типов ----------------

const str = (v: unknown, d = "") => (typeof v === "string" ? v : d);
const bool = (v: unknown, d: boolean) => (typeof v === "boolean" ? v : d);
export const clampInt = (v: unknown, lo: number, hi: number, d: number) => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.trunc(n))) : d;
};
const strList = (v: unknown): string[] | null =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : null;

export function sanitizeAv(v: unknown): AvSettings {
  const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
  return {
    coke: o.coke === "no_sulfur" ? "no_sulfur" : o.coke === "with_sulfur" ? "with_sulfur" : AV_FACTORY_DEFAULTS.coke,
    fuel: o.fuel === "coal" ? "coal" : o.fuel === "sulfur" ? "sulfur" : AV_FACTORY_DEFAULTS.fuel,
    scrap: clampInt(o.scrap, 0, 100, AV_FACTORY_DEFAULTS.scrap),
  };
}

export function sanitizeSplitter(v: unknown): SplitterState {
  const d = defaultSplitter();
  const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
  const divisions = Array.isArray(o.divisions)
    ? o.divisions.map((x) => {
        const r = (x && typeof x === "object" ? x : {}) as Record<string, unknown>;
        return { name: str(r.name), people: clampInt(r.people, 1, 100, 1) };
      })
    : d.divisions;
  return {
    storageInput: str(o.storageInput),
    requiredInput: str(o.requiredInput),
    unitName: str(o.unitName),
    storageName: str(o.storageName),
    storagePass: str(o.storagePass),
    weekdayIndex: clampInt(o.weekdayIndex, 0, 6, d.weekdayIndex),
    divisionCount: clampInt(o.divisionCount, 1, 100, d.divisionCount),
    divisions,
    quotaText: str(o.quotaText),
    omtoName: str(o.omtoName),
    omtoCount: clampInt(o.omtoCount, 0, 50, 0),
    omtoNames: strList(o.omtoNames) ?? [],
    modsText: str(o.modsText),
    equipmentText: str(o.equipmentText),
    aviationCount: clampInt(o.aviationCount, 0, 50, 0),
    aviationNames: strList(o.aviationNames) ?? [],
    aviationText: str(o.aviationText),
    enforceMul4: bool(o.enforceMul4, d.enforceMul4),
    freeEmats: bool(o.freeEmats, false),
    freeHemats: bool(o.freeHemats, false),
    freeRmats: bool(o.freeRmats, false),
    omtoList: withoutNotFactory(strList(o.omtoList)?.filter(Boolean) ?? d.omtoList),
    aviationList: strList(o.aviationList)?.filter(Boolean) ?? d.aviationList,
    omtoEditorOpen: bool(o.omtoEditorOpen, false),
    aviationEditorOpen: bool(o.aviationEditorOpen, false),
    factoryOpen: bool(o.factoryOpen, true),
    omtoOpen: bool(o.omtoOpen, true),
    aviationOpen: bool(o.aviationOpen, true),
    avDefaults: sanitizeAv(o.avDefaults),
  };
}

export const DEPOT_TYPES = ["storage", "seaport", "aircraft"];

export function sanitizeWarehouses(v: unknown): Warehouse[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) => (x && typeof x === "object" ? (x as Record<string, unknown>) : null))
    .filter((x): x is Record<string, unknown> => !!x && typeof x.name === "string" && typeof x.expire === "number")
    .map((x) => ({
      id: str(x.id) || newId(),
      name: x.name as string,
      hex: str(x.hex),
      depotType: DEPOT_TYPES.includes(str(x.depotType)) ? str(x.depotType) : "",
      depot: str(x.depot),
      password: str(x.password).replace(/\D/g, "").slice(0, 6),
      expire: x.expire as number,
    }));
}

export function newId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

/** Подтянуть массивы до текущих счётчиков (новые поля — пустые). */
export function ensureLengths(s: SplitterState) {
  while (s.divisions.length < s.divisionCount) s.divisions.push({ name: "", people: 1 });
  while (s.omtoNames.length < s.omtoCount) s.omtoNames.push("");
  while (s.aviationNames.length < s.aviationCount) s.aviationNames.push("");
}

export function hydrate(data: Record<string, unknown>) {
  const a = (data.app ?? {}) as Record<string, unknown>;
  if (isLang(a.lang)) app.lang = a.lang;
  app.tab = clampInt(a.tab, 0, 2, 0);
  Object.assign(splitter, sanitizeSplitter(data.splitter));
  ensureLengths(splitter);
  const q = (data.quotaWriter ?? {}) as Record<string, unknown>;
  quotaWriter.notes = str(q.notes);
  quotaWriter.qty = clampInt(q.qty, 1, 999999, 1);
  quotaWriter.page = clampInt(q.page, 0, 11, 0);
  timers.warehouses = sanitizeWarehouses((data.timers as Record<string, unknown> | undefined)?.warehouses);
}
