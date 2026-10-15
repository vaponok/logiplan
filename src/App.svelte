<script lang="ts">
  import { onMount } from "svelte";
  import { save } from "./lib/storage";
  import { watchMaximized } from "./lib/platform";
  import { app, quotaWriter, splitter, timers } from "./lib/state.svelte";
  import TitleBar from "./ui/TitleBar.svelte";
  import Splitter from "./ui/Splitter.svelte";
  import QuotaWriter from "./ui/QuotaWriter.svelte";
  import Timers from "./ui/Timers.svelte";
  import DialogHost from "./ui/DialogHost.svelte";

  const TABS = 3;
  let maximized = $state(false);
  onMount(() => {
    void watchMaximized((m) => (maximized = m));
  });

  // Любое изменение состояния — отложенная запись на диск.
  $effect(() => save("app", $state.snapshot(app)));
  $effect(() => save("splitter", $state.snapshot(splitter)));
  $effect(() => save("quotaWriter", $state.snapshot(quotaWriter)));
  $effect(() => save("timers", $state.snapshot(timers)));

  $effect(() => {
    document.documentElement.lang = app.lang;
  });
  // Развёрнутое окно — без скруглений (их видно бы было по краям экрана).
  $effect(() => {
    document.documentElement.style.setProperty("--win-radius", maximized ? "0px" : "16px");
  });
</script>

<div class="window" class:maximized>
  <TitleBar {maximized} />
  <main class="stack">
    <!-- Все вкладки остаются в DOM (состояние полей сохраняется) и стоят
         в ряд; переключение — сдвиг ленты вбок. Неактивные — inert:
         в них не попасть клавишей Tab. -->
    <div class="track" style:transform="translateX(-{(app.tab * 100) / TABS}%)">
      <section class="page" inert={app.tab !== 0} aria-hidden={app.tab !== 0}>
        <div class="canvas"><Splitter /></div>
      </section>
      <section class="page" inert={app.tab !== 1} aria-hidden={app.tab !== 1}><QuotaWriter /></section>
      <section class="page" inert={app.tab !== 2} aria-hidden={app.tab !== 2}><Timers /></section>
    </div>
  </main>
</div>
<DialogHost />

<style>
  .window {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #fff;
    border-radius: var(--win-radius);
    overflow: hidden;
    position: relative;
  }
  /* тонкий контур поверх содержимого, чтобы окно не терялось на светлом фоне */
  .window::after {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: inherit;
    box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.35);
    pointer-events: none;
    z-index: 50;
  }
  .window.maximized::after {
    display: none;
  }
  .stack {
    flex: 1;
    min-height: 0;
    padding: 8px 0;
    border-top: var(--border);
    overflow: hidden;
  }
  .track {
    display: flex;
    width: 300%;
    height: 100%;
    /* без will-change: постоянный GPU-слой отключал бы ClearType у текста */
    transition: transform 0.38s cubic-bezier(0.22, 0.61, 0.36, 1);
  }
  .page {
    width: calc(100% / 3);
    flex: none;
    height: 100%;
    min-height: 0;
    padding: 0 8px;
  }
  .canvas {
    height: 100%;
    overflow-y: auto;
    border: var(--border);
    border-radius: 12px;
  }
  @media (prefers-reduced-motion: reduce) {
    .track {
      transition: none;
    }
  }
</style>
