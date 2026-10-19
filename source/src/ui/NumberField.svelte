<script lang="ts">
  // Числовое поле как QSpinBox без стрелок: границы, ↑/↓ и колесо мыши.
  let {
    value,
    min,
    max,
    onchange,
    width = "64px",
    title = undefined,
  }: {
    value: number;
    min: number;
    max: number;
    onchange: (v: number) => void;
    width?: string;
    title?: string;
  } = $props();

  let text = $state("");
  let focused = $state(false);
  $effect(() => {
    if (!focused) text = String(value);
  });

  const clamp = (n: number) => Math.min(max, Math.max(min, Math.trunc(n)));

  function commit() {
    const n = Number(text.trim());
    const v = Number.isFinite(n) && text.trim() !== "" ? clamp(n) : value;
    text = String(v);
    if (v !== value) onchange(v);
  }

  function step(d: number) {
    const v = clamp(value + d);
    text = String(v);
    if (v !== value) onchange(v);
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      step(1);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      step(-1);
    } else if (e.key === "Enter") {
      commit();
    }
  }

  function onwheel(e: WheelEvent) {
    if (!focused) return;
    e.preventDefault();
    step(e.deltaY < 0 ? 1 : -1);
  }
</script>

<input
  class="field"
  type="text"
  inputmode="numeric"
  style:width
  {title}
  bind:value={text}
  onfocus={() => (focused = true)}
  onblur={() => {
    focused = false;
    commit();
  }}
  oninput={() => {
    const n = Number(text.trim());
    if (text.trim() !== "" && Number.isFinite(n) && n >= min && n <= max && Math.trunc(n) === n) onchange(n);
  }}
  {onkeydown}
  {onwheel}
/>
