import { describe, expect, it } from "vitest";
import type { Dividend } from "@/api/types";
import { agenda, byAsset, monthlyBars, yearMonthTable } from "./aggregate";

let id = 0;
function div(p: Partial<Dividend> & Pick<Dividend, "ticker" | "net" | "ex_date">): Dividend {
  return {
    id: ++id,
    asset_class: "STOCK",
    type: "DIVIDEND",
    status: "PAID",
    pay_date: p.ex_date,
    quantity: "100",
    amount_per_share: "0.1",
    gross: p.net,
    tax: "0",
    source: "AUTO",
    ...p,
  };
}

const TODAY = "2026-10-08";
const data: Dividend[] = [
  div({ ticker: "AAA3", net: "10.00", ex_date: "2026-09-01", pay_date: "2026-09-20" }),
  div({ ticker: "AAA3", net: "5.50", ex_date: "2026-10-01", pay_date: "2026-10-05" }),
  div({ ticker: "BBB4", net: "20.00", ex_date: "2026-10-02", pay_date: "2026-11-10", status: "ANNOUNCED" }),
  div({ ticker: "BBB4", net: "7.00", ex_date: "2025-03-01", pay_date: "2025-03-15", status: "CONFIRMED" }),
  div({ ticker: "CCC11", net: "3.00", ex_date: "2026-10-14", pay_date: null, status: "ANNOUNCED" }),
];

describe("monthlyBars", () => {
  it("spans 12 months back plus announced future months", () => {
    const bars = monthlyBars(data, TODAY);
    expect(bars[0].month).toBe("2025-11");
    expect(bars.at(-1)!.month).toBe("2026-11");
    expect(bars.find((b) => b.month === "2026-09")!.received).toBe(10);
    expect(bars.find((b) => b.month === "2026-10")).toEqual({ month: "2026-10", received: 5.5, receivable: 3 });
    expect(bars.find((b) => b.month === "2026-11")!.receivable).toBe(20);
  });
});

describe("yearMonthTable", () => {
  it("sums received per month and averages by elapsed months", () => {
    const rows = yearMonthTable(data, TODAY);
    expect(rows.map((r) => r.year)).toEqual([2026, 2025]);
    expect(rows[0].months[8]).toBe(10);
    expect(rows[0].total).toBe(15.5);
    expect(rows[0].average).toBeCloseTo(1.55);
    expect(rows[1].average).toBeCloseTo(7 / 12);
  });
});

describe("byAsset", () => {
  it("only counts received inside the window", () => {
    expect(byAsset(data, "2025-10-08", TODAY)).toEqual([{ ticker: "AAA3", total: 15.5 }]);
  });
});

describe("agenda", () => {
  it("lists future data-com and payment dates in order", () => {
    const items = agenda(data, TODAY).map((i) => `${i.date}:${i.kind}:${i.dividend.ticker}`);
    expect(items).toEqual(["2026-10-14:EX_DATE:CCC11", "2026-11-10:PAYMENT:BBB4"]);
  });
});
