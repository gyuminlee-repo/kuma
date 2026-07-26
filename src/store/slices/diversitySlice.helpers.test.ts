import { describe, expect, it } from "vitest";
import { combinatorialFraction, countSubstitutionTokens } from "./diversitySlice.helpers";

describe("countSubstitutionTokens", () => {
  it("counts a single substitution as 1", () => {
    expect(countSubstitutionTokens("A10C")).toBe(1);
  });

  it("counts every substitution token in a colon-separated combo", () => {
    expect(countSubstitutionTokens("L59M:W60T:K64W")).toBe(3);
  });

  it("returns 0 when no substitution token is found", () => {
    expect(countSubstitutionTokens("not-a-variant")).toBe(0);
  });
});

describe("combinatorialFraction", () => {
  it("returns 0 for an all-single-substitution pool", () => {
    expect(combinatorialFraction(["A10C", "B20D", "C30E"])).toBe(0);
  });

  it("returns 1 for an all-combo pool", () => {
    expect(combinatorialFraction(["L59M:W60T", "A10C:B20D:C30E"])).toBe(1);
  });

  it("returns the correct fraction for a mixed pool", () => {
    expect(combinatorialFraction(["A10C", "L59M:W60T", "B20D", "C30E:D40F"])).toBe(0.5);
  });

  it("returns 0 for an empty pool without dividing by zero", () => {
    expect(combinatorialFraction([])).toBe(0);
  });
});
