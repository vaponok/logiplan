<script lang="ts">
  // Маленькая кнопка «копировать» в правом верхнем углу текстового поля.
  // Родитель должен быть position: relative (класс .copywrap в app.css).
  import { tr } from "../core/i18n";
  import { toast } from "../lib/dialogs.svelte";
  import { copyText } from "../lib/platform";
  import { app } from "../lib/state.svelte";

  let { text }: { text: string } = $props();
  let done = $state(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function copy() {
    if (!text || !(await copyText(text))) return;
    done = true;
    toast(tr("copied_toast", app.lang));
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => (done = false), 1200);
  }
</script>

<button
  class="copybtn"
  class:done
  disabled={!text}
  title={tr("copy_tooltip", app.lang)}
  aria-label={tr("copy_tooltip", app.lang)}
  onclick={copy}
>
  {#if done}
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"
      ><path d="M3 8.5 L6.5 12 L13 4.5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" /></svg
    >
  {:else}
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"
      ><rect x="5" y="5" width="9" height="9" rx="1.5" fill="none" stroke="#fff" stroke-width="2" /><path
        d="M11 3.2 V2.5 A1 1 0 0 0 10 1.5 H3 A1 1 0 0 0 2 2.5 V9.5 A1 1 0 0 0 3 10.5 H3.2"
        fill="none"
        stroke="#fff"
        stroke-width="2"
      /></svg
    >
  {/if}
</button>

<style>
  .copybtn {
    position: absolute;
    /* правее — полоса прокрутки поля (18 px) и его рамка */
    top: 9px;
    right: 24px;
    width: 34px;
    height: 30px;
    padding: 0;
    display: grid;
    place-items: center;
    border-radius: 8px;
    border: var(--border);
    background: var(--primary);
    cursor: pointer;
    z-index: 1;
    transition:
      background 0.15s,
      opacity 0.15s;
  }
  .copybtn:hover {
    background: var(--primary-hover);
  }
  .copybtn:active {
    background: var(--primary-pressed);
  }
  .copybtn:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
  }
  .copybtn.done {
    background: #28a745;
  }
  .copybtn:disabled {
    opacity: 0.35;
    cursor: default;
  }
</style>
