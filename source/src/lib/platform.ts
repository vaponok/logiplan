// Обёртки над окном Tauri; в браузере (npm run dev) — безопасные заглушки.
import { isTauri } from "@tauri-apps/api/core";
import type { ResizeDirection } from "./win";

export type { ResizeDirection };

type Win = import("./win").AppWindow;
let winPromise: Promise<Win | null> | null = null;

export function appWindow(): Promise<Win | null> {
  if (!winPromise) {
    winPromise = isTauri()
      ? import("./win").then((m) => m.getCurrentWindow())
      : Promise.resolve(null);
  }
  return winPromise;
}

export const inTauri = () => isTauri();

export async function minimize() {
  await (await appWindow())?.minimize();
}

export async function toggleMaximize() {
  await (await appWindow())?.toggleMaximize();
}

export async function closeWindow() {
  const w = await appWindow();
  if (w) await w.close();
  else window.close();
}


/** Растягивание окна за прозрачную полосу вокруг него (см. ResizeFrame.svelte). */
export async function startResize(dir: ResizeDirection) {
  await (await appWindow())?.startResizeDragging(dir);
}

/** Перед закрытием окна — дождаться сохранения настроек. */
export async function beforeClose(fn: () => Promise<void>) {
  const w = await appWindow();
  if (w) {
    await w.onCloseRequested(async () => {
      await fn();
    });
  } else {
    window.addEventListener("beforeunload", () => void fn());
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}
