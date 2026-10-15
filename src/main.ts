import "./app.css";
import { mount } from "svelte";
import App from "./App.svelte";
import { tr } from "./core/i18n";
import { toast } from "./lib/dialogs.svelte";
import { importLegacy } from "./lib/legacyImport";
import { beforeClose } from "./lib/platform";
import { app, hydrate } from "./lib/state.svelte";
import { flush, initStorage } from "./lib/storage";

async function start() {
  const data = await initStorage();
  hydrate(data);
  // Первый запуск: пробуем забрать настройки старой Python-версии из реестра.
  const firstRun = !("app" in data);
  const migrated = firstRun ? await importLegacy() : false;

  mount(App, { target: document.getElementById("app")! });
  await beforeClose(flush);
  if (migrated) toast(tr("migrated_toast", app.lang), 5000);
}

void start();
