// The route line reads destination ← origin, whatever the language of the addresses.
import { routeLine } from "../lib/route";

const LRI = "\u2066";
const FSI = "\u2068";
const PDI = "\u2069";
const strip = (s: string) => s.replace(/[\u2066\u2068\u2069]/g, "");

describe("routeLine", () => {
  test("puts the destination first and the origin after the arrow", () => {
    expect(strip(routeLine("דיזנגוף 50", "ויצמן 2"))).toBe("ויצמן 2 ← דיזנגוף 50");
  });

  test("isolates each address inside a left-to-right line", () => {
    expect(routeLine("A", "B")).toBe(`${LRI}${FSI}B${PDI} ← ${FSI}A${PDI}${PDI}`);
  });

  test("keeps the same order for English addresses", () => {
    expect(strip(routeLine("Boston Consulting Group", "Abba Hillel"))).toBe(
      "Abba Hillel ← Boston Consulting Group"
    );
  });

  test("falls back to placeholders for missing addresses", () => {
    expect(strip(routeLine(null, "  "))).toBe("יעד לא ידוע ← מוצא לא ידוע");
    expect(strip(routeLine("x", null, { from: "?", to: "כל יעד" }))).toBe("כל יעד ← x");
  });
});
