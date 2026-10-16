<script lang="ts">
  // «⚙ Настроить цены самолётов» — порт AviationRecipeDialog.
  import { tr, trItem, type Lang } from "../core/i18n";
  import type { AvSettings } from "../core/quotaParse";
  import type { AviationOrder } from "../core/splitter";
  import Modal from "./Modal.svelte";

  let {
    orders,
    defaults,
    lang,
    onsave,
    oncancel,
  }: {
    orders: AviationOrder[];
    defaults: AvSettings;
    lang: Lang;
    onsave: (defaults: AvSettings, perLine: Map<number, AvSettings>) => void;
    oncancel: () => void;
  } = $props();

  // Начальные значения формы берутся один раз при открытии диалога.
  const init = (() => ({ defaults: { ...defaults }, orders: orders.map((o) => ({ ...o })) }))();
  let def = $state<AvSettings>(init.defaults);
  let rows = $state(
    init.orders.map((o) => ({
      order: o,
      custom: o.settings.coke !== init.defaults.coke || o.settings.fuel !== init.defaults.fuel || o.settings.scrap !== init.defaults.scrap,
      s: { ...o.settings },
    })),
  );

  function save() {
    const perLine = new Map<number, AvSettings>();
    for (const r of rows) if (r.custom) perLine.set(r.order.lineIndex, { ...r.s });
    onsave({ ...def }, perLine);
  }
</script>

{#snippet settingsForm(s: AvSettings, scrapLabel: string)}
  <div class="grid">
    <span>{tr("coke_label", lang)}</span>
    <div class="row">
      <span class="check"><input type="radio" checked={s.coke === "with_sulfur"} onchange={() => (s.coke = "with_sulfur")} aria-label={tr("coke_with_sulfur", lang)} /><span>{tr("coke_with_sulfur", lang)}</span></span>
      <span class="check"><input type="radio" checked={s.coke === "no_sulfur"} onchange={() => (s.coke = "no_sulfur")} aria-label={tr("coke_no_sulfur", lang)} /><span>{tr("coke_no_sulfur", lang)}</span></span>
    </div>
    <span>{tr("fuel_label", lang)}</span>
    <div class="row">
      <span class="check"><input type="radio" checked={s.fuel === "sulfur"} onchange={() => (s.fuel = "sulfur")} aria-label={tr("fuel_sulfur", lang)} /><span>{tr("fuel_sulfur", lang)}</span></span>
      <span class="check"><input type="radio" checked={s.fuel === "coal"} onchange={() => (s.fuel = "coal")} aria-label={tr("fuel_coal", lang)} /><span>{tr("fuel_coal", lang)}</span></span>
    </div>
    <span>{scrapLabel}</span>
    <div class="row">
      <input class="slider" type="range" min="0" max="100" bind:value={s.scrap} />
      <span class="pct">{s.scrap}%</span>
    </div>
  </div>
{/snippet}

<Modal title={tr("av_dialog_title", lang)} onclose={oncancel} wide>
  <section class="group">
    <div class="group-title">{tr("av_defaults_group", lang)}</div>
    {@render settingsForm(def, tr("scrap_via_label", lang))}
  </section>
  <section class="group orders">
    <div class="group-title">{tr("av_orders_group", lang)}</div>
    {#if !rows.length}
      <div>{tr("av_no_orders", lang)}</div>
    {/if}
    {#each rows as r (r.order.lineIndex)}
      <div class="order">
        <div class="head">
          <b>#{r.order.lineIndex + 1}: {trItem(r.order.name, lang)} (×{r.order.count})</b>
          <span class="check"><input type="checkbox" bind:checked={r.custom} aria-label={tr("custom_settings_cb", lang)} /><span>{tr("custom_settings_cb", lang)}</span></span>
        </div>
        {#if r.custom}
          <div class="sub">{@render settingsForm(r.s, tr("via_scrap_label", lang))}</div>
        {/if}
      </div>
    {/each}
  </section>
  {#snippet footer()}
    <button class="btn small" onclick={oncancel}>{tr("btn_cancel", lang)}</button>
    <button class="btn small" onclick={save}>{tr("btn_save", lang)}</button>
  {/snippet}
</Modal>

<style>
  .grid {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 8px 12px;
    align-items: center;
    white-space: normal;
  }
  .row {
    display: flex;
    gap: 16px;
    align-items: center;
  }
  .slider {
    flex: 1;
    accent-color: var(--primary);
  }
  .pct {
    width: 44px;
    text-align: right;
  }
  .orders {
    white-space: normal;
  }
  .order {
    padding: 8px 0;
    border-bottom: 1px solid #c8ced6;
  }
  .head {
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
  }
  .sub {
    padding: 8px 0 0 20px;
  }
</style>
