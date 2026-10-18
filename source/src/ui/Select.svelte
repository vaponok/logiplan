<script lang="ts" generics="T">
  // Выпадающий список в стиле программы: системный <select> рисует список
  // средствами ОС (в WebView2 — по-виндовому), стилизовать его нельзя.
  type Option = { value: T; label: string };
  let {
    value = $bindable(),
    options,
    placeholder = "",
    disabled = false,
    class: cls = "",
    onchange,
  }: {
    value: T;
    options: Option[];
    placeholder?: string;
    disabled?: boolean;
    class?: string;
    onchange?: (v: T) => void;
  } = $props();

  let open = $state(false);
  let up = $state(false); // список над полем, если снизу не хватает места
  let active = $state(-1); // подсвеченный пункт (мышь/стрелки)
  let root: HTMLDivElement;
  let list = $state<HTMLDivElement>();

  const selected = $derived(options.findIndex((o) => o.value === value));
  const MAX_H = 280;

  function show() {
    if (disabled || open) return;
    const r = root.getBoundingClientRect();
    up = window.innerHeight - r.bottom < MAX_H + 8 && r.top > window.innerHeight - r.bottom;
    active = selected;
    open = true;
  }

  function pick(i: number) {
    const o = options[i];
    open = false;
    if (!o) return;
    if (o.value !== value) {
      value = o.value;
      onchange?.(o.value);
    }
  }

  function onkeydown(e: KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        show();
      }
      return;
    }
    if (e.key === "Escape" || e.key === "Tab") {
      open = false;
      if (e.key === "Escape") e.preventDefault();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = options.length;
      active = e.key === "ArrowDown" ? Math.min(n - 1, active + 1) : Math.max(0, active - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(active);
    }
  }

  // подсвеченный пункт — в видимую часть списка
  $effect(() => {
    if (open && list && active >= 0) (list.children[active] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
  });

  // клик мимо — закрыть
  $effect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (!root.contains(e.target as Node)) open = false;
    };
    window.addEventListener("pointerdown", close, true);
    return () => window.removeEventListener("pointerdown", close, true);
  });
</script>

<div class="sel {cls}" bind:this={root}>
  <button
    type="button"
    class="field btn-sel"
    class:placeholder={selected < 0}
    class:open
    {disabled}
    aria-haspopup="listbox"
    aria-expanded={open}
    onclick={() => (open ? (open = false) : show())}
    {onkeydown}
  >
    <span class="text">{selected >= 0 ? options[selected].label : placeholder}</span>
    <svg class="arrow" width="12" height="8" viewBox="0 0 12 8" aria-hidden="true"
      ><path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" /></svg
    >
  </button>
  {#if open}
    <div class="list" class:up role="listbox" bind:this={list} style:max-height="{MAX_H}px">
      {#each options as o, i (i)}
        <div
          class="opt"
          class:active={i === active}
          class:selected={i === selected}
          role="option"
          tabindex="-1"
          aria-selected={i === selected}
          onpointerenter={() => (active = i)}
          onpointerdown={(e) => e.preventDefault()}
          onclick={() => pick(i)}
          onkeydown={() => {}}
        >
          {o.label}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .sel {
    position: relative;
    min-width: 0;
  }
  .btn-sel {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    text-align: left;
    cursor: pointer;
  }
  .btn-sel:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .btn-sel.open {
    border-color: var(--primary);
  }
  .text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .placeholder .text {
    color: #757575;
  }
  .arrow {
    flex: none;
    transition: transform 0.15s;
  }
  .open .arrow {
    transform: rotate(180deg);
  }
  .list {
    position: absolute;
    left: 0;
    top: calc(100% + 4px);
    /* не уже поля; длинные названия расширяют список, а не обрезаются */
    min-width: 100%;
    width: max-content;
    max-width: min(520px, 90vw);
    z-index: 50;
    overflow-y: auto;
    background: #fff;
    border: var(--border);
    /* 12px: внутри рамки 9px — как у ползунка, в крайнем положении он
       ложится в угол без зазора */
    border-radius: 12px;
    padding: 4px;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
  }
  .list.up {
    top: auto;
    bottom: calc(100% + 4px);
  }
  .opt {
    padding: 7px 10px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    user-select: none;
  }
  .opt.selected {
    font-weight: 700;
  }
  .opt.active {
    background: var(--primary);
    color: #fff;
  }
</style>
