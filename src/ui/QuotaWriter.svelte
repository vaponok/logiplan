<script lang="ts">
  // Вкладка «Написание квоты»: страницы с кнопками-картинками; щелчок
  // дописывает «Название,количество» в поле квоты.
  import pagesJson from "../data/quotaPages.json";
  import { tr, trItem } from "../core/i18n";
  import { app, quotaWriter as q } from "../lib/state.svelte";
  import CopyButton from "./CopyButton.svelte";
  import NumberField from "./NumberField.svelte";

  interface Btn {
    key: string;
    index: number;
    item: string | null;
    image: string | null;
    imageBasename: string;
  }
  interface Page {
    page: number;
    scroll: boolean;
    white: boolean;
    navIcon: string | null;
    buttons: Btn[];
  }
  const pages = pagesJson.pages as Page[];
  const L = $derived(app.lang);
  const current = $derived(pages[q.page] ?? pages[0]);

  let notesEl: HTMLTextAreaElement | undefined = $state();

  function press(b: Btn) {
    const n = q.qty;
    // без подписи — имя файла картинки, как button_clicked() в quota_writer.py
    const line = b.item ? `${trItem(b.item, app.lang)},${n}` : `${b.imageBasename},${n}`;
    q.notes = q.notes ? `${q.notes}\n${line}` : line;
    // прокрутить поле к новой строке, как QTextEdit.append
    queueMicrotask(() => notesEl && (notesEl.scrollTop = notesEl.scrollHeight));
  }
</script>

<div class="qw">
  <div class="left">
    <nav class="nav">
      {#each pages as p, i (p.page)}
        <button class="navbtn" class:checked={q.page === i} onclick={() => (q.page = i)} aria-label={String(i + 1)}>
          {#if p.navIcon}
            <img src="/images/{p.navIcon}" alt={String(i + 1)} draggable="false" />
          {:else}
            {i + 1}
          {/if}
        </button>
      {/each}
    </nav>
    <div class="pagebox" class:white={current.white}>
      <div class="grid">
        {#each current.buttons as b (b.key)}
          <button class="imgbtn" title={b.item ? trItem(b.item, L) : ""} onclick={() => press(b)}>
            {#if b.image}
              <img src="/images/{b.image}" alt={b.item ? trItem(b.item, L) : ""} loading="lazy" draggable="false" />
            {:else}
              B{b.index}
            {/if}
          </button>
        {/each}
      </div>
    </div>
  </div>

  <div class="right">
    <div class="qty">
      <span>{tr("qty_label", L)}</span>
      <NumberField value={q.qty} min={1} max={999999} width="100px" title={tr("qty_tooltip", L)} onchange={(v) => (q.qty = v)} />
    </div>
    <span class="lbl">{tr("quota_label", L)}</span>
    <div class="copywrap notes-wrap">
      <textarea class="area notes" bind:this={notesEl} placeholder={tr("notes_placeholder", L)} bind:value={q.notes}></textarea>
      <CopyButton text={q.notes} />
    </div>
  </div>
</div>

<style>
  .qw {
    display: flex;
    gap: 12px;
    height: 100%;
    padding: 8px;
    min-height: 0;
  }
  .left {
    flex: 4;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .right {
    flex: 1;
    min-width: 340px;
    display: flex;
    flex-direction: column;
  }
  .nav {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .navbtn {
    width: 64px;
    height: 64px;
    padding: 0;
    background: #2b2b2b;
    color: #e6e6e6;
    border: 1px solid #444;
    border-radius: 6px;
    overflow: hidden;
    display: grid;
    place-items: center;
    cursor: pointer;
    font-weight: 700;
  }
  .navbtn img {
    max-width: 64px;
    max-height: 64px;
    object-fit: contain;
  }
  .navbtn:active,
  .imgbtn:active {
    background: #1f1f1f;
  }
  .navbtn.checked {
    outline: 3px solid var(--primary);
    outline-offset: -3px;
  }
  .pagebox {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 10px;
    border-radius: 8px;
  }
  .pagebox.white {
    background: #fff;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, 150px);
    gap: 10px;
    max-width: calc(6 * 150px + 5 * 10px);
  }
  .imgbtn {
    width: 150px;
    height: 150px;
    padding: 0;
    background: #2b2b2b;
    color: #e6e6e6;
    border: 1px solid #444;
    border-radius: 6px;
    overflow: hidden;
    cursor: pointer;
  }
  .imgbtn img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: fill;
  }
  .qty {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .notes-wrap {
    flex: 1;
    min-height: 200px;
    display: flex;
  }
  .notes {
    flex: 1;
    padding: 10px 66px 10px 10px;
    resize: none;
    background: #fff;
  }
</style>
