export function quantityValue(input: string): number | null {
  if (!/^\d+(\.\d+)?$/.test(input.trim())) return null;
  const value = Number(input);
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function grossProceeds(quantity: string, price: string | null): number | null {
  const amount = quantityValue(quantity);
  if (amount === null || price === null || !Number.isFinite(Number(price)) || Number(price) <= 0) return null;
  const total = amount * Number(price);
  return Number.isFinite(total) && total > 0 ? total : null;
}

export function proceeds(quantity: string, latest: string | null, forecast: string | null) {
  const observed = grossProceeds(quantity, latest), estimated = grossProceeds(quantity, forecast);
  return {observed, estimated, difference: observed === null || estimated === null ? null : estimated - observed};
}
