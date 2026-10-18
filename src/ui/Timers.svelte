<script lang="ts">
  // Вкладка «Таймеры складов»: склад живёт 50 часов от последнего обновления.
  import { tr } from "../core/i18n";
  import { regions } from "../data/depots.json";
  import { alertDialog, confirmDialog } from "../lib/dialogs.svelte";
  import { app, newId, timers, type Warehouse } from "../lib/state.svelte";

  const HOURS_50 = 50 * 3600 * 1000;
  const L = $derived(app.lang);
  let name = $state("");
  let hex = $state("");
  let depot = $state(""); // индекс в depots региона
  const depots = $derived(regions.find((r) => r.region === hex)?.depots ?? []);
  let password = $state("");
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
    if (password && password.length !== 6) {
      await alertDialog(tr("wt_error_title", app.lang), tr("wt_password_error", app.lang));
      return;
    }
    const d = depot ? (depots[Number(depot)] as [string, string]) : undefined;
    timers.warehouses.push({
      id: newId(),
      name: n,
      hex,
      depotType: d?.[0] ?? "",
      depot: d?.[1] ?? "",
      password,
      expire: Date.now() + HOURS_50,
    });
    name = hex = depot = password = "";
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

  /** «Морской порт — Saltbrook Channel» */
  function depotLabel(type: string, town: string) {
    return type ? `${tr(`wt_depot_${type}`, L)} — ${town}` : town;
  }

  /** Гекс · склад · пароль под названием. */
  function meta(w: Warehouse) {
    const parts = [w.hex, depotLabel(w.depotType, w.depot)].filter(Boolean);
    if (w.password) parts.push(`${tr("wt_password_placeholder", L)}: ${w.password}`);
    return parts.join(" · ");
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
    <input class="field name-input" placeholder={tr("wt_name_placeholder", L)} bind:value={name} />
    <select class="field" class:empty={!hex} bind:value={hex} onchange={() => (depot = "")}>
      <option value="">{tr("wt_hex_placeholder", L)}</option>
      {#each regions as r (r.region)}
        <option value={r.region}>{r.region}</option>
      {/each}
    </select>
    <select class="field depot-select" class:empty={!depot} bind:value={depot} disabled={!hex}>
      <option value="">{tr("wt_depot_placeholder", L)}</option>
      {#each depots as [type, town], i (i)}
        <option value={String(i)}>{depotLabel(type, town)}</option>
      {/each}
    </select>
    <input
      class="field password-input"
      placeholder={tr("wt_password_placeholder", L)}
      inputmode="numeric"
      maxlength="6"
      autocomplete="off"
      value={password}
      oninput={(e) => {
        password = e.currentTarget.value.replace(/\D/g, "").slice(0, 6);
        e.currentTarget.value = password;
      }}
    />
    <button class="btn add" type="submit">{tr("wt_add_btn", L)}</button>
  </form>
  <div class="list">
    {#each timers.warehouses as w (w.id)}
      {@const v = view(w.expire)}
      {@const m = meta(w)}
      <div class="wh">
        <div class="wh-info">
          <div class="wh-name">{w.name}</div>
          {#if m}<div class="wh-meta">{m}</div>{/if}
        </div>
        <div class="timer {v.zone}">{v.text}</div>
        <button class="btn refresh" onclick={() => refresh(w)}>{tr("wt_refresh_btn", L)}</button>
        <button class="btn del" aria-label={tr("wt_delete_tooltip", L)} onclick={() => remove(w)}
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
    flex-wrap: wrap;
    gap: 8px;
  }
  .field {
    flex: 1 1 120px;
    min-width: 0;
    border: var(--border);
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    outline: none;
  }
  .field:focus {
    border-color: var(--primary);
  }
  .name-input {
    flex: 2 1 180px;
  }
  .password-input {
    flex: 0 1 110px;
  }
  select.field {
    padding-right: 30px;
    background: #fff
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%23000' stroke-width='2'/%3E%3C/svg%3E")
      no-repeat right 12px center;
  }
  select.field:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .depot-select {
    flex: 2 1 200px;
  }
  .empty {
    color: #757575;
  }
  .empty option {
    color: #000;
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
  .wh-info {
    min-width: 180px;
    flex: 1;
    overflow-wrap: anywhere;
  }
  .wh-name {
    font-size: 14px;
    font-weight: 600;
  }
  .wh-meta {
    margin-top: 4px;
    font-size: 12px;
    opacity: 0.7;
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
