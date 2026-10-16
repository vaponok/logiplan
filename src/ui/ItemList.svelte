<script lang="ts">
  // Список с множественным выбором (Ctrl/Shift), как QListWidget ExtendedSelection.
  import { trItem, type Lang } from "../core/i18n";

  let {
    items,
    lang,
    selected = $bindable(new Set<string>()),
    onactivate,
  }: {
    items: string[];
    lang: Lang;
    selected?: Set<string>;
    onactivate?: (name: string) => void;
  } = $props();

  let anchor: number | null = null;

  function click(e: MouseEvent, idx: number) {
    const name = items[idx];
    const next = new Set(e.ctrlKey || e.metaKey ? selected : []);
    if (e.shiftKey && anchor !== null) {
      const [a, b] = anchor < idx ? [anchor, idx] : [idx, anchor];
      if (!(e.ctrlKey || e.metaKey)) next.clear();
      for (let i = a; i <= b; i++) next.add(items[i]);
    } else if (e.ctrlKey || e.metaKey) {
      if (next.has(name)) next.delete(name);
      else next.add(name);
      anchor = idx;
    } else {
      next.add(name);
      anchor = idx;
    }
    selected = next;
  }
</script>

<div class="list" role="listbox" aria-multiselectable="true" tabindex="0">
  {#each items as name, idx (name)}
    <div
      class="item"
      class:sel={selected.has(name)}
      role="option"
      aria-selected={selected.has(name)}
      tabindex="-1"
      onclick={(e) => click(e, idx)}
      ondblclick={() => onactivate?.(name)}
      onkeydown={(e) => e.key === "Enter" && onactivate?.(name)}
    >
      {trItem(name, lang)}
    </div>
  {/each}
</div>

<style>
  .list {
    border: var(--border);
    border-radius: 8px;
    padding: 4px;
    background: #fff;
    /* растягивается до низа колонки: левый и правый списки кончаются вровень */
    height: 300px;
    flex: 1 0 auto;
    overflow-y: auto;
    outline: none;
    user-select: none;
  }
  .item {
    padding: 3px 6px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .item:hover {
    background: #e8f0ff;
  }
  .item.sel {
    background: var(--primary);
    color: #fff;
  }
</style>
