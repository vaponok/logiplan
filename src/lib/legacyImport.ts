// Перенос настроек из старой версии (QSettings в реестре Windows).
// Ключи — как в legacy/resource_splitter.py (save_settings/load_settings)
// и legacy/warehouse_timer.py (save_state).
import { invoke, isTauri } from "@tauri-apps/api/core";
import { AVIATION_DEFAULT, OMTO_DEFAULT, withoutNotFactory } from "../core/splitter";
import { clampInt, ensureLengths, newId, sanitizeAv, splitter, timers, type Warehouse } from "./state.svelte";

interface LegacySettings {
  splitter: Record<string, string>;
  timers: Record<string, string>;
}

const truthy = (v: string | undefined) => v !== undefined && ["true", "True", "1"].includes(v);

function jsonList(v: string | undefined): string[] | null {
  if (!v) return null;
  try {
    const x = JSON.parse(v);
    return Array.isArray(x) ? x.filter((n) => n).map(String) : null;
  } catch {
    return null;
  }
}

/** datetime.isoformat() без часового пояса — локальное время. */
export function parseNaiveIso(s: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/.exec(s.trim());
  if (!m) return null;
  const ms = m[7] ? Math.floor(Number(m[7].padEnd(6, "0")) / 1000) : 0;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], m[6] ? +m[6] : 0, ms);
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

export function applyLegacySplitter(s: Record<string, string>): boolean {
  if (!Object.keys(s).length) return false;
  const t = splitter;
  t.unitName = s.unit_name ?? t.unitName;
  t.storageName = s.storage_name ?? t.storageName;
  t.storagePass = s.storage_pass ?? t.storagePass;
  t.divisionCount = clampInt(s.division_count, 1, 100, 3);
  t.quotaText = s.quota_text ?? t.quotaText;
  t.weekdayIndex = clampInt(s.target_weekday, 0, 6, 4);

  let maxIdx = t.divisionCount - 1;
  for (const k of Object.keys(s)) {
    const m = /^division_(?:name|people)_(\d+)$/.exec(k);
    if (m) maxIdx = Math.max(maxIdx, +m[1]);
  }
  t.divisions = Array.from({ length: maxIdx + 1 }, (_, i) => ({
    name: s[`division_name_${i}`] ?? "",
    people: clampInt(s[`division_people_${i}`], 1, 100, 1),
  }));

  if (s.mods_quota_text === undefined && s.equipment_quota_text === undefined) {
    t.modsText = s.factory_quota_text ?? "";
    t.equipmentText = "";
  } else {
    t.modsText = s.mods_quota_text ?? "";
    t.equipmentText = s.equipment_quota_text ?? "";
  }
  t.omtoName = s.omto_name ?? "";
  t.enforceMul4 = s.enforce_mul4 === undefined ? true : truthy(s.enforce_mul4);
  t.freeEmats = truthy(s.free_emats);
  t.freeHemats = truthy(s.free_hemats);
  t.freeRmats = s.free_rmats !== undefined ? truthy(s.free_rmats) : truthy(s.free_bmats);
  t.omtoList = withoutNotFactory(jsonList(s.omto_custom_list) ?? [...OMTO_DEFAULT]);
  t.aviationList = jsonList(s.aviation_custom_list) ?? [...AVIATION_DEFAULT];
  t.omtoEditorOpen = truthy(s.omto_group_expanded);
  t.aviationEditorOpen = truthy(s.aviation_group_expanded);
  t.aviationText = s.aviation_quota_text ?? "";
  t.storageInput = s.storage_input ?? "";
  t.requiredInput = s.required_input ?? "";
  t.omtoCount = clampInt(s.omto_count, 0, 50, 0);
  t.omtoNames = jsonList(s.omto_names) ?? [];
  t.aviationCount = clampInt(s.aviation_count, 0, 50, 0);
  t.aviationNames = jsonList(s.aviation_names) ?? [];
  t.avDefaults = sanitizeAv({ coke: s.av_default_coke, fuel: s.av_default_fuel, scrap: s.av_default_scrap });
  ensureLengths(t);
  return true;
}

export function applyLegacyTimers(s: Record<string, string>): boolean {
  if (!s.warehouses) return false;
  try {
    const list = JSON.parse(s.warehouses);
    if (!Array.isArray(list)) return false;
    const out: Warehouse[] = [];
    for (const w of list) {
      if (!w || typeof w.name !== "string") continue;
      const expire = typeof w.expire_time === "string" ? parseNaiveIso(w.expire_time) : null;
      out.push({ id: newId(), name: w.name, hex: "", depot: "", password: "", expire: expire ?? Date.now() });
    }
    timers.warehouses = out;
    return out.length > 0;
  } catch {
    return false;
  }
}

/** true — что-то перенесли. */
export async function importLegacy(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const legacy = await invoke<LegacySettings>("import_legacy_settings");
    const a = applyLegacySplitter(legacy.splitter ?? {});
    const b = applyLegacyTimers(legacy.timers ?? {});
    return a || b;
  } catch (e) {
    console.warn("Старые настройки не прочитаны", e);
    return false;
  }
}
