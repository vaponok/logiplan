<script lang="ts">
  // Невидимая рамка в прозрачной полосе вокруг окна (там, где тень): за неё
  // окно растягивается, как за край обычного окна Windows. Самые внешние
  // ~4 px Tauri обрабатывает сам; это — остальная ширина полосы. Со стороны,
  // прижатой к краю экрана, полосы нет — нет и рамки.
  import { frame, RADIUS } from "../lib/frame.svelte";
  import { startResize, type ResizeDirection } from "../lib/platform";

  const R = RADIUS;
  const f = $derived(frame);

  // Угловая зона — «Г» из двух полос плюс прозрачная часть скругления окна
  // (до самой дуги). Рисуется для левого верхнего угла и отражается.
  const cornerPath = (gx: number, gy: number) => `path("M0 0 H${gx + R} V${gy} A${R} ${R} 0 0 0 ${gx} ${gy + R} H0 Z")`;

  interface Zone {
    dir: ResizeDirection;
    style: string;
  }
  const zones = $derived.by((): Zone[] => {
    const z: Zone[] = [];
    // края: отступ от угла — там, где угол есть
    const cl = f.left ? f.left + R : 0;
    const cr = f.right ? f.right + R : 0;
    const ct = f.top ? f.top + R : 0;
    const cb = f.bottom ? f.bottom + R : 0;
    if (f.top) z.push({ dir: "North", style: `top:0;left:${cl}px;right:${cr}px;height:${f.top}px;cursor:ns-resize` });
    if (f.bottom) z.push({ dir: "South", style: `bottom:0;left:${cl}px;right:${cr}px;height:${f.bottom}px;cursor:ns-resize` });
    if (f.left) z.push({ dir: "West", style: `left:0;top:${ct}px;bottom:${cb}px;width:${f.left}px;cursor:ew-resize` });
    if (f.right) z.push({ dir: "East", style: `right:0;top:${ct}px;bottom:${cb}px;width:${f.right}px;cursor:ew-resize` });
    const corner = (gx: number, gy: number, pos: string, flip: string, cursor: string) =>
      `${pos};width:${gx + R}px;height:${gy + R}px;clip-path:${cornerPath(gx, gy)};transform:${flip};cursor:${cursor}`;
    if (f.top && f.left) z.push({ dir: "NorthWest", style: corner(f.left, f.top, "top:0;left:0", "none", "nwse-resize") });
    if (f.top && f.right) z.push({ dir: "NorthEast", style: corner(f.right, f.top, "top:0;right:0", "scaleX(-1)", "nesw-resize") });
    if (f.bottom && f.left) z.push({ dir: "SouthWest", style: corner(f.left, f.bottom, "bottom:0;left:0", "scaleY(-1)", "nesw-resize") });
    if (f.bottom && f.right) z.push({ dir: "SouthEast", style: corner(f.right, f.bottom, "bottom:0;right:0", "scale(-1,-1)", "nwse-resize") });
    return z;
  });

  function down(e: MouseEvent, dir: ResizeDirection) {
    if (e.button !== 0) return;
    e.preventDefault();
    void startResize(dir);
  }
</script>

{#each zones as z (z.dir)}
  <div
    class="zone"
    style={z.style}
    aria-hidden="true"
    onmousedown={(e) => down(e, z.dir)}
    oncontextmenu={(e) => e.preventDefault()}
  ></div>
{/each}

<style>
  .zone {
    position: fixed;
    z-index: 1000;
  }
</style>
