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
  wt_password_placeholder: { ru: "Пароль", en: "Password", fr: "Mot de passe" },
  wt_password_error: {
    ru: "Пароль — 6 цифр",
    en: "The password must be 6 digits",
    fr: "Le mot de passe doit comporter 6 chiffres",
  },
  migrated_toast: {
    ru: "Настройки перенесены из старой версии программы",
    en: "Settings imported from the old version",
    fr: "Paramètres importés de l'ancienne version",
  },
};
