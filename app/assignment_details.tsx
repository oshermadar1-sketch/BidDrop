// app/assignment_details.tsx
// Driver-safe matching (no fake matches): prefer server data by assignment_id.

import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  View,
  Text,
  ActivityIndicator,
  StyleSheet,
  TouchableOpacity,
  Image,
  Dimensions,
  Alert,
  ScrollView,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useFocusEffect } from "@react-navigation/native";
import * as Linking from "expo-linking";
import Svg, { Path } from "react-native-svg";
import { Ionicons } from "@expo/vector-icons";

import {
  listSenderRequests,
  listRiderRequests,
  checkOfferMatchStatus,
  getAssignmentByRequest,
  getAssignmentById, // ← prefer fetching by assignment id when available
  initiateEscrow, // ← new: create escrow on pay click
  rateDriver,
  type RequestRow,
  type RiderRequestRow,
  type AssignmentDetailOut,
} from "../lib/api";
import {
  TrustStars,
  TrustExplain,
  StarPicker,
} from "../components/TrustStars";

// ---- Theme & layout constants ----
const GREEN = "#9BAC70";
const BROWN = "#AF947E"; // softer taupe-brown accent
const BG = "#f7f7f5";
const TXT = "#0b0b0b";
const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");
const WAVE_H = Math.max(360, Math.floor(SCREEN_H * 0.5));
const HERO_H = 440;

// Hero images (transparent PNGs)
const pkgImg = require("../assets/images/package_image.png");
const rideImg = require("../assets/images/green_car.png");

type Role = "sender" | "rider" | "driver";
type RequestLite = {
  id: string;
  type: "package" | "ride" | "passenger";
  from_address?: string | null;
  to_address?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  notes?: string | null;
};

export default function AssignmentDetails() {
  const router = useRouter();
  const { role, token, requestId, offerId, home, assignmentId } =
    useLocalSearchParams<{
      role: Role;
      token: string;
      requestId?: string;
      offerId?: string;
      home?: string;
      assignmentId?: string;
    }>();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [resolvedRequestId, setResolvedRequestId] = useState<string | null>(
    null
  );
  const [assignmentIdLocal, setAssignmentIdLocal] = useState<string | null>(
    null
  ); // ✅ prefer this if present

  const [assignment, setAssignment] = useState<AssignmentDetailOut | null>(
    null
  );
  const [requestMeta, setRequestMeta] = useState<RequestLite | null>(null);
  const [isDriverMatched, setIsDriverMatched] = useState(false);
  const [paying, setPaying] = useState(false); // ← payment in-flight flag
  const [ratingValue, setRatingValue] = useState(0); // customer's chosen stars (0 = none yet)
  const [ratingSending, setRatingSending] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  // Reset state when role/offer changes
  useEffect(() => {
    setResolvedRequestId(null);
    setAssignmentIdLocal(null);
    setAssignment(null);
    setRequestMeta(null);
    setIsDriverMatched(false);
    setError(null);
  }, [role, offerId, requestId]);

  // -------- Resolve request/assignment id (role-safe) --------
  useEffect(() => {
    let cancelled = false;

    async function resolveIds() {
      setLoading(true);
      setError(null);

      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      try {
        if (!token) throw new Error("missing token");
        const r: Role = (role as Role) || "sender";

        if (r === "sender") {
          if (requestId) {
            setResolvedRequestId(String(requestId));
          } else {
            const buckets: ("active" | "open")[] = ["active", "open"];
            let found: RequestRow | null = null;
            for (const b of buckets) {
              const rows = await listSenderRequests(String(token), b, {
                limit: 50,
              });
              found = rows[0] ?? null;
              if (found) break;
            }
            if (!found) throw new Error("לא נמצאה בקשה להצגה");
            setResolvedRequestId(String(found.id));
          }
        } else if (r === "rider") {
          if (requestId) {
            setResolvedRequestId(String(requestId));
          } else {
            const buckets: ("active" | "open")[] = ["active", "open"];
            let found: RiderRequestRow | null = null;
            for (const b of buckets) {
              const rows = await listRiderRequests(String(token), b, {
                limit: 50,
              });
              found = rows[0] ?? null;
              if (found) break;
            }
            if (!found) throw new Error("לא נמצאה בקשה להצגה");
            setResolvedRequestId(String(found.id));
          }
        } else {
          // DRIVER:
          // If navigated with assignmentId (best), we are good.
          if (assignmentId) {
            setIsDriverMatched(true);
            // requestId is optional; it will be confirmed from the server payload.
            if (requestId) setResolvedRequestId(String(requestId));
            setLoading(false);
            return;
          }

          if (!offerId)
            throw new Error("אין הצעה פתוחה להצגת התאמה (offerId חסר)");

          // Ask backend for THIS offer only (backend should verify by offer_id/created_at)
          let reqId = "";
          let asgId = "";

          const pollUntil = Date.now() + 9000;
          while (Date.now() < pollUntil && !asgId) {
            try {
              const st = await checkOfferMatchStatus(
                String(token),
                String(offerId)
              );
              if (st?.status === "matched") {
                asgId = String(st.assignment_id || "");
                reqId = String(st.request_id || "");
                break;
              }
            } catch {}
            await new Promise((r) => setTimeout(r, 1000));
          }

          if (!asgId && !reqId) throw new Error("עדיין אין התאמה להצעה הזו");

          setIsDriverMatched(true);
          if (asgId) setAssignmentIdLocal(asgId); // ✅ prefer fetching by assignment_id
          if (reqId) setResolvedRequestId(reqId);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "שגיאה בטעינת הנתונים");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    resolveIds();
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, [role, token, requestId, offerId, assignmentId]);

  /* -------- Fetch assignment (prefer by assignment_id) -------- */
  useEffect(() => {
    // For driver we must have confirmed match first
    if ((role as Role) === "driver" && !isDriverMatched) return;

    const hasAssignmentId =
      (typeof assignmentId === "string" && assignmentId.length > 0) ||
      (typeof assignmentIdLocal === "string" && assignmentIdLocal.length > 0);

    if (!hasAssignmentId && !resolvedRequestId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const MAX_WAIT_MS = 10_000;
    const INTERVAL_MS = 1_000;
    const t0 = Date.now();

    async function fetchIt() {
      setLoading(true);
      setError(null);
      try {
        let data: AssignmentDetailOut;

        const asgId = (assignmentIdLocal || assignmentId) as string | undefined;
        if (asgId) {
          // ✅ Source of truth: fetch by assignment_id
          data = await getAssignmentById(String(asgId));
        } else {
          // Fallback (sender/rider): fetch by request_id (only_active on server)
          data = await getAssignmentByRequest(String(resolvedRequestId));
        }

        if (cancelled) return;

        // Keep requestId in sync (server is canonical)
        if (data.request_id && data.request_id !== resolvedRequestId) {
          setResolvedRequestId(data.request_id);
        }

        setAssignment(data);
        const reqFromApi = (data as any).request as RequestLite | undefined;
        if (reqFromApi?.id) setRequestMeta(reqFromApi);
        setLoading(false);
      } catch (e: any) {
        const msg = e?.message || "";
        const is404 =
          msg.includes("No active assignment") ||
          msg.includes("Assignment not found") ||
          msg.includes("404");
        if (!is404 || Date.now() - t0 > MAX_WAIT_MS) {
          if (!cancelled) {
            setError(msg || "שגיאה בטעינת ההתאמה");
            setLoading(false);
          }
          return;
        }
        timer = setTimeout(() => !cancelled && fetchIt(), INTERVAL_MS);
      }
    }

    fetchIt();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [
    assignmentId,
    assignmentIdLocal,
    resolvedRequestId,
    role,
    isDriverMatched,
  ]);

  // -------- Refresh on focus (prefer by assignment_id) --------
  useFocusEffect(
    useCallback(() => {
      const asgId = (assignmentIdLocal || assignmentId) as string | undefined;
      const hasAssignmentId = !!asgId;
      if (!hasAssignmentId && !resolvedRequestId) return;
      if ((role as Role) === "driver" && !isDriverMatched) return;

      (hasAssignmentId
        ? getAssignmentById(String(asgId))
        : getAssignmentByRequest(String(resolvedRequestId))
      )
        .then((data) => {
          if (!data) return;
          if (data.request_id && data.request_id !== resolvedRequestId) {
            setResolvedRequestId(data.request_id);
          } else {
            setAssignment(data);
            if ((data as any).request?.id)
              setRequestMeta((data as any).request);
          }
        })
        .catch(() => {});
    }, [
      assignmentId,
      assignmentIdLocal,
      resolvedRequestId,
      role,
      isDriverMatched,
    ])
  );

  // ---- Payment helpers ----

  const isPayerRole = (role as Role) === "sender" || (role as Role) === "rider";

  const canInitiatePayment =
    !!assignment &&
    isPayerRole &&
    !!assignment.payment_status &&
    ["pending_deposit", "failed", "refunded", "cancelled"].includes(
      assignment.payment_status as string
    );

  const handlePay = async () => {
    if (!assignment) return;
    if (!token) {
      Alert.alert("שגיאה", "נדרשת התחברות כדי לבצע תשלום.");
      return;
    }
    if (!canInitiatePayment || paying) {
      return;
    }

    try {
      setPaying(true);
      // Call backend: create DB escrow + on-chain escrow entry
      const escrow = await initiateEscrow(
        String(token),
        assignment.assignment_id
      );

      // Update local payment_status from escrow.status
      setAssignment((prev) =>
        prev
          ? ({ ...prev, payment_status: escrow.status } as AssignmentDetailOut)
          : prev
      );

      // Navigate to dedicated payment info screen
      router.replace({
        pathname: "/payment_details",
        params: {
          token,
          assignmentId: assignment.assignment_id,
          escrowId: escrow.id,
        },
      });
    } catch (e: any) {
      const msg =
        e?.message || "שגיאה ביצירת פיקדון התשלום. נסה/י שוב בעוד מספר דקות.";
      Alert.alert("שגיאה", msg);
    } finally {
      setPaying(false);
    }
  };

  // ---- Rating the driver (customer, after completion) ----
  const canRateDriver =
    !!assignment &&
    isPayerRole &&
    assignment.status === "completed" &&
    assignment.driver_rating_score == null;

  const handleRate = async () => {
    if (!assignment || ratingValue < 1 || ratingSending) return;
    try {
      setRatingSending(true);
      await rateDriver(assignment.assignment_id, ratingValue);
      // Reload so the driver's trust score includes the new rating
      const fresh = await getAssignmentById(assignment.assignment_id);
      setAssignment(fresh);
    } catch (e: any) {
      Alert.alert("שגיאה", e?.message || "שליחת הדירוג נכשלה. נסה/י שוב.");
    } finally {
      setRatingSending(false);
    }
  };

  // -------- UI states --------
  if (loading) {
    return (
      <View style={S.centerWrap}>
        <ActivityIndicator />
        <Text style={S.sub}>טוען נתונים…</Text>
      </View>
    );
  }
  if (error) {
    return (
      <View style={S.centerWrap}>
        <Text style={S.err}>{error}</Text>
      </View>
    );
  }
  if (!assignment) return null;

  const d = assignment.driver;
  const req = (assignment as any).request as RequestLite | undefined;

  // Treat both "ride" and legacy "passenger" as ride
  const t = ((req?.type as string) || "").toLowerCase();
  const isRide = t === "ride" || t === "passenger";

  // Determine user role for text selection (default to "sender" for safety)
  const roleStr: Role = (role as Role) || "sender";

  // Role-aware headline text for driver vs sender/rider
  const kind = getKindLabel(roleStr, isRide);

  const heroImage = isRide ? rideImg : pkgImg;

  const callEnabled = !!d.phone;
  const onCall = () => d.phone && Linking.openURL(`tel:${d.phone}`);

  const assignedLocal = new Date(assignment.assigned_at).toLocaleString();
  const trustScore =
    typeof d.trust_score === "number"
      ? d.trust_score
      : typeof d.rating === "number"
        ? d.rating
        : null;
  const etaLabel =
    typeof assignment.predicted_minutes === "number"
      ? `כ-${Math.round(assignment.predicted_minutes)} דקות`
      : "—";

  // Lower hero image more for the car
  const heroOffset = isRide ? 56 : 16;

  // Price label from agreed_price_cents (if exists)
  const priceCents =
    typeof assignment.agreed_price_cents === "number"
      ? assignment.agreed_price_cents
      : null;
  const priceLabel =
    priceCents != null ? `${(priceCents / 100).toFixed(2)} ₪` : "—";
  const paymentStatusLabel = prettyPaymentStatus(assignment.payment_status);

  return (
    <View style={S.page}>
      {/* fixed top layer */}
      <View style={S.header}>
        <GreenDiagonalWave />
        <View style={[S.heroWrap, { transform: [{ translateY: heroOffset }] }]}>
          <Image source={heroImage} style={S.heroImg} resizeMode="contain" />
        </View>
      </View>

      {/* content scrolls over the fixed header (rating box can be below the fold) */}
      <ScrollView style={{ flex: 1 }} contentContainerStyle={S.details}>
        <Text style={S.kind}>{kind}</Text>

        {/* Route pill – LTR: FROM (left) → arrow-forward → TO (right) */}
        <RoutePillLTR from={req?.from_address} to={req?.to_address} />

        <View style={S.driverRow}>
          <Image
            source={{
              uri: d.avatar_url || "https://ui-avatars.com/api/?name=Driver",
            }}
            style={S.avatar}
          />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={S.name} numberOfLines={1}>
              {d.full_name || "נהג ללא שם"}
            </Text>
            <TrustStars
              score={trustScore}
              isNew={d.is_new_courier}
              numRatings={d.num_ratings}
            />
          </View>
          <TouchableOpacity
            onPress={onCall}
            disabled={!callEnabled}
            style={[
              S.iconBtn,
              S.iconBtnBrown,
              !callEnabled && { opacity: 0.4 },
            ]}
          >
            <Ionicons name="call" size={20} color="#fff" />
          </TouchableOpacity>
        </View>

        <TrustExplain d={d} />

        {!!req?.notes && (
          <View style={S.notesBox}>
            <Text style={S.notesTitle}>הערות</Text>
            <Text style={S.notesBody} numberOfLines={3}>
              {req?.notes}
            </Text>
          </View>
        )}

        <View style={S.infoRow}>
          <InfoItem label="סטטוס" value={prettyStatus(assignment.status)} />
          <InfoItem label="שעת שיוך" value={assignedLocal} />
        </View>

        <View style={S.infoRow}>
          <InfoItem label="מחיר שסוכם" value={priceLabel} />
          <InfoItem label="סטטוס תשלום" value={paymentStatusLabel} />
        </View>

        <View style={S.infoRow}>
          <InfoItem label="זמן משלוח משוער (חיזוי)" value={etaLabel} />
        </View>

        {isPayerRole && assignment.driver_rating_score != null && (
          <View style={S.rateBox}>
            <Text style={S.notesTitle}>הדירוג שלך לשליח</Text>
            <TrustStars score={assignment.driver_rating_score} />
          </View>
        )}

        {canRateDriver && (
          <View style={S.rateBox}>
            <Text style={S.notesTitle}>איך היה המשלוח? דרג/י את השליח</Text>
            <StarPicker
              value={ratingValue}
              onChange={setRatingValue}
              disabled={ratingSending}
            />
            <TouchableOpacity
              onPress={handleRate}
              disabled={ratingValue < 1 || ratingSending}
              style={[
                S.btn,
                S.btnBrown,
                { opacity: ratingValue < 1 || ratingSending ? 0.5 : 1 },
              ]}
            >
              <Text style={S.btnText}>
                {ratingSending ? "שולח…" : "שליחת דירוג"}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {canInitiatePayment && (
          <TouchableOpacity
            onPress={handlePay}
            disabled={paying}
            style={[
              S.btn,
              S.btnBrown, // ← brown like the phone icon button
              { marginTop: 16, opacity: paying ? 0.6 : 1 },
            ]}
          >
            <Text style={S.btnText}>
              {paying ? "מעדכן פיקדון…" : "להמשך תשלום"}
            </Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </View>
  );
}

/* ---------------- helpers & small components ---------------- */

// Role-aware headline text
function getKindLabel(role: Role, isRide: boolean): string {
  // Driver sees "you have a ride/package to do"
  if (role === "driver") {
    return isRide
      ? "יש לך טרמפ לעשות, איזה כיף!"
      : "יש לך חבילה לאסוף, איזה כיף!";
  }

  // Sender (package owner)
  if (role === "sender") {
    return isRide
      ? "איזה כיף, מצאנו לך נהג!"
      : "איזה כיף, מצאנו נהג שיקח את החבילה שלך!";
  }

  // Rider (passenger)
  return isRide
    ? "איזה כיף, מצאנו לך נהג שיסיע אותך!"
    : "איזה כיף, מצאנו לך נהג!";
}

function prettyStatus(s: string) {
  return s.replaceAll("_", " ");
}

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

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, gap: 4 }}>
      <Text style={S.infoLabel}>{label}</Text>
      <Text style={S.infoValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

/* ---- Route pill (LTR): FROM left → arrow-forward → TO right; no dots ---- */
function RoutePillLTR({
  from,
  to,
}: {
  from?: string | null;
  to?: string | null;
}) {
  if (!from && !to) return null;
  return (
    <View style={S.routePill}>
      <View style={[S.routeRow, { flexDirection: "row" }]}>
        <Text style={[S.routeText, { textAlign: "right" }]} numberOfLines={1}>
          {from || "—"}
        </Text>
        <Ionicons
          name="arrow-forward"
          size={18}
          color="#6b7280"
          style={{ marginHorizontal: 10, transform: [{ scaleX: -1 }] }}
        />
        <Text style={[S.routeText, { textAlign: "left" }]} numberOfLines={1}>
          {to || "—"}
        </Text>
      </View>
    </View>
  );
}

/* -------- Curved diagonal wave (fixed at top) -------- */
function GreenDiagonalWave() {
  const h = WAVE_H;
  const d = `
    M 0 0
    H ${SCREEN_W}
    V ${h * 0.36}
    C ${SCREEN_W * 0.78} ${h * 0.62}, ${SCREEN_W * 0.35} ${h * 0.8}, 0 ${h * 0.92}
    Z
  `;
  return (
    <Svg
      width={SCREEN_W}
      height={h}
      style={S.waveSvg}
      viewBox={`0 0 ${SCREEN_W} ${h}`}
    >
      <Path d={d} fill={GREEN} />
    </Svg>
  );
}

/* ---------------- Styles ---------------- */

const S = StyleSheet.create({
  page: { flex: 1, backgroundColor: BG },

  header: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: WAVE_H,
  },
  waveSvg: { position: "absolute", top: 0, left: 0 },

  heroWrap: {
    position: "absolute",
    bottom: 0,
    left: 16,
    right: 16,
    height: HERO_H,
    borderRadius: 28,
    overflow: "hidden",
    backgroundColor: "transparent",
    justifyContent: "flex-end",
  },
  heroImg: { width: "100%", height: HERO_H, backgroundColor: "transparent" },

  details: {
    marginTop: WAVE_H - 12,
    paddingHorizontal: 16,
    paddingBottom: 40,
    gap: 12,
    justifyContent: "flex-start",
  },

  centerWrap: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  sub: { fontSize: 14, opacity: 0.7 },
  err: { color: "#b91c1c", fontWeight: "700" },

  kind: { fontSize: 18, fontWeight: "800", color: TXT },

  routePill: {
    alignSelf: "center",
    width: "84%",
    backgroundColor: "#ffffff",
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
  routeRow: { alignItems: "center", justifyContent: "space-between" },
  routeText: { color: TXT, fontWeight: "700", maxWidth: "44%" },

  driverRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginTop: 8,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "#e5e7eb",
  },
  name: { fontSize: 18, fontWeight: "700", color: TXT },
  dimSmall: { color: "#6b7280", fontSize: 12 },

  rateBox: {
    marginTop: 12,
    padding: 12,
    borderRadius: 14,
    backgroundColor: "#fff",
    gap: 10,
    alignItems: "center",
  },
  notesBox: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: "#e5e7eb",
  },
  notesTitle: { fontWeight: "800", marginBottom: 6, color: TXT },
  notesBody: { color: "#374151", lineHeight: 20 },

  infoRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 16,
    marginTop: 2,
  },
  infoLabel: { color: "#6b7280", fontSize: 12 },
  infoValue: { color: TXT, fontWeight: "600" },

  btn: {
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
    alignSelf: "center",
  },
  btnText: { color: "#fff", fontWeight: "800" },
  btnBrown: { backgroundColor: BROWN },

  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  iconBtnBrown: { backgroundColor: BROWN },
});
