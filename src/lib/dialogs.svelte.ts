// Модальные окна (вместо QMessageBox) и всплывающие подсказки.
export interface DialogState {
  title: string;
  text: string;
  kind: "confirm" | "alert";
  resolve: (ok: boolean) => void;
}

export const ui = $state({
  dialog: null as DialogState | null,
  toast: null as string | null,
});

let toastTimer: ReturnType<typeof setTimeout> | null = null;

export function confirmDialog(title: string, text: string): Promise<boolean> {
  return new Promise((resolve) => {
    ui.dialog = { title, text, kind: "confirm", resolve };
  });
}

export function alertDialog(title: string, text: string): Promise<boolean> {
  return new Promise((resolve) => {
    ui.dialog = { title, text, kind: "alert", resolve };
  });
}

export function closeDialog(ok: boolean) {
  const d = ui.dialog;
  ui.dialog = null;
  d?.resolve(ok);
}

export function toast(text: string, ms = 2200) {
  ui.toast = text;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (ui.toast = null), ms);
}
