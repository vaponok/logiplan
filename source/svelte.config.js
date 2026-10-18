import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  preprocess: vitePreprocess(),
  // все компоненты на рунах: без кода старого режима в сборке
  compilerOptions: { runes: true },
};
