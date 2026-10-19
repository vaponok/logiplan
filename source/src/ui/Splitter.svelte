<script lang="ts">
  // Вкладка «Распределитель» — UI ResourceSplitter.
  import { tr, trResource, WEEKDAYS } from "../core/i18n";
  import type { AvSettings } from "../core/quotaParse";
  import {
    applyAviationSettings,
    aviationOrders,
    AVIATION_DEFAULT,
    calculateQuota,
    OMTO_DEFAULT,
    todayLocal,
    type AviationOrder,
    type SplitterInput,
    UNIT_RESOURCES,
  } from "../core/splitter";
  import { calculateInBackground } from "../lib/calcClient";
  import { app, ensureLengths, results, splitter as s } from "../lib/state.svelte";
  import AviationDialog from "./AviationDialog.svelte";
  import CopyButton from "./CopyButton.svelte";
  import ListEditor from "./ListEditor.svelte";
  import NumberField from "./NumberField.svelte";
  import Select from "./Select.svelte";

  const L = $derived(app.lang);
  let avDialog = $state<AviationOrder[] | null>(null);

  function setCount(key: "divisionCount" | "omtoCount" | "aviationCount", v: number) {
    s[key] = v;
    ensureLengths(s);
  }

  function onCalcQuota() {
    const r = calculateQuota(s.storageInput, s.requiredInput, s.omtoList, s.aviationList, app.lang);
    s.quotaText = r.main;
    s.modsText = r.mods;
    s.equipmentText = r.equipment;
    s.aviationText = r.aviation;
  }

  function buildInput(): SplitterInput {
    const snap = $state.snapshot(s);
    return {
      lang: app.lang,
      quotaText: snap.quotaText,
      divisions: snap.divisions.slice(0, snap.divisionCount),
      unitName: snap.unitName,
      storageName: snap.storageName,
      storagePass: snap.storagePass,
      weekdayIndex: snap.weekdayIndex,
      today: todayLocal(),
      omtoName: snap.omtoName,
      omtoCount: snap.omtoCount,
      omtoNames: snap.omtoNames.slice(0, snap.omtoCount),
      modsText: snap.modsText,
      equipmentText: snap.equipmentText,
      aviationCount: snap.aviationCount,
      aviationNames: snap.aviationNames.slice(0, snap.aviationCount),
      aviationText: snap.aviationText,
      enforceMul4: snap.enforceMul4,
      freeEmats: snap.freeEmats,
      freeHemats: snap.freeHemats,
      freeRmats: snap.freeRmats,
      omtoList: snap.omtoList,
      aviationList: snap.aviationList,
      avDefaults: snap.avDefaults,
      unitWeights: snap.balanceMode === "units" ? snap.unitWeights : null,
    };
  }

  async function onCalculate() {
    if (results.busy) return;
    results.busy = true;
    try {
      const r = await calculateInBackground(buildInput());
      results.output = r.output;
      if (r.undefinedLines) results.undefinedLines = r.undefinedLines;
    } catch (e) {
      results.output = tr("calc_error", app.lang, { e: e instanceof Error ? e.message : String(e) });
    } finally {
      results.busy = false;
    }
  }

  function openAviationDialog() {
    avDialog = aviationOrders(s.aviationText, s.avDefaults);
  }

  function saveAviationDialog(defaults: AvSettings, perLine: Map<number, AvSettings>) {
    const orders = avDialog ?? [];
    s.aviationText = applyAviationSettings(s.aviationText, orders, defaults, perLine, app.lang);
    s.avDefaults = defaults;
    avDialog = null;
  }


  const undefColor = { aviation: "#3ba0ff", factory: "#ffe600", unknown: "#ff3b3b" } as const;
</script>

<div class="splitter">
  <!-- ===== Расчёт квоты ===== -->
  <section class="group">
    <div class="group-title">{tr("calc_quota_group", L)}</div>
    <div class="two">
      <div class="col">
        <span class="lbl">{tr("storage_label", L)}</span>
        <textarea class="area" style:min-height="200px" placeholder={tr("storage_placeholder", L)} bind:value={s.storageInput}
        ></textarea>
      </div>
      <div class="col">
        <span class="lbl">{tr("required_label", L)}</span>
        <textarea class="area" style:min-height="200px" placeholder={tr("required_placeholder", L)} bind:value={s.requiredInput}
        ></textarea>
      </div>
    </div>
    <button class="btn wide" onclick={onCalcQuota}>{tr("calc_quota_btn", L)}</button>
  </section>

  <!-- ===== Шапка плана ===== -->
  <span class="lbl">{tr("unit_name_label", L)}</span>
  <input class="field block" bind:value={s.unitName} />
  <span class="lbl">{tr("main_storage_label", L)}</span>
  <input class="field block" bind:value={s.storageName} />
  <span class="lbl">{tr("storage_password_label", L)}</span>
  <input class="field block" bind:value={s.storagePass} />
  <span class="lbl">{tr("plan_until_label", L)}</span>
  <Select bind:value={s.weekdayIndex} options={WEEKDAYS[L].map((day, i) => ({ value: i, label: day }))} />
  <span class="lbl">{tr("division_count_label", L)}</span>
  <NumberField value={s.divisionCount} min={1} max={100} width="100%" onchange={(v) => setCount("divisionCount", v)} />

  <div class="divisions">
    {#each s.divisions.slice(0, s.divisionCount) as d, i (i)}
      <div class="division">
        <span>{tr("division_number_label", L, { i: i + 1 })}</span>
        <input class="field name" placeholder={tr("unit_name_input_placeholder", L)} bind:value={d.name} />
        <span>{tr("people_suffix_label", L)}</span>
        <NumberField value={d.people} min={1} max={100} onchange={(v) => (d.people = v)} />
      </div>
    {/each}
  </div>

  <span class="lbl">{tr("quota_label", L)}</span>
  <textarea class="area" style:min-height="300px" bind:value={s.quotaText}></textarea>

  <!-- ===== Завод ===== -->
  <section class="group" class:folded={!s.factoryOpen}>
    <button type="button" class="group-title fold" aria-expanded={s.factoryOpen} onclick={() => (s.factoryOpen = !s.factoryOpen)}>
      <svg class="chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
        ><path d="M1 3l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" /></svg
      >{tr("factory_group", L)}
    </button>
    {#if s.factoryOpen}

    <section class="group" class:folded={!s.omtoOpen}>
      <button type="button" class="group-title fold" aria-expanded={s.omtoOpen} onclick={() => (s.omtoOpen = !s.omtoOpen)}>
        <svg class="chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
          ><path d="M1 3l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" /></svg
        >{tr("omto_subgroup", L)}
      </button>
      {#if s.omtoOpen}
      <div class="row">
        <span>{tr("omto_name_label", L)}</span>
        <input class="field grow" bind:value={s.omtoName} />
        <span>{tr("headcount_label", L)}</span>
        <NumberField value={s.omtoCount} min={0} max={50} onchange={(v) => setCount("omtoCount", v)} />
      </div>
      {#each s.omtoNames.slice(0, s.omtoCount) as _n, i (i)}
        <input class="field block person" placeholder={tr("person_name_placeholder", L, { i: i + 1 })} bind:value={s.omtoNames[i]} />
      {/each}
      <div class="two">
        <div class="col">
          <span class="lbl">{tr("mods_label", L)}</span>
          <textarea class="area" style:min-height="300px" bind:value={s.modsText}></textarea>
        </div>
        <div class="col">
          <span class="lbl">{tr("equipment_label", L)}</span>
          <textarea class="area" style:min-height="300px" bind:value={s.equipmentText}></textarea>
        </div>
      </div>
      <ListEditor
        title={tr("omto_editor_group", L)}
        open={s.omtoEditorOpen}
        ontoggle={(v) => (s.omtoEditorOpen = v)}
        list={s.omtoList}
        exclude={s.aviationList}
        pool={s.omtoList}
        defaults={OMTO_DEFAULT}
        lang={L}
        onchange={(next) => (s.omtoList = next)}
        labels={{
          search: tr("omto_search_placeholder", L),
          selected: tr("in_omto_label", L),
          addTip: tr("add_to_omto_tooltip", L),
          removeTip: tr("remove_from_omto_tooltip", L),
          resetTip: tr("reset_omto_tooltip", L),
          resetTitle: tr("reset_omto_dialog_title", L),
          resetText: tr("reset_omto_dialog_text", L),
        }}
      />
      {/if}
    </section>

    <section class="group" class:folded={!s.aviationOpen}>
      <button type="button" class="group-title fold" aria-expanded={s.aviationOpen} onclick={() => (s.aviationOpen = !s.aviationOpen)}>
        <svg class="chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
          ><path d="M1 3l5 5 5-5" fill="none" stroke="currentColor" stroke-width="2" /></svg
        >{tr("aviation_subgroup", L)}
      </button>
      {#if s.aviationOpen}
      <div class="row">
        <span>{tr("headcount_label", L)}</span>
        <NumberField value={s.aviationCount} min={0} max={50} onchange={(v) => setCount("aviationCount", v)} />
      </div>
      {#each s.aviationNames.slice(0, s.aviationCount) as _n, i (i)}
        <input class="field block person" placeholder={tr("pilot_name_placeholder", L, { i: i + 1 })} bind:value={s.aviationNames[i]} />
      {/each}
      <span class="lbl">{tr("aviation_label", L)}</span>
      <textarea class="area" style:min-height="300px" bind:value={s.aviationText}></textarea>
      <button class="btn wide" onclick={openAviationDialog}>{tr("aviation_recipe_btn", L)}</button>
      <ListEditor
        title={tr("aviation_editor_group", L)}
        open={s.aviationEditorOpen}
        ontoggle={(v) => (s.aviationEditorOpen = v)}
        list={s.aviationList}
        exclude={s.omtoList}
        pool={s.omtoList}
        defaults={AVIATION_DEFAULT}
        lang={L}
        onchange={(next) => (s.aviationList = next)}
        labels={{
          search: tr("aviation_search_placeholder", L),
          selected: tr("in_aviation_label", L),
          addTip: tr("add_to_aviation_tooltip", L),
          removeTip: tr("remove_from_aviation_tooltip", L),
          resetTip: tr("reset_aviation_tooltip", L),
          resetTitle: tr("reset_aviation_dialog_title", L),
          resetText: tr("reset_aviation_dialog_text", L),
        }}
      />
      {/if}
    </section>
    {/if}
  </section>

  <!-- ===== Флажки и расчёт ===== -->
  <div class="checks">
    <span class="check"><input type="checkbox" bind:checked={s.enforceMul4} aria-label={tr("mul4_checkbox", L)} /><span>{tr("mul4_checkbox", L)}</span></span>
    <span class="check"><input type="checkbox" bind:checked={s.freeEmats} aria-label={tr("free_emats_checkbox", L)} /><span>{tr("free_emats_checkbox", L)}</span></span>
    <span class="check"><input type="checkbox" bind:checked={s.freeHemats} aria-label={tr("free_hemats_checkbox", L)} /><span>{tr("free_hemats_checkbox", L)}</span></span>
    <span class="check"><input type="checkbox" bind:checked={s.freeRmats} aria-label={tr("free_rmats_checkbox", L)} /><span>{tr("free_rmats_checkbox", L)}</span></span>
  </div>

  <!-- ===== Режим распределения ===== -->
  <div class="row mode">
    <span>{tr("balance_mode_label", L)}</span>
    <Select
      class="mode-select"
      bind:value={s.balanceMode}
      options={[
        { value: "resources", label: tr("balance_mode_resources", L) },
        { value: "units", label: tr("balance_mode_units", L) },
      ]}
    />
  </div>
  {#if s.balanceMode === "units"}
    <span class="lbl">{tr("unit_weights_label", L)}</span>
    <div class="weights">
      {#each UNIT_RESOURCES as r (r)}
        <span class="weight">
          <span>{trResource(r, L)}</span>
          <NumberField value={s.unitWeights[r]} min={0} max={100000} decimals={2} step={0.5} width="80px" onchange={(v) => (s.unitWeights[r] = v)} />
        </span>
      {/each}
    </div>
  {/if}

  <button class="btn wide" disabled={results.busy} onclick={onCalculate}>
    {results.busy ? tr("calculating", L) : tr("calculate_btn", L)}
  </button>

  <!-- ===== Результат ===== -->
  <div class="results">
    <div class="col">
      <span class="lbl">{tr("result_label", L)}</span>
      <div class="copywrap">
        <textarea class="area out" readonly value={results.output}></textarea>
        <CopyButton text={results.output} />
      </div>
    </div>
    <div class="col">
      <span class="lbl unknown">{tr("unknown_positions_label", L)}</span>
      <div class="area undef" role="log">
        {#each results.undefinedLines as u, i (i)}
          <div class="uline" style:color={undefColor[u.kind]}>{u.text}</div>
        {/each}
      </div>
    </div>
  </div>
</div>

{#if avDialog}
  <AviationDialog orders={avDialog} defaults={s.avDefaults} lang={L} onsave={saveAviationDialog} oncancel={() => (avDialog = null)} />
{/if}

<style>
  .splitter {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px;
  }
  .two {
    display: flex;
    gap: 10px;
  }
  .col {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .wide {
    width: 100%;
    margin-top: 8px;
  }
  .block {
    display: block;
    width: 100%;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .grow {
    flex: 1;
  }
  .person {
    margin-top: 6px;
  }
  .divisions {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 6px;
  }
  .division {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .division .name {
    min-width: 250px;
    flex: 1;
  }
  .mode {
    margin-bottom: 4px;
  }
  .row :global(.mode-select) {
    width: 260px;
  }
  .weights {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    margin-bottom: 4px;
  }
  .weight {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .checks {
    display: flex;
    flex-direction: column;
    /* флажок нажимается по своей подписи, а не по всей строке */
    align-items: flex-start;
    gap: 6px;
    margin: 10px 0 4px;
  }
  .results {
    display: flex;
    gap: 10px;
    margin-top: 6px;
  }
  .unknown {
    color: red;
  }
  .out {
    min-height: 300px;
    height: 460px;
    /* место под кнопку «копировать» в углу */
    padding-right: 66px;
  }
  /* заголовок сворачиваемого раздела */
  .fold {
    width: 100%;
    padding: 0;
    border: none;
    background: none;
    text-align: left;
    font: inherit;
    font-weight: 600;
  }
  .folded {
    padding-bottom: 10px;
  }
  .fold[aria-expanded="false"] {
    margin-bottom: 0;
  }
  .chev {
    flex: none;
    transition: transform 0.15s;
  }
  .fold[aria-expanded="false"] .chev {
    transform: rotate(-90deg);
  }
  .uline {
    /* пустое имя (строка Лётки вида "(Ящик),2") — всё равно видимая строка */
    min-height: 1.35em;
  }
  .undef {
    min-height: 300px;
    height: 460px;
    overflow: auto;
    white-space: pre-wrap;
    user-select: text;
    cursor: text;
  }
</style>
