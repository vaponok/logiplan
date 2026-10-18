// Только те вызовы окна, которые нужны программе. Повторяет то, что делает
// @tauri-apps/api/window 2.x (те же команды plugin:window|… и события), но
// без остальных ~80 методов класса Window: в exe лежит меньше JS.
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface Position {
  x: number;
  y: number;
}
export interface Size {
  width: number;
  height: number;
}
export interface Monitor {
  workArea: { position: Position; size: Size };
}

export type ResizeDirection = "East" | "North" | "NorthEast" | "NorthWest" | "South" | "SouthEast" | "SouthWest" | "West";

interface TauriInternals {
  metadata: { currentWindow: { label: string } };
}

export class AppWindow {
  constructor(readonly label: string) {}

  private call<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
    return invoke<T>(`plugin:window|${cmd}`, { label: this.label, ...args });
  }

  private on(event: string, handler: () => void | Promise<void>): Promise<UnlistenFn> {
    return listen(event, handler, { target: { kind: "Window", label: this.label } });
  }

  minimize = () => this.call<void>("minimize");
  toggleMaximize = () => this.call<void>("toggle_maximize");
  close = () => this.call<void>("close");
  destroy = () => this.call<void>("destroy");
  isMinimized = () => this.call<boolean>("is_minimized");
  isMaximized = () => this.call<boolean>("is_maximized");
  outerPosition = () => this.call<Position>("outer_position");
  outerSize = () => this.call<Size>("outer_size");
  startResizeDragging = (direction: ResizeDirection) => this.call<void>("start_resize_dragging", { value: direction });
  onResized = (handler: () => void) => this.on("tauri://resize", handler);
  onMoved = (handler: () => void) => this.on("tauri://move", handler);
  /** Как Window.onCloseRequested без preventDefault: после обработчика окно закрывается. */
  onCloseRequested = (handler: () => Promise<void>) =>
    this.on("tauri://close-requested", async () => {
      await handler();
      await this.destroy();
    });
}

export function getCurrentWindow(): AppWindow {
  const internals = (window as unknown as { __TAURI_INTERNALS__: TauriInternals }).__TAURI_INTERNALS__;
  return new AppWindow(internals.metadata.currentWindow.label);
}

/** Монитор, на котором окно (null — не определился). */
export const currentMonitor = () => invoke<Monitor | null>("plugin:window|current_monitor");
