<script lang="ts">
  // Окно поверх приложения (затемнение + карточка). Esc — закрыть.
  import type { Snippet } from "svelte";
  let {
    title,
    onclose,
    children,
    footer,
    wide = false,
  }: { title: string; onclose: () => void; children: Snippet; footer?: Snippet; wide?: boolean } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose()} />

<div class="backdrop" role="presentation" onmousedown={(e) => e.target === e.currentTarget && onclose()}>
  <div class="card" class:wide role="dialog" aria-modal="true" aria-label={title}>
    <div class="title">{title}</div>
    <div class="body">{@render children()}</div>
    {#if footer}<div class="footer">{@render footer()}</div>{/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(7, 20, 34, 0.35);
    display: grid;
    place-items: center;
    z-index: 100;
  }
  .card {
    background: #fff;
    border: var(--border);
    border-radius: 12px;
    min-width: 340px;
    max-width: min(560px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    display: flex;
    flex-direction: column;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  }
  .card.wide {
    width: min(760px, calc(100vw - 32px));
    max-width: none;
    min-height: min(500px, calc(100vh - 48px));
  }
  .title {
    font-weight: 700;
    font-size: 15px;
    padding: 12px 16px 6px;
  }
  .body {
    padding: 6px 16px 12px;
    overflow: auto;
    flex: 1;
    white-space: pre-wrap;
  }
  .footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 0 16px 14px;
  }
</style>
