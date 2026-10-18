// Рамка окна: прозрачная полоса под тень с каждой стороны и скругления углов.
// Полоса подогнана под тень (сверху тень короче, снизу длиннее) и пропадает
// со стороны, прижатой к краю рабочей области экрана (Win+←/→, Snap Layouts,
// развёртывание по вертикали), и целиком — у развёрнутого окна.
import { appWindow } from "./platform";

export const GUTTER = { top: 6, right: 10, bottom: 14, left: 10 } as const;
export const RADIUS = 16;

export interface Frame {
  maximized: boolean;
  /** Толщина полосы под тень, px (0 — сторона у края экрана). */
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export const frame = $state<Frame>({ maximized: false, ...GUTTER });

/** Записать рамку в CSS-переменные и в общее состояние. */
export function applyFrame(f: Frame) {
  Object.assign(frame, f);
  const st = document.documentElement.style;
  const px = (n: number) => `${n}px`;
  st.setProperty("--g-top", px(f.top));
  st.setProperty("--g-right", px(f.right));
  st.setProperty("--g-bottom", px(f.bottom));
  st.setProperty("--g-left", px(f.left));
  // угол скругляется, только если обе его стороны «свободны»
  const r = (a: number, b: number) => px(a && b ? RADIUS : 0);
  st.setProperty("--r-tl", r(f.top, f.left));
  st.setProperty("--r-tr", r(f.top, f.right));
  st.setProperty("--r-br", r(f.bottom, f.right));
  st.setProperty("--r-bl", r(f.bottom, f.left));
}

const TOUCH_TOLERANCE = 2; // физ. px

/** Текущая рамка; null — окно свёрнуто (тогда ничего не меняем). */
export async function computeFrame(): Promise<Frame | null> {
  const w = await appWindow();
  if (!w) return { maximized: false, ...GUTTER };
  // У свёрнутого окна tao сбрасывает «развёрнуто» — не верим ему до разворота.
  if (await w.isMinimized()) return null;
  const maximized = await w.isMaximized();
  if (maximized) return { maximized, top: 0, right: 0, bottom: 0, left: 0 };
  const { currentMonitor } = await import("./win");
  const [pos, size, mon] = await Promise.all([w.outerPosition(), w.outerSize(), currentMonitor()]);
  if (!mon) return { maximized, ...GUTTER };
  const wa = mon.workArea;
  const near = (a: number, b: number) => Math.abs(a - b) <= TOUCH_TOLERANCE;
  return {
    maximized,
    top: near(pos.y, wa.position.y) ? 0 : GUTTER.top,
    left: near(pos.x, wa.position.x) ? 0 : GUTTER.left,
    right: near(pos.x + size.width, wa.position.x + wa.size.width) ? 0 : GUTTER.right,
    bottom: near(pos.y + size.height, wa.position.y + wa.size.height) ? 0 : GUTTER.bottom,
  };
}

/** Следить за окном: размер, положение, развёртывание. Пока окно тянут,
 *  пересчёт не чаще раза в 150 мс (первый — сразу, последний — обязательно),
 *  чтобы запросы к окну не мешали WebView2 перерисовываться. */
export async function watchFrame() {
  const w = await appWindow();
  if (!w) return;
  let running = false;
  let again = false;
  const update = async () => {
    if (running) {
      again = true;
      return;
    }
    running = true;
    try {
      do {
        again = false;
        const f = await computeFrame();
        if (f) applyFrame(f);
      } while (again);
    } finally {
      running = false;
    }
  };
  const THROTTLE_MS = 150;
  let last = -Infinity;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const schedule = () => {
    if (timer) return;
    const wait = THROTTLE_MS - (performance.now() - last);
    if (wait <= 0) {
      last = performance.now();
      void update();
    } else {
      timer = setTimeout(() => {
        timer = null;
        last = performance.now();
        void update();
      }, wait);
    }
  };
  await w.onResized(schedule);
  await w.onMoved(schedule);
  await update();
}
