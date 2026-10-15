<script lang="ts">
  // Флаги рисуются вектором, как в make_flag_pixmap() старой версии.
  import type { Lang } from "../core/i18n";
  let { kind, w = 34, h = 22 }: { kind: Lang; w?: number; h?: number } = $props();
</script>

<svg width={w} height={h} viewBox="0 0 {w} {h}" aria-hidden="true">
  {#if kind === "ru"}
    <rect x="0" y="0" width={w} height={h / 3 + 0.5} fill="#ffffff" />
    <rect x="0" y={h / 3} width={w} height={h / 3 + 0.5} fill="#0039A6" />
    <rect x="0" y={(2 * h) / 3} width={w} height={h / 3 + 0.5} fill="#D52B1E" />
  {:else if kind === "fr"}
    <rect x="0" y="0" width={w / 3 + 0.5} height={h} fill="#0055A4" />
    <rect x={w / 3} y="0" width={w / 3 + 0.5} height={h} fill="#ffffff" />
    <rect x={(2 * w) / 3} y="0" width={w / 3 + 0.5} height={h} fill="#EF4135" />
  {:else}
    <rect x="0" y="0" width={w} height={h} fill="#00247D" />
    <g stroke-linecap="butt">
      <path d="M0 0 L{w} {h} M0 {h} L{w} 0" stroke="#fff" stroke-width={h * 0.3} />
      <path d="M0 0 L{w} {h} M0 {h} L{w} 0" stroke="#CF142B" stroke-width={h * 0.12} />
      <path d="M{w / 2} 0 L{w / 2} {h} M0 {h / 2} L{w} {h / 2}" stroke="#fff" stroke-width={h * 0.4} />
      <path d="M{w / 2} 0 L{w / 2} {h} M0 {h / 2} L{w} {h / 2}" stroke="#CF142B" stroke-width={h * 0.2} />
    </g>
  {/if}
</svg>

<style>
  svg {
    display: block;
    border-radius: 2px;
  }
</style>
