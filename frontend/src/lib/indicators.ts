/** Simple moving average aligned with `values`: null until `days` values exist. */
export function sma(values: number[], days: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  values.forEach((v, i) => {
    sum += v;
    if (i >= days) sum -= values[i - days];
    out.push(i >= days - 1 ? sum / days : null);
  });
  return out;
}
