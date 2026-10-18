import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Чанк core запускается как Worker, поэтому в нём должен оказаться calcHost
// и не должно быть импортов (иначе в Worker поедет код интерфейса и каждый
// расчёт упадёт). Если разбиение на чанки сломается — сборка остановится.
function checkCoreChunk(): Plugin {
  return {
    name: "check-core-chunk",
    apply: "build",
    generateBundle(_opts, bundle) {
      const core = Object.values(bundle).find((c) => c.type === "chunk" && c.name === "core");
      if (!core || core.type !== "chunk") throw new Error("нет чанка core");
      if (!Object.keys(core.modules).some((m) => /[\\/]src[\\/]core[\\/]calcHost\.ts$/.test(m)))
        throw new Error("calcHost.ts не попал в чанк core");
      if (core.imports.length || core.dynamicImports.length)
        throw new Error(`чанк core импортирует другие чанки: ${[...core.imports, ...core.dynamicImports].join(", ")}`);
    },
  };
}

// Tauri ожидает фиксированный порт dev-сервера и не любит, когда Vite
// очищает экран (теряются ошибки сборки Rust).
export default defineConfig({
  plugins: [svelte(), checkCoreChunk()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**", "**/legacy/**"] },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1024,
    // WebView2 сам умеет modulepreload — полифилл не нужен
    modulePreload: false,
    rolldownOptions: {
      // Логика и данные — отдельным чанком: его же запускает фоновый Worker
      // (src/core/calcHost.ts), так что код и данные не лежат в exe дважды.
      // [\\/] — сборка exe идёт на Windows.
      output: { codeSplitting: { groups: [{ name: "core", test: /[\\/]src[\\/](core|data)[\\/]/ }] } },
    },
  },
  test: {
    include: ["tests/**/*.test.ts"],
    testTimeout: 60000,
  },
});
