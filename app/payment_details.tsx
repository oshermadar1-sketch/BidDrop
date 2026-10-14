// app/payment_details.tsx
// Payment summary screen with green gradient background (same vibe as home screens).
//
// Flow:
//  - Opened after escrow creation from assignment_details.
//  - Shows agreed price, basic assignment info, and payment status.
//  - Explains that actual money is NOT charged yet (logical escrow only).
//  - Single button to go back to home.

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";

import { getAssignmentById, type AssignmentDetailOut } from "../lib/api";

// ---- Brand palette (same as home pages) ----
const GREEN_1 = "#DDECCB";
const GREEN_2 = "#CBE1B4";
const GREEN_3 = "#BFD8A0";
const GREEN_4 = "#9BAC70";

const TXT = "#0b0b0b";
const BROWN = "#AF947E";
const CARD_BG = "rgba(255,255,255,0.94)";
const CARD_BORDER = "rgba(0,0,0,0.06)";

type Params = {
  token?: string;
  assignmentId?: string;
  escrowId?: string;
};

export default function PaymentDetails() {
  const router = useRouter();
  const { token, assignmentId, escrowId } = useLocalSearchParams<Params>();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assignment, setAssignment] = useState<AssignmentDetailOut | null>(
    null
  );

  // Load latest assignment data (price + payment_status + driver/request)
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        if (!assignmentId) {
          throw new Error("חסר מזהה שיוך (assignmentId)");
        }
        const data = await getAssignmentById(String(assignmentId));
        if (cancelled) return;
        setAssignment(data);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message || "שגיאה בטעינת נתוני התשלום");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [assignmentId]);

  const handleDone = () => {
    // Go back to main home page (kept as-is; can be changed to role-based redirect if needed)
    router.replace({
      pathname: "/home_page",
      params: { token },
    });
  };

  if (loading) {
    return (
      <LinearGradient
        colors={[GREEN_1, GREEN_2, GREEN_3, GREEN_4]}
        start={{ x: 1, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={S.gradient}
      >
        <View style={S.center}>
          <ActivityIndicator />
          <Text style={S.sub}>טוען פרטי תשלום…</Text>
        </View>
      </LinearGradient>
    );
  }

  if (error || !assignment) {
    return (
      <LinearGradient
        colors={[GREEN_1, GREEN_2, GREEN_3, GREEN_4]}
        start={{ x: 1, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={S.gradient}
      >
        <View style={S.center}>
          <Text style={S.err}>{error || "לא נמצאו נתונים לתשלום"}</Text>
          <TouchableOpacity onPress={handleDone} style={[S.btn, S.btnBrown]}>
            <Text style={S.btnText}>חזרה למסך הבית</Text>
          </TouchableOpacity>
        </View>
      </LinearGradient>
    );
  }

  const req = (assignment as any).request as {
    from_address?: string | null;
    to_address?: string | null;
  };

  const priceCents =
    typeof assignment.agreed_price_cents === "number"
      ? assignment.agreed_price_cents
      : null;
  const priceLabel =
    priceCents != null ? `${(priceCents / 100).toFixed(2)} ₪` : "—";

  const paymentStatusLabel = prettyPaymentStatus(assignment.payment_status);

  const driverName = assignment.driver?.full_name || "נהג ללא שם";

  const fromLabel = req?.from_address || "—";
  const toLabel = req?.to_address || "—";

  return (
    <LinearGradient
      colors={[GREEN_1, GREEN_2, GREEN_3, GREEN_4]}
      start={{ x: 1, y: 0 }}
      end={{ x: 0, y: 1 }}
      style={S.gradient}
    >
      <View style={S.page}>
        {/* Header + icon */}
        <View style={S.header}>
          <View style={S.headerRow}>
            <View style={S.iconCircle}>
              <Ionicons name="card" size={22} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={S.title}>פרטי תשלום</Text>
              <Text style={S.subtitle}>
                הפיקדון נשמר עבורך במערכת עבור השיוך הנוכחי.
              </Text>
            </View>
          </View>

          <View style={S.badgeRow}>
            <Ionicons name="shield-checkmark" size={16} color="#fff" />
            <Text style={S.badgeText}>אין חיוב מיידי, רק פיקדון לוגי</Text>
          </View>
        </View>

        {/* Amount card */}
        <View style={S.card}>
          <Text style={S.sectionTitle}>סכום התשלום שסוכם</Text>
          <Text style={S.amount}>{priceLabel}</Text>

          <View style={S.row}>
            <Text style={S.label}>סטטוס תשלום:</Text>
            <Text style={S.value}>{paymentStatusLabel}</Text>
          </View>

          {escrowId && (
            <View style={S.row}>
              <Text style={S.label}>מזהה פיקדון:</Text>
              <Text style={S.valueSmall} numberOfLines={1}>
                {escrowId}
              </Text>
            </View>
          )}
        </View>

        {/* Assignment details card */}
        <View style={S.card}>
          <Text style={S.sectionTitle}>פרטי השיוך</Text>
          <View style={S.row}>
            <Text style={S.label}>נהג:</Text>
            <Text style={S.value}>{driverName}</Text>
          </View>

          <View style={[S.routePill, { flexDirection: "row" }]}>
            <Text
              style={[S.routeText, { textAlign: "left" }]}
              numberOfLines={1}
            >
              {fromLabel}
            </Text>
            <Ionicons
              name="arrow-forward"
              size={18}
              color="#6b7280"
              style={{ marginHorizontal: 10, transform: [{ scaleX: -1 }] }}
            />
            <Text
              style={[S.routeText, { textAlign: "right" }]}
              numberOfLines={1}
            >
              {toLabel}
            </Text>
          </View>
        </View>

        {/* Explanation card */}
        <View style={S.card}>
          <Text style={S.sectionTitle}>מה קורה עכשיו?</Text>
          <Text style={S.body}>
            בשלב זה לא מתבצע חיוב בכרטיס אשראי. המערכת רק שומרת פיקדון לוגי
            בבלוקצ&apos;יין שמייצג התחייבות לתשלום לנהג בסיום המשלוח.
          </Text>
          <Text style={S.body}>
            לאחר שהמשלוח יסומן כמושלם ותאשר/י את המסירה, הפיקדון יסומן כתשלום
            שיש להעביר לנהג (לפי המנגנון שנקבע מחוץ לאפליקציה).
          </Text>
        </View>

        {/* Footer button */}
        <View style={S.footer}>
          <TouchableOpacity onPress={handleDone} style={[S.btn, S.btnBrown]}>
            <Text style={S.btnText}>אישור, אפשר להמשיך</Text>
          </TouchableOpacity>
        </View>
      </View>
    </LinearGradient>
  );
}

/* ---------------- helpers ---------------- */

function prettyPaymentStatus(s?: string | null) {
  if (!s) return "לא זמין";
  switch (s) {
    case "pending_deposit":
      return "ממתין להפקדת תשלום";
    case "deposited":
      return "תשלום הופקד";
    case "released":
      return "תשלום שוחרר";
    case "refunded":
      return "תשלום הוחזר";
    case "failed":
      return "תשלום נכשל";
    case "cancelled":
      return "תשלום בוטל";
    default:
      return s.replaceAll("_", " ");
  }
}

/* ---------------- styles ---------------- */

const S = StyleSheet.create({
  gradient: {
    flex: 1,
  },
  page: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 60,
    paddingBottom: 16,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingHorizontal: 16,
  },
  sub: { fontSize: 14, color: "#374151" },
  err: { fontSize: 14, color: "#b91c1c", textAlign: "center" },

  header: {
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 8,
  },
  iconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: BROWN,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 22,
    fontWeight: "900",
    color: TXT,
    textAlign: "left",
  },
  subtitle: {
    fontSize: 13,
    color: "#374151",
    marginTop: 2,
    textAlign: "left",
  },

  badgeRow: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(0,0,0,0.25)",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
  },
  badgeText: {
    color: "#fff",
    fontSize: 11,
    fontWeight: "600",
  },

  card: {
    backgroundColor: CARD_BG,
    borderRadius: 18,
    padding: 14,
    marginTop: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: CARD_BORDER,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "800",
    color: TXT,
    marginBottom: 8,
    textAlign: "left",
  },
  amount: {
    fontSize: 26,
    fontWeight: "900",
    color: TXT,
    marginBottom: 10,
    textAlign: "left",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 4,
  },
  label: {
    fontSize: 13,
    color: "#6b7280",
    marginLeft: 8,
  },
  value: {
    fontSize: 14,
    color: TXT,
    fontWeight: "700",
  },
  valueSmall: {
    fontSize: 11,
    color: TXT,
    flex: 1,
    textAlign: "left",
  },
  body: {
    fontSize: 13,
    color: "#374151",
    lineHeight: 20,
    textAlign: "left",
    marginTop: 4,
  },

  routePill: {
    marginTop: 10,
    alignSelf: "stretch",
    backgroundColor: "#f9fafb",
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  routeText: {
    color: TXT,
    fontWeight: "600",
    maxWidth: "40%",
  },

  footer: {
    marginTop: 18,
    alignItems: "center",
  },
  btn: {
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 999,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  btnBrown: {
    backgroundColor: BROWN,
  },
  btnText: {
    color: "#fff",
    fontWeight: "900",
    fontSize: 15,
  },
});
