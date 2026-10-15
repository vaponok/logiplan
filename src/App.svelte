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
</script>

<div class="window" class:maximized>
  <TitleBar {maximized} />
  <main class="stack">
    <!-- Вкладки не пересоздаются при переключении: состояние полей сохраняется -->
    <div class="page scroll canvas" hidden={app.tab !== 0}><Splitter /></div>
    <div class="page" hidden={app.tab !== 1}><QuotaWriter /></div>
    <div class="page" hidden={app.tab !== 2}><Timers /></div>
  </main>
</div>
<DialogHost />

<style>
  .window {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #fff;
  }
  .stack {
    flex: 1;
    min-height: 0;
    padding: 8px;
    border-top: var(--border);
  }
  .page {
    height: 100%;
    min-height: 0;
  }
  .page[hidden] {
    display: none;
  }
  .scroll {
    overflow-y: auto;
  }
  .canvas {
    border: var(--border);
    border-radius: 12px;
  }
</style>
