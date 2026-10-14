// app/ui/theme.ts
// Design tokens shared across screens

export const COLORS = {
  // Base
  bg: "#ffffff",
  text: "#0B0B0B",
  dim: "#6B7280",
  border: "#E5E7EB",
  card: "#ffffff",

  // Brand (match app CTAs)
  primary: "#C19A6B", // CTA, highlights (זהה ל-green4)
  primaryDark: "#8E6B3A", // Headlines / emphasis on light bg
  primaryOn: "#0B0B0B", // Text color on primary

  // Mocha accents
  mocha: "#8B5E3C",
  borderMocha: "rgba(139, 94, 60, 0.35)", // for card borders
  softMocha: "#F1E6DE", // warm beige solid
  softMochaTranslucent: "rgba(139, 94, 60, 0.22)", // translucent card bg

  // Pastel backgrounds (no pink)
  softSage: "#F1F6EA", // gentle green
  softSlate: "#F6F7F9", // neutral gray

  // Sender Home gradient stops (greens)
  green1: "#DDECCB",
  green2: "#CBE1B4",
  green3: "#BFD8A0",
  green4: "#9BAC70", // equals primary
};

export const RAD = { xs: 8, sm: 12, md: 16, lg: 20, pill: 999 };

export const SHADOW = {
  card: {
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
};
