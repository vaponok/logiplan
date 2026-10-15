<script lang="ts">
  // Редактор «Все предметы ↔ выбранные» для МТО и Лётного отделения.
  import { tr, trItem, type Lang } from "../core/i18n";
  import { allItemNames, sortedByLower } from "../core/splitter";
  import { confirmDialog } from "../lib/dialogs.svelte";
  import ItemList from "./ItemList.svelte";

  let {
    title,
    open,
    ontoggle,
    list,
    exclude,
    pool,
    defaults,
    lang,
    onchange,
    labels,
  }: {
    title: string;
    open: boolean;
    ontoggle: (open: boolean) => void;
    /** Текущий список (канонические имена). */
    list: string[];
    /** Взаимоисключающий список (МТО <-> Лётка). */
    exclude: string[];
    /** Откуда берутся «Все предметы»: ITEM_NAMES ∪ pool. */
    pool: string[];
    defaults: readonly string[];
    lang: Lang;
    onchange: (next: string[]) => void;
    labels: {
      search: string;
      selected: string;
      addTip: string;
      removeTip: string;
      resetTip: string;
      resetTitle: string;
      resetText: string;
    };
  } = $props();

  let search = $state("");
  let selAvail = $state(new Set<string>());
  let selChosen = $state(new Set<string>());

  // Поиск — и по русскому имени, и по названию на текущем языке.
  const matches = (name: string, q: string) =>
    !q || name.toLowerCase().includes(q) || trItem(name, lang).toLowerCase().includes(q);

  const available = $derived.by(() => {
    const q = search.trim().toLowerCase();
    const chosen = new Set(list.map((s) => s.toLowerCase()));
    const ex = new Set(exclude.map((s) => s.toLowerCase()));
    return allItemNames(pool).filter((n) => !chosen.has(n.toLowerCase()) && !ex.has(n.toLowerCase()) && matches(n, q));
  });
  const chosenView = $derived.by(() => {
    const q = search.trim().toLowerCase();
    return sortedByLower(list).filter((n) => matches(n, q));
  });

  function add(names: Iterable<string>) {
    const next = [...list];
    for (const n of names) if (!next.includes(n)) next.push(n);
    selAvail = new Set();
    onchange(next);
  }

  function remove(names: Iterable<string>) {
    const drop = new Set(names);
    selChosen = new Set();
    onchange(list.filter((n) => !drop.has(n)));
  }

  async function reset() {
    if (await confirmDialog(labels.resetTitle, labels.resetText)) onchange([...defaults]);
  }

  // Выделение — только среди видимых строк (как в пересобираемом QListWidget).
  const prune = (sel: Set<string>, visible: string[]) => {
    const vis = new Set(visible);
    const kept = [...sel].filter((n) => vis.has(n));
    return kept.length === sel.size ? sel : new Set(kept);
  };
  $effect(() => {
    selAvail = prune(selAvail, available);
  });
  $effect(() => {
    selChosen = prune(selChosen, chosenView);
  });
</script>

<section class="group">
  <label class="group-title check">
    <input type="checkbox" checked={open} onchange={(e) => ontoggle(e.currentTarget.checked)} />
    {title}
  </label>
  {#if open}
    <div class="lists">
      <div class="col">
        <span class="lbl">{tr("all_items_label", lang)}</span>
        <input class="field search" placeholder={labels.search} bind:value={search} />
        <ItemList items={available} {lang} bind:selected={selAvail} onactivate={(n) => add([n])} />
      </div>
      <div class="btncol">
        <button class="btn" title={labels.addTip} onclick={() => add(selAvail)}>→&nbsp;&nbsp;+</button>
        <button class="btn" title={labels.removeTip} onclick={() => remove(selChosen)}>−&nbsp;&nbsp;←</button>
      </div>
      <div class="col">
        <span class="lbl">{labels.selected}</span>
        <ItemList items={chosenView} {lang} bind:selected={selChosen} onactivate={(n) => remove([n])} />
      </div>
    </div>
    <div class="bottom">
      <button class="btn" title={labels.resetTip} onclick={reset}>{tr("reset_default_btn", lang)}</button>
    </div>
  {/if}
</section>

<style>
  .lists {
    display: flex;
    gap: 10px;
    align-items: stretch;
  }
  .col {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .search {
    margin-bottom: 6px;
  }
  .btncol {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
  }
  .bottom {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
</style>
