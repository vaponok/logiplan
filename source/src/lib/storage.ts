// Постоянное хранилище настроек.
// В exe (Tauri) — файл settings.json в папке данных приложения
// (%APPDATA%\com.vaponok.logiplan\), в браузере (npm run dev) — localStorage.
import { isTauri } from "@tauri-apps/api/core";

type Data = Record<string, unknown>;

interface Backend {
  loadAll(): Promise<Data>;
  write(key: string, value: unknown): Promise<void>;
  flush(): Promise<void>;
}

const LS_PREFIX = "logiplan:";

const localBackend: Backend = {
  async loadAll() {
    const out: Data = {};
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (!k || !k.startsWith(LS_PREFIX)) continue;
        try {
          out[k.slice(LS_PREFIX.length)] = JSON.parse(localStorage.getItem(k) ?? "null");
        } catch {
          /* битая запись — пропускаем */
        }
      }
    } catch {
      /* localStorage недоступен */
    }
    return out;
  },
  async write(key, value) {
    try {
      localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
    } catch {
      /* нет места / запрещено — работаем без сохранения */
    }
  },
  async flush() {},
};

async function tauriBackend(): Promise<Backend> {
  const { load } = await import("@tauri-apps/plugin-store");
  const store = await load("settings.json", { autoSave: false, defaults: {} });
  return {
    async loadAll() {
      return Object.fromEntries(await store.entries());
    },
    async write(key, value) {
      await store.set(key, value);
    },
    async flush() {
      await store.save();
    },
  };
}

let backend: Backend = localBackend;
const pending = new Map<string, unknown>();
let timer: ReturnType<typeof setTimeout> | null = null;
let chain: Promise<void> = Promise.resolve();

export async function initStorage(): Promise<Data> {
  if (isTauri()) {
    try {
      backend = await tauriBackend();
    } catch (e) {
      console.error("Хранилище Tauri недоступно, использую localStorage", e);
    }
  }
  return backend.loadAll();
}

/** Отложенная запись (пачкой раз в 400 мс). */
export function save(key: string, value: unknown) {
  pending.set(key, value);
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => void flush(), 400);
}

/** Немедленно записать всё отложенное на диск. */
export function flush(): Promise<void> {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  const batch = [...pending];
  pending.clear();
  chain = chain.then(async () => {
    try {
      for (const [k, v] of batch) await backend.write(k, v);
      await backend.flush();
    } catch (e) {
      console.error("Не удалось сохранить настройки", e);
    }
  });
  return chain;
}
