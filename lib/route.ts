// lib/route.ts
// One way to show a route on every screen: destination ← origin.
// A Hebrew reader starts on the right at the origin and follows the arrow to the
// destination; the arrow also points at the destination for a left-to-right glance.
//
// The whole line is wrapped in a left-to-right isolate (LRI ... PDI) so its order never
// depends on the language of the first address, and each address sits in its own
// first-strong isolate (FSI ... PDI) so Hebrew and English addresses keep their own order.
const LRI = "\u2066";
const FSI = "\u2068";
const PDI = "\u2069";

const isolate = (text: string) => `${FSI}${text}${PDI}`;

export function routeLine(
  from?: string | null,
  to?: string | null,
  fallback: { from: string; to: string } = { from: "מוצא לא ידוע", to: "יעד לא ידוע" }
): string {
  const origin = (from ?? "").trim() || fallback.from;
  const destination = (to ?? "").trim() || fallback.to;
  return `${LRI}${isolate(destination)} ← ${isolate(origin)}${PDI}`;
}
