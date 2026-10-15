<script lang="ts">
  // Собственный заголовок окна: иконка, вкладки, флаги языков, кнопки окна.
  // Тащить окно можно за любое пустое место заголовка (data-tauri-drag-region),
  // двойной щелчок по нему разворачивает окно.
  import { LANGS, tr, type Lang } from "../core/i18n";
  import { app } from "../lib/state.svelte";
  import { closeWindow, minimize, toggleMaximize } from "../lib/platform";
  import Flag from "./Flag.svelte";

  let { maximized = false }: { maximized?: boolean } = $props();
  const tabs = ["tab_splitter", "tab_quota", "tab_timers"];
  const flagTips: Record<Lang, string> = { ru: "lang_ru_tooltip", en: "lang_en_tooltip", fr: "lang_fr_tooltip" };
</script>

<header class="titlebar" data-tauri-drag-region>
  <img class="icon" src="/icon.png" alt="" width="28" height="28" draggable="false" />
  <div class="spacer" data-tauri-drag-region></div>
  <!-- вкладки и флаги в одной строке: флаги по центру высоты вкладок -->
  <div class="tabrow">
    <div class="tabs" role="tablist">
      {#each tabs as key, i (key)}
        <button
          class="tab"
          class:selected={app.tab === i}
          role="tab"
          aria-selected={app.tab === i}
          onclick={() => (app.tab = i)}>{tr(key, app.lang)}</button
        >
      {/each}
    </div>
    <div class="flags">
      {#each LANGS as code (code)}
        <button
          class="flag"
          class:checked={app.lang === code}
          title={tr(flagTips[code], app.lang)}
          aria-label={tr(flagTips[code], app.lang)}
          onclick={() => (app.lang = code)}
        >
          <Flag kind={code} />
        </button>
      {/each}
    </div>
  </div>
  <div class="grow" data-tauri-drag-region></div>
  <div class="winbtns">
    <button class="winbtn" title={tr("btn_minimize", app.lang)} onclick={minimize}>─</button>
    <button class="winbtn" title={tr("btn_maximize", app.lang)} onclick={toggleMaximize} aria-label={tr("btn_maximize", app.lang)}>
      {#if maximized}
        <svg width="20" height="20" viewBox="0 0 20 20"
          ><rect x="2" y="6" width="12" height="12" fill="none" stroke="#fff" stroke-width="2" /><path
            d="M6 6 V2 H18 V14 H14"
            fill="none"
            stroke="#fff"
            stroke-width="2"
          /></svg
        >
      {:else}
        <svg width="20" height="20" viewBox="0 0 20 20"><rect x="2" y="2" width="16" height="16" fill="none" stroke="#fff" stroke-width="2" /></svg>
      {/if}
    </button>
    <button class="winbtn" title={tr("btn_close", app.lang)} onclick={closeWindow}>✕</button>
  </div>
</header>

<style>
  .titlebar {
    height: 64px;
    flex: none;
    display: flex;
    align-items: flex-end;
    gap: 8px;
    padding: 6px 8px 0;
    background: #fff;
    user-select: none;
  }
  .icon {
    align-self: center;
    margin-bottom: 0;
  }
  .spacer {
    width: 42px;
    align-self: stretch;
  }
  .grow {
    flex: 1;
    align-self: stretch;
  }
  .tabrow {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .tabs {
    display: flex;
    align-items: flex-end;
    gap: 2px;
  }
  .tab {
    background: var(--primary);
    color: #fff;
    border: var(--border);
    border-bottom-color: var(--primary);
    border-radius: 8px 8px 0 0;
    padding: 8px 18px;
    min-height: 36px;
    font-size: 14px;
    cursor: pointer;
    transition:
      padding 0.25s cubic-bezier(0.22, 0.61, 0.36, 1),
      background 0.2s;
  }
  .tab.selected {
    background: var(--primary-pressed);
    border-bottom-color: var(--primary-pressed);
    font-weight: 800;
    padding: 8px 30px;
  }
  .flags {
    display: flex;
    gap: 6px;
    padding-left: 10px;
  }
  .flag {
    width: 38px;
    height: 26px;
    padding: 0;
    border-radius: 5px;
    border: 2px solid #000;
    background: transparent;
    display: grid;
    place-items: center;
    overflow: hidden;
    cursor: pointer;
  }
  .flag:hover {
    border-color: var(--primary-hover);
  }
  .flag.checked {
    border: 3px solid var(--primary);
  }
  .winbtns {
    display: flex;
    gap: 8px;
    align-self: center;
  }
  .winbtn {
    width: 36px;
    height: 28px;
    border-radius: 6px;
    padding: 0;
    font-weight: 700;
    border: 3px solid #000;
    background: var(--primary);
    color: #fff;
    display: grid;
    place-items: center;
    cursor: pointer;
  }
  .winbtn:hover {
    background: var(--primary-hover);
  }
  .winbtn:active {
    background: var(--primary-pressed);
  }
</style>
