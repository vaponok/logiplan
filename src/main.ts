import "./app.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { tr } from "./core/i18n";
import { toast } from "./lib/dialogs.svelte";
import { importLegacy } from "./lib/legacyImport";
import { applyFrame, computeFrame } from "./lib/frame.svelte";
import { beforeClose } from "./lib/platform";
import { app, hydrate } from "./lib/state.svelte";
import { flush, initStorage } from "./lib/storage";

async function start() {
  const data = await initStorage();
  hydrate(data);
  // Первый запуск: пробуем забрать настройки старой Python-версии из реестра.
  const firstRun = !("app" in data);
  const migrated = firstRun ? await importLegacy() : false;

  // рамку окна — до первого кадра, чтобы развёрнутое окно не мелькнуло тенью
  const f = await computeFrame().catch(() => null);
  if (f) applyFrame(f);
  mount(App, { target: document.getElementById("app")! });
  await beforeClose(flush);
  if (migrated) toast(tr("migrated_toast", app.lang), 5000);
}

// Браузерное меню по правой кнопке («Назад», «Обновить», «Печать») в
// программе ни к чему; в полях ввода оставляем — там копировать/вставить.
document.addEventListener("contextmenu", (e) => {
  const t = e.target as HTMLElement | null;
  if (t?.closest("input, textarea, [contenteditable='true']")) return;
  e.preventDefault();
});

void start();
