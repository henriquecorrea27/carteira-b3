import { describe, expect, it } from "vitest";
import { sma } from "./indicators";

describe("sma", () => {
  it("averages the last n values and is null before n values exist", () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4]);
  });

  it("is all null with fewer values than the window", () => {
    expect(sma([10, 11], 200)).toEqual([null, null]);
  });
});
