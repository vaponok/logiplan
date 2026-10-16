// Обёртки над окном Tauri; в браузере (npm run dev) — безопасные заглушки.
import { isTauri } from "@tauri-apps/api/core";

type Win = import("@tauri-apps/api/window").Window;
let winPromise: Promise<Win | null> | null = null;

export function appWindow(): Promise<Win | null> {
  if (!winPromise) {
    winPromise = isTauri()
      ? import("@tauri-apps/api/window").then((m) => m.getCurrentWindow())
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

export type ResizeDirection = "East" | "North" | "NorthEast" | "NorthWest" | "South" | "SouthEast" | "SouthWest" | "West";

/** Растягивание окна за прозрачную полосу вокруг него (см. ResizeFrame.svelte). */
export async function startResize(dir: ResizeDirection) {
  await (await appWindow())?.startResizeDragging(dir);
}

/** Скругление и полоса под тень; у развёрнутого окна — ни того, ни другого. */
export function applyFrame(maximized: boolean) {
  const st = document.documentElement.style;
  st.setProperty("--win-radius", maximized ? "0px" : "16px");
  st.setProperty("--win-gutter", maximized ? "0px" : "14px");
}

export async function isMaximized(): Promise<boolean> {
  const w = await appWindow();
  return w ? w.isMaximized() : false;
}

/** Подписка на «развёрнуто/не развёрнуто». */
export async function watchMaximized(cb: (maximized: boolean) => void) {
  const w = await appWindow();
  if (!w) return;
  cb(await w.isMaximized());
  await w.onResized(async () => cb(await w.isMaximized()));
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
