// Мелкие совместимые с Python функции: без них вывод (числа, обрезка
// строк, округление) расходился бы со старой версией в краевых случаях.

// Символы, которые Python считает пробельными (str.isspace / str.split()).
const PY_WS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const STRIP_RE = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, "g");
const RSTRIP_RE = new RegExp(`[${PY_WS}]+$`);
const SPLIT_RE = new RegExp(`[${PY_WS}]+`);
const LINE_BREAK_RE = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;

/** str.strip() */
export function strip(s: string): string {
  return s.replace(STRIP_RE, "");
}

/** str.rstrip() */
export function rstrip(s: string): string {
  return s.replace(RSTRIP_RE, "");
}

/** str.split() без аргументов: по любым пробелам, без пустых кусков. */
export function splitWs(s: string): string[] {
  return s.split(SPLIT_RE).filter((p) => p !== "");
}

/** str.splitlines() — без пустого хвоста после финального перевода строки. */
export function splitlines(s: string): string[] {
  if (!s) return [];
  const parts = s.split(LINE_BREAK_RE);
  if (parts.length && parts[parts.length - 1] === "") parts.pop();
  return parts;
}

/** int(s) для уже обрезанной строки; null вместо ValueError. */
export function pyInt(s: string): number | null {
  const t = strip(s);
  if (!/^[+-]?\d+(?:_\d+)*$/.test(t)) return null;
  return parseInt(t.replace(/_/g, ""), 10);
}

/** round(x) — банковское округление до целого (как в Python 3). */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/**
 * round(x, nd) — Python округляет точное двоичное значение, а при точной
 * середине выбирает чётную цифру. toFixed() округляет так же точно, но
 * середину всегда вверх, поэтому середину ловим отдельно.
 */
export function pyRoundTo(x: number, nd: number): number {
  if (!Number.isFinite(x)) return x;
  const exact = Math.abs(x).toFixed(100);
  const dot = exact.indexOf(".");
  const tail = exact.slice(dot + 1 + nd);
  const isTie = tail[0] === "5" && /^50*$/.test(tail);
  if (!isTie) return Number(x.toFixed(nd));
  // Точная середина: отбрасываем хвост и смотрим на последнюю цифру.
  const truncated = exact.slice(0, dot + 1 + nd);
  const lastDigit = Number(truncated[truncated.length - 1]);
  const down = Number(truncated);
  const step = Math.pow(10, -nd);
  const magnitude = lastDigit % 2 === 0 ? down : Number((down + step).toFixed(nd));
  return x < 0 ? -magnitude : magnitude;
}

/** repr(float): 12.0, 3.25, 1e-05 … */
export function floatRepr(x: number): string {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const ax = Math.abs(x);
  if (ax >= 1e16 || ax < 1e-4) {
    // Python: мантисса без лишних нулей, экспонента минимум из двух цифр.
    const [mant, exp] = x.toExponential().split("e");
    const sign = exp[0] === "-" ? "-" : "+";
    const digits = exp.replace(/^[+-]/, "").padStart(2, "0");
    return `${mant}e${sign}${digits}`;
  }
  const s = String(x);
  return Number.isInteger(x) ? `${s}.0` : s;
}

/** Строковое представление числа так, как его печатал бы Python. */
export function pyNum(x: number, isFloat: boolean): string {
  return isFloat ? floatRepr(x) : String(x);
}

/** str.format(**kw) для простых шаблонов вида {name}; бросает, как KeyError. */
export function pyFormat(template: string, kw: Record<string, unknown>): string {
  return template.replace(/\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (m, key: string | undefined) => {
    if (m === "{{") return "{";
    if (m === "}}") return "}";
    if (key !== undefined && Object.prototype.hasOwnProperty.call(kw, key)) return String(kw[key]);
    throw new Error(`KeyError: ${key}`);
  });
}

/** Сравнение строк как в Python (по кодовым точкам), для sort(). */
export function cmpStr(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/** Python-сравнение кортежей чисел. */
export function cmpTuple(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return a.length - b.length;
}

/** Python `//` для целых. */
export function floorDiv(a: number, b: number): number {
  return Math.floor(a / b);
}
