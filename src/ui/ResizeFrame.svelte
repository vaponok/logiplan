<script lang="ts">
  // Невидимая рамка в прозрачной полосе вокруг окна (там, где тень): за неё
  // окно растягивается, как за край обычного окна Windows. Самые внешние
  // ~4 px Tauri обрабатывает сам; это — остальная ширина полосы.
  import { startResize, type ResizeDirection } from "../lib/platform";

  const zones: Array<{ dir: ResizeDirection; cls: string }> = [
    { dir: "North", cls: "n" },
    { dir: "South", cls: "s" },
    { dir: "West", cls: "w" },
    { dir: "East", cls: "e" },
    { dir: "NorthWest", cls: "nw" },
    { dir: "NorthEast", cls: "ne" },
    { dir: "SouthWest", cls: "sw" },
    { dir: "SouthEast", cls: "se" },
  ];

  function down(e: MouseEvent, dir: ResizeDirection) {
    if (e.button !== 0) return;
    e.preventDefault();
    void startResize(dir);
  }
</script>

{#each zones as z (z.cls)}
  <div class="zone {z.cls}" aria-hidden="true" onmousedown={(e) => down(e, z.dir)}></div>
{/each}

<style>
  .zone {
    position: fixed;
    z-index: 1000;
    /* угол чуть заходит на скруглённый край окна — там его прозрачная часть */
    --c: calc(var(--win-gutter) + 10px);
  }
  .n,
  .s {
    left: var(--c);
    right: var(--c);
    height: var(--win-gutter);
    cursor: ns-resize;
  }
  .n {
    top: 0;
  }
  .s {
    bottom: 0;
  }
  .w,
  .e {
    top: var(--c);
    bottom: var(--c);
    width: var(--win-gutter);
    cursor: ew-resize;
  }
  .w {
    left: 0;
  }
  .e {
    right: 0;
  }
  .nw,
  .ne,
  .sw,
  .se {
    width: var(--c);
    height: var(--c);
    /* только сама полоса и угол окна, не его содержимое */
    clip-path: polygon(0 0, 100% 0, 100% var(--win-gutter), var(--win-gutter) var(--win-gutter), var(--win-gutter) 100%, 0 100%);
  }
  .nw {
    top: 0;
    left: 0;
    cursor: nwse-resize;
  }
  .ne {
    top: 0;
    right: 0;
    cursor: nesw-resize;
    transform: scaleX(-1);
  }
  .sw {
    bottom: 0;
    left: 0;
    cursor: nesw-resize;
    transform: scaleY(-1);
  }
  .se {
    bottom: 0;
    right: 0;
    cursor: nwse-resize;
    transform: scale(-1, -1);
  }
</style>
