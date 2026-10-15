<script lang="ts">
  // Вкладка «Таймеры складов»: склад живёт 50 часов от последнего обновления.
  import { tr } from "../core/i18n";
  import { alertDialog, confirmDialog } from "../lib/dialogs.svelte";
  import { app, newId, timers, type Warehouse } from "../lib/state.svelte";

  const HOURS_50 = 50 * 3600 * 1000;
  const L = $derived(app.lang);
  let name = $state("");
  let now = $state(Date.now());

  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(t);
  });

  async function add() {
    const n = name.trim();
    if (!n) {
      await alertDialog(tr("wt_error_title", app.lang), tr("wt_error_text", app.lang));
      return;
    }
    timers.warehouses.push({ id: newId(), name: n, expire: Date.now() + HOURS_50 });
    name = "";
  }

  function refresh(w: Warehouse) {
    w.expire = Date.now() + HOURS_50;
    now = Date.now();
  }

  async function remove(w: Warehouse) {
    if (await confirmDialog(tr("wt_confirm_title", app.lang), tr("wt_confirm_text", app.lang, { name: w.name }))) {
      timers.warehouses = timers.warehouses.filter((x) => x.id !== w.id);
    }
  }

  function view(expire: number) {
    const secs = (expire - now) / 1000;
    if (secs <= 0) return { text: tr("wt_expired", L), zone: "expired" };
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const sec = Math.floor(secs % 60);
    const pad = (x: number) => String(x).padStart(2, "0");
    const zone = h > 48 ? "green" : h >= 5 ? "orange" : "red";
    return { text: `${pad(h)}:${pad(m)}:${pad(sec)}`, zone };
  }
</script>

<div class="wt">
  <div class="header">{tr("wt_header", L)}</div>
  <form
    class="input-row"
    onsubmit={(e) => {
      e.preventDefault();
      add();
    }}
  >
    <input class="name-input" placeholder={tr("wt_name_placeholder", L)} bind:value={name} />
    <button class="btn add" type="submit">{tr("wt_add_btn", L)}</button>
  </form>
  <div class="list">
    {#each timers.warehouses as w (w.id)}
      {@const v = view(w.expire)}
      <div class="wh">
        <div class="wh-name">{w.name}</div>
        <div class="timer {v.zone}">{v.text}</div>
        <button class="btn refresh" title={tr("wt_refresh_tooltip", L)} onclick={() => refresh(w)}>{tr("wt_refresh_btn", L)}</button>
        <button class="btn del" title={tr("wt_delete_tooltip", L)} aria-label={tr("wt_delete_tooltip", L)} onclick={() => remove(w)}
          >🗑️</button
        >
      </div>
    {/each}
  </div>
</div>

<style>
  .wt {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    height: 100%;
    min-height: 0;
  }
  .header {
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    padding: 12px;
    border: var(--border);
    border-radius: 12px;
  }
  .input-row {
    display: flex;
    gap: 8px;
  }
  .name-input {
    flex: 1;
    border: var(--border);
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    outline: none;
  }
  .name-input:focus {
    border-color: var(--primary);
  }
  .add {
    padding: 10px 20px;
  }
  .list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    border: var(--border);
    border-radius: 12px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .wh {
    display: flex;
    align-items: center;
    gap: 12px;
    border: var(--border);
    border-radius: 12px;
    padding: 12px 18px;
  }
  .wh-name {
    font-size: 14px;
    font-weight: 600;
    min-width: 180px;
    flex: 1;
    overflow-wrap: anywhere;
  }
  .timer {
    font-size: 16px;
    font-weight: 700;
    border: 2px solid;
    border-radius: 8px;
    padding: 8px 16px;
    min-width: 150px;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  .timer.green {
    color: #28a745;
    border-color: #28a745;
    background: #e8f5e9;
  }
  .timer.orange {
    color: #ff8c00;
    border-color: #ff8c00;
    background: #fff4e6;
  }
  .timer.red,
  .timer.expired {
    color: #dc3545;
    border-color: #dc3545;
    background: #ffe6e6;
  }
  .refresh {
    background: #28a745;
    border-radius: 10px;
    padding: 8px 16px;
    font-size: 12px;
  }
  .refresh:hover {
    background: #34c759;
  }
  .refresh:active {
    background: #1e8035;
  }
  .del {
    width: 40px;
    height: 40px;
    padding: 0;
    border-radius: 10px;
    background: #dc3545;
    font-size: 16px;
  }
  .del:hover {
    background: #ff4757;
  }
  .del:active {
    background: #bd2130;
  }
</style>
