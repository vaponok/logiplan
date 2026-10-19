// Строки интерфейса, которых не было в Python-версии (там их рисовал Qt
// сам или функций не было). Остальные переводы — src/data/i18n.json;
// строки, изменённые по сравнению со старой версией, — tools/data_updates.py.
type Tr = { ru: string; en: string; fr: string };

export const EXTRA_UI_STRINGS: Record<string, Tr> = {
  btn_yes: { ru: "Да", en: "Yes", fr: "Oui" },
  btn_no: { ru: "Нет", en: "No", fr: "Non" },
  btn_ok: { ru: "ОК", en: "OK", fr: "OK" },
  copy_tooltip: { ru: "Копировать", en: "Copy", fr: "Copier" },
  copied_toast: { ru: "Скопировано", en: "Copied", fr: "Copié" },
  calculating: { ru: "Считаю…", en: "Calculating…", fr: "Calcul…" },
  calc_error: { ru: "Ошибка расчёта: {e}", en: "Calculation error: {e}", fr: "Erreur de calcul : {e}" },
  wt_hex_placeholder: { ru: "Гекс склада", en: "Hex", fr: "Hexagone" },
  wt_depot_placeholder: { ru: "Склад", en: "Depot", fr: "Dépôt" },
  // типы складов (tools/depots.py); ru — как на русской вики игры
  wt_depot_storage: { ru: "Складское помещение", en: "Storage Depot", fr: "Dépôt" },
  wt_depot_seaport: { ru: "Морской порт", en: "Seaport", fr: "Port" },
  wt_depot_aircraft: { ru: "Авиадепо", en: "Aircraft Depot", fr: "Dépôt d'aéronefs" },
  wt_password_placeholder: { ru: "Пароль", en: "Password", fr: "Mot de passe" },
  wt_password_error: {
    ru: "Пароль — 6 цифр",
    en: "The password must be 6 digits",
    fr: "Le mot de passe doit comporter 6 chiffres",
  },
  balance_mode_label: { ru: "Распределять поровну:", en: "Balance evenly:", fr: "Équilibrer :" },
  balance_mode_resources: { ru: "каждый ресурс", en: "each resource", fr: "chaque ressource" },
  balance_mode_units: { ru: "условные единицы", en: "weighted units", fr: "unités pondérées" },
  unit_weights_label: {
    ru: "Сколько условных единиц весит 1 ресурс:",
    en: "Units per 1 of each resource:",
    fr: "Unités pour 1 de chaque ressource :",
  },
  units_line: {
    ru: "Условные единицы: {v} (на человека: {pp})",
    en: "Units: {v} (per person: {pp})",
    fr: "Unités : {v} (par personne : {pp})",
  },
  migrated_toast: {
    ru: "Настройки перенесены из старой версии программы",
    en: "Settings imported from the old version",
    fr: "Paramètres importés de l'ancienne version",
  },
};
