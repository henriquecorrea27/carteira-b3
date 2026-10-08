import { describe, expect, it } from "vitest";
import { buildAnalysis, buildPositions, buildReturnSeries, buildSummary } from "./data";

describe("demo data is internally consistent", () => {
  const positions = buildPositions();

  it("summary equity equals the sum of positions", () => {
    const sum = positions.reduce((a, p) => a + Number(p.market_value), 0);
    expect(Number(buildSummary().equity)).toBeCloseTo(sum, 2);
  });

  it("weights add up to 100%", () => {
    expect(positions.reduce((a, p) => a + Number(p.weight_pct), 0)).toBeCloseTo(100, 0);
  });

  it("position rules match the analysis screen", () => {
    for (const p of positions.filter((x) => x.rules)) {
      const a = buildAnalysis(p.ticker)!;
      expect(p.rules!.score_final).toBe(a.score_final);
      expect(p.rules!.decision).toBe(a.decision);
    }
  });

  it("shows every decision at least once (so every UI state is visible)", () => {
    const decisions = new Set(positions.map((p) => p.rules?.decision).filter(Boolean));
    expect([...decisions].sort()).toEqual(["AVOID", "BUY", "WAIT"]);
  });

  it("return series ends at the summary's total return", () => {
    const series = buildReturnSeries();
    expect(series.at(-1)!.portfolio_pct).toBe(buildSummary().total_return_pct);
  });
});
