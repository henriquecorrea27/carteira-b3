import { describe, expect, it } from "vitest";
import {
  formatBRL,
  formatBRLCompact,
  formatDate,
  formatDateTimeShort,
  formatDayMonth,
  formatMonthLong,
  formatMonthShort,
  formatMultiple,
  formatNumber,
  formatPct,
  formatQuantity,
  parseDecimalInput,
  signOf,
  toNumber,
} from "./format";

describe("formatBRL", () => {
  it("formats decimal strings in pt-BR", () => {
    expect(formatBRL("1234.56")).toBe("R$ 1.234,56");
    expect(formatBRL("0")).toBe("R$ 0,00");
    expect(formatBRL(1000000)).toBe("R$ 1.000.000,00");
  });
  it("uses a true minus sign for negatives and an optional plus", () => {
    expect(formatBRL("-12.5")).toBe("−R$ 12,50");
    expect(formatBRL("12.5", { signed: true })).toBe("+R$ 12,50");
    expect(formatBRL("0", { signed: true })).toBe("R$ 0,00");
    expect(formatBRL("-0.001")).toBe("R$ 0,00");
  });
  it("keeps up to 4 decimals when precise (per-share values)", () => {
    expect(formatBRL("0.0243", { precise: true })).toBe("R$ 0,0243");
    expect(formatBRL("0.5", { precise: true })).toBe("R$ 0,50");
  });
  it("returns a dash for missing values", () => {
    expect(formatBRL(null)).toBe("—");
    expect(formatBRL("abc")).toBe("—");
  });
});

describe("formatBRLCompact", () => {
  it("compacts thousands and millions", () => {
    expect(formatBRLCompact(48500)).toBe("R$ 48,5 mil");
    expect(formatBRLCompact(1200000)).toBe("R$ 1,2 mi");
    expect(formatBRLCompact(950)).toBe("R$ 950");
    expect(formatBRLCompact(-2000)).toBe("−R$ 2 mil");
  });
});

describe("numbers and percentages", () => {
  it("formats numbers", () => {
    expect(formatNumber("1234.5")).toBe("1.234,5");
    expect(formatNumber(2, { minDecimals: 2 })).toBe("2,00");
    expect(formatQuantity("33.33")).toBe("33,33");
    expect(formatQuantity("100")).toBe("100");
  });
  it("formats percentage points", () => {
    expect(formatPct("14.7")).toBe("14,70%");
    expect(formatPct("14.7", { decimals: 1 })).toBe("14,7%");
    expect(formatPct("-3.215", { decimals: 2 })).toBe("−3,22%");
    expect(formatPct("2", { signed: true, decimals: 1 })).toBe("+2,0%");
    expect(formatPct("-0.001", { decimals: 1 })).toBe("0,0%");
  });
  it("formats multiples", () => {
    expect(formatMultiple("8.43")).toBe("8,4x");
  });
  it("parses and signs", () => {
    expect(toNumber("1.5")).toBe(1.5);
    expect(toNumber("")).toBeNull();
    expect(signOf("-2")).toBe(-1);
    expect(signOf("0")).toBe(0);
    expect(signOf(null)).toBe(0);
  });
});

describe("dates", () => {
  it("formats ISO dates without timezone drift", () => {
    expect(formatDate("2026-01-01")).toBe("01/01/2026");
    expect(formatDate("2026-10-08T00:00:00Z")).toBe("08/10/2026");
    expect(formatDayMonth("2026-10-08")).toBe("08/10");
    expect(formatDate(null)).toBe("—");
    expect(formatDateTimeShort("2026-10-08T18:05:00-03:00")).toBe("08/10 18:05");
  });
  it("formats months", () => {
    expect(formatMonthShort("2026-03")).toBe("mar/26");
    expect(formatMonthLong("2026-03-15")).toBe("março de 2026");
  });
});

describe("parseDecimalInput", () => {
  it("accepts pt-BR and dot decimals", () => {
    expect(parseDecimalInput("1.234,56")).toBe("1234.56");
    expect(parseDecimalInput("R$ 10,5")).toBe("10.5");
    expect(parseDecimalInput("12.34")).toBe("12.34");
    expect(parseDecimalInput("1.000")).toBe("1000");
    expect(parseDecimalInput("abc")).toBeNull();
    expect(parseDecimalInput("")).toBeNull();
  });
});
