import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Tauri ожидает фиксированный порт dev-сервера и не любит, когда Vite
// очищает экран (теряются ошибки сборки Rust).
export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**", "**/legacy/**"] },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1024,
  },
  worker: { format: "es" },
  test: {
    include: ["tests/**/*.test.ts"],
    testTimeout: 60000,
  },
});
