// components/TrustStars.tsx
// Courier trust score (1..5) drawn as stars, an explanation of how it was computed,
// and a star picker for rating a courier.
import React, { useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

const STAR_COLOR = "#f59e0b";
const EMPTY_COLOR = "#d1d5db";

/** Read-only stars. Score is rounded to the nearest half star. */
export function TrustStars({
  score,
  isNew,
  numRatings,
  size = 18,
}: {
  score: number | null | undefined;
  isNew?: boolean | null;
  numRatings?: number | null;
  size?: number;
}) {
  if (score == null) {
    return <Text style={S.dim}>אין עדיין דירוג</Text>;
  }

  const halves = Math.round(Math.max(0, Math.min(5, score)) * 2);
  const icons = [0, 1, 2, 3, 4].map((i) => {
    const left = halves - i * 2;
    if (left >= 2) return "star" as const;
    if (left === 1) return "star-half" as const;
    return "star-outline" as const;
  });

  return (
    <View style={S.row}>
      {/* Stars always fill left to right, also in RTL */}
      <View style={[S.row, { direction: "ltr" }]}>
        {icons.map((name, i) => (
          <Ionicons
            key={i}
            name={name}
            size={size}
            color={name === "star-outline" ? EMPTY_COLOR : STAR_COLOR}
          />
        ))}
      </View>
      <Text style={S.score}>{score.toFixed(1)}</Text>
      {isNew ? (
        <View style={S.badge}>
          <Text style={S.badgeText}>שליח/ה חדש/ה</Text>
        </View>
      ) : numRatings ? (
        <Text style={S.dim}>({numRatings} דירוגים)</Text>
      ) : null}
    </View>
  );
}

export type TrustDetails = {
  trust_score?: number | null;
  customer_part?: number | null;
  model_part?: number | null;
  customer_weight?: number | null;
  model_weight?: number | null;
  num_ratings?: number | null;
  num_timed_deliveries?: number | null;
  is_new_courier?: boolean | null;
};

const pct = (w?: number | null) => `${Math.round((w ?? 0) * 100)}%`;
const num = (v?: number | null) => (v == null ? "—" : v.toFixed(2));

/** "How is the score calculated?" link that opens the trust score breakdown. */
export function TrustExplain({ d }: { d: TrustDetails }) {
  const [open, setOpen] = useState(false);
  if (d.trust_score == null || d.model_part == null) return null;

  const ratings = d.num_ratings ?? 0;
  const timed = d.num_timed_deliveries ?? 0;
  const summary =
    ratings === 0
      ? "שליח/ה חדש/ה: עדיין אין דירוגים, ולכן המודל קובע את כל הציון."
      : (d.customer_weight ?? 0) >= 0.69
      ? "שליח/ה ותיק/ה: הלקוחות קובעים 70% מהציון, המודל 30%."
      : `עם כל דירוג חלק הלקוחות גדל, עד 70% אחרי 20 דירוגים (עכשיו ${ratings}).`;

  return (
    <View>
      <TouchableOpacity onPress={() => setOpen((v) => !v)}>
        <Text style={S.link}>
          {open ? "הסתרת ההסבר ▲" : "איך חושב הציון? ▼"}
        </Text>
      </TouchableOpacity>

      {open && (
        <View style={S.explain}>
          <View style={S.explainRow}>
            <Text style={S.explainLabel}>👥 דירוג לקוחות</Text>
            <Text style={S.explainValue}>
              {ratings > 0 ? num(d.customer_part) : "אין עדיין"} ({ratings}{" "}
              דירוגים) × {pct(d.customer_weight)}
            </Text>
          </View>
          <View style={S.explainRow}>
            <Text style={S.explainLabel}>🧠 ציון ביצועים (למידת מכונה)</Text>
            <Text style={S.explainValue}>
              {num(d.model_part)} ({timed} משלוחים נמדדו) ×{" "}
              {pct(d.model_weight)}
            </Text>
          </View>
          <View style={S.explainDivider} />
          <View style={S.explainRow}>
            <Text style={[S.explainLabel, { fontWeight: "800" }]}>
              ⭐ ציון סופי
            </Text>
            <Text style={[S.explainValue, { fontWeight: "800" }]}>
              {num(d.trust_score)}
            </Text>
          </View>
          <Text style={S.explainNote}>{summary}</Text>
          <Text style={S.explainNote}>
            ציון ביצועים: מודל אחד חוזה כמה זמן המשלוח אמור לקחת (מסלול, מזג
            אוויר, שעה). מודל שני, שלמד מ-27 אלף משלוחים איך לקוחות מדרגים לפי
            איחור, נותן לכל משלוח את הדירוג הצפוי. שליח/ה חדש/ה מתחיל/ה מהציון
            של שליח טיפוסי.
          </Text>
        </View>
      )}
    </View>
  );
}

/** Tappable stars for choosing a 1..5 rating. */
export function StarPicker({
  value,
  onChange,
  size = 36,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  size?: number;
  disabled?: boolean;
}) {
  return (
    <View style={[S.row, { direction: "ltr", gap: 8 }]}>
      {[1, 2, 3, 4, 5].map((v) => (
        <TouchableOpacity
          key={v}
          onPress={() => onChange(v)}
          disabled={disabled}
          accessibilityLabel={`${v} כוכבים`}
        >
          <Ionicons
            name={v <= value ? "star" : "star-outline"}
            size={size}
            color={v <= value ? STAR_COLOR : EMPTY_COLOR}
          />
        </TouchableOpacity>
      ))}
    </View>
  );
}

const S = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 4 },
  score: { fontWeight: "800", color: "#0b0b0b", fontSize: 14 },
  dim: { color: "#6b7280", fontSize: 12 },
  badge: {
    backgroundColor: "#eef2e3",
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  badgeText: { color: "#5c6b3a", fontSize: 11, fontWeight: "700" },
  link: {
    color: "#5c6b3a",
    fontSize: 13,
    fontWeight: "700",
    textAlign: "right",
    textDecorationLine: "underline",
  },
  explain: {
    marginTop: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: "#e5e7eb",
    gap: 6,
  },
  explainRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  explainLabel: { color: "#111827", fontSize: 13 },
  explainValue: { color: "#111827", fontSize: 13 },
  explainDivider: { height: 1, backgroundColor: "#e5e7eb", marginVertical: 2 },
  explainNote: { color: "#6b7280", fontSize: 12, textAlign: "right" },
});
