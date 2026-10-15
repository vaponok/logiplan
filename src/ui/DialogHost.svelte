<script lang="ts">
  import { tr } from "../core/i18n";
  import { closeDialog, ui } from "../lib/dialogs.svelte";
  import { app } from "../lib/state.svelte";
  import Modal from "./Modal.svelte";
</script>

{#if ui.dialog}
  <Modal title={ui.dialog.title} onclose={() => closeDialog(false)}>
    {ui.dialog.text}
    {#snippet footer()}
      {#if ui.dialog?.kind === "confirm"}
        <button class="btn small" onclick={() => closeDialog(true)}>{tr("btn_yes", app.lang)}</button>
        <button class="btn small" onclick={() => closeDialog(false)}>{tr("btn_no", app.lang)}</button>
      {:else}
        <button class="btn small" onclick={() => closeDialog(true)}>{tr("btn_ok", app.lang)}</button>
      {/if}
    {/snippet}
  </Modal>
{/if}

{#if ui.toast}
  <div class="toast" role="status">{ui.toast}</div>
{/if}

<style>
  .toast {
    position: fixed;
    left: 50%;
    bottom: 24px;
    transform: translateX(-50%);
    background: var(--ink);
    color: #fff;
    border: var(--border);
    border-radius: 10px;
    padding: 10px 16px;
    z-index: 200;
    font-weight: 600;
  }
</style>
