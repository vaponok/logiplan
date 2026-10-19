<script lang="ts">
  // Числовое поле как QSpinBox без стрелок: границы, ↑/↓ и колесо мыши.
  let {
    value,
    min,
    max,
    onchange,
    width = "64px",
    title = undefined,
    decimals = 0,
    step: stepSize = 1,
  }: {
    value: number;
    min: number;
    max: number;
    onchange: (v: number) => void;
    width?: string;
    title?: string;
    /** знаков после запятой (0 — целые) */
    decimals?: number;
    /** шаг стрелок и колеса */
    step?: number;
  } = $props();

  let text = $state("");
  let focused = $state(false);
  $effect(() => {
    if (!focused) text = String(value);
  });

  const k = $derived(10 ** decimals);
  const clamp = (n: number) => Math.min(max, Math.max(min, decimals ? Math.round(n * k) / k : Math.trunc(n)));
  // дробные можно вводить и через запятую
  const parse = (t: string) => Number(t.trim().replace(",", "."));

  function commit() {
    const n = parse(text);
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
      step(stepSize);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      step(-stepSize);
    } else if (e.key === "Enter") {
      commit();
    }
  }

  function onwheel(e: WheelEvent) {
    if (!focused) return;
    e.preventDefault();
    step(e.deltaY < 0 ? stepSize : -stepSize);
  }
</script>

<input
  class="field"
  type="text"
  inputmode={decimals ? "decimal" : "numeric"}
  style:width
  {title}
  bind:value={text}
  onfocus={() => (focused = true)}
  onblur={() => {
    focused = false;
    commit();
  }}
  oninput={() => {
    const n = parse(text);
    if (text.trim() !== "" && Number.isFinite(n) && n >= min && n <= max && clamp(n) === n) onchange(n);
  }}
  {onkeydown}
  {onwheel}
/>
