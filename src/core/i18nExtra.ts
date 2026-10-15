// Строки интерфейса, которых не было в Python-версии (там их рисовал Qt
// сам или функций не было). Остальные переводы — src/data/i18n.json.
type Tr = { ru: string; en: string; fr: string };

export const EXTRA_UI_STRINGS: Record<string, Tr> = {
  btn_yes: { ru: "Да", en: "Yes", fr: "Oui" },
  btn_no: { ru: "Нет", en: "No", fr: "Non" },
  btn_ok: { ru: "ОК", en: "OK", fr: "OK" },
  btn_restore: { ru: "Восстановить", en: "Restore", fr: "Restaurer" },
  copy_tooltip: { ru: "Копировать", en: "Copy", fr: "Copier" },
  copied_toast: { ru: "Скопировано", en: "Copied", fr: "Copié" },
  calculating: { ru: "Считаю…", en: "Calculating…", fr: "Calcul…" },
  calc_error: { ru: "Ошибка расчёта: {e}", en: "Calculation error: {e}", fr: "Erreur de calcul : {e}" },
  migrated_toast: {
    ru: "Настройки перенесены из старой версии программы",
    en: "Settings imported from the old version",
    fr: "Paramètres importés de l'ancienne version",
  },
};
