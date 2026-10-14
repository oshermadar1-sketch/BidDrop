// app/request_details.tsx
// Task details screen: shows full assignment info.
// Driver can update assignment status; sender confirms package received; rider confirms arrival.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Modal,
  Pressable,
  ScrollView,
} from "react-native";
import { useLocalSearchParams, Stack } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import {
  getAssignmentById,
  getAssignmentByRequest,
  updateAssignmentStatus,
  confirmAssignmentDelivered, // (no longer used but kept for now – safe to remove if you want)
  confirmEscrowDelivered,
  type AssignmentDetailOut,
  type AssignmentStatus,
} from "../lib/api";
import { COLORS } from "./ui/theme";
import { TrustStars } from "../components/TrustStars";

type ModeKey = "driver" | "rider" | "sender";

type Params = {
  assignment_id?: string;
  request_id?: string;
  token?: string;
  mode?: ModeKey;
};

/* ---------- Helpers for date/time + labels (similar to bucket_list) ---------- */

const LRM = "\u200E";
const ltr = (seg: string) => `${LRM}${seg}${LRM}`;
const fmt2 = (n: number) => String(n).padStart(2, "0");

function fmtDate(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${fmt2(d.getDate())}.${fmt2(d.getMonth() + 1)}.${d.getFullYear()}`;
}

function fmtTime(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${fmt2(d.getHours())}:${fmt2(d.getMinutes())}`;
}

// Range text only (without "חלון")
function windowRangeText(s?: string | null, e?: string | null) {
  if (s && e) {
    const same = fmtDate(s) === fmtDate(e);
    const startSeg = `${fmtDate(s)} ${fmtTime(s)}`;
    const endSeg = `${fmtDate(e)} ${fmtTime(e)}`;
    return same
      ? `${ltr(startSeg)}${ltr("–")}${ltr(fmtTime(e))}`
      : `${ltr(startSeg)} ${ltr("→")} ${ltr(endSeg)}`;
  }
  if (s) return ltr(`${fmtDate(s)} ${fmtTime(s)}`);
  if (e) return ltr(`${fmtDate(e)} ${fmtTime(e)}`);
  return "—";
}

function statusHebrew(status: string): string {
  switch (status) {
    case "created":
      return "נוצרה";
    case "picked_up":
      return "נאסף";
    case "in_transit":
      return "בדרך";
    case "completed":
      return "הושלם";
    case "cancelled":
      return "בוטל";
    case "failed":
      return "נכשל";
    default:
      return status;
  }
}

function paymentStatusHebrew(status?: string | null): string {
  if (!status) return "—";
  switch (status) {
    case "pending_deposit":
      return "ממתין לתשלום";
    case "deposited":
      return "שולם (מופקד)";
    case "released":
      return "שוחרר";
    case "refunded":
      return "הוחזר";
    case "failed":
      return "תשלום נכשל";
    case "cancelled":
      return "בוטל";
    default:
      return status;
  }
}

// Allowed status transitions (must mirror backend routes_assignments.py)
const ALLOWED_STATUS_TRANSITIONS: Record<AssignmentStatus, AssignmentStatus[]> =
  {
    created: ["picked_up", "cancelled", "failed"],
    picked_up: ["in_transit", "cancelled", "failed"],
    in_transit: ["completed", "cancelled", "failed"],
    completed: [],
    cancelled: [],
    failed: [],
  };

function allowedNext(status: AssignmentStatus): AssignmentStatus[] {
  return ALLOWED_STATUS_TRANSITIONS[status] ?? [];
}

const STATUS_LABELS: Record<AssignmentStatus, string> = {
  created: "נוצרה",
  picked_up: "נאסף",
  in_transit: "בדרך",
  completed: "הושלם",
  cancelled: "בוטל",
  failed: "נכשל",
};

/* ---------------------------- Main screen ---------------------------- */

export default function RequestDetailsScreen() {
  const { assignment_id, request_id, token, mode } =
    useLocalSearchParams<Params>();

  const [data, setData] = useState<AssignmentDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [sheetVisible, setSheetVisible] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const [confirmingDelivered, setConfirmingDelivered] = useState(false);

  const isDriverView: boolean = mode === "driver";
  const isSenderView: boolean = mode === "sender";
  const isRiderView: boolean = mode === "rider";
  const isCustomerView: boolean = isSenderView || isRiderView;

  // Only driver can update assignment status
  const canUpdateStatus =
    !!token && (!!assignment_id || !!request_id) && isDriverView;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);

    try {
      // 1) Try by assignment_id if we have it
      if (assignment_id) {
        try {
          const res = await getAssignmentById(String(assignment_id));
          setData(res);
          return;
        } catch (e: any) {
          const msg = e?.message || "";
          const is404 =
            msg.includes("Assignment not found") ||
            msg.includes("404") ||
            msg.includes("Not Found");
          // If not 404 or we don't have request_id, rethrow
          if (!is404 || !request_id) {
            throw e;
          }
          // else: fall through to try by request_id
        }
      }

      // 2) Try by request_id
      if (request_id) {
        const res = await getAssignmentByRequest(String(request_id));
        setData(res);
        return;
      }

      // 3) No IDs at all
      setErr("חסר מזהה משימה או מזהה בקשה");
    } catch (e: any) {
      setErr(e?.message || "שגיאה בטעינת הנתונים");
    } finally {
      setLoading(false);
    }
  }, [assignment_id, request_id]);

  useEffect(() => {
    load();
  }, [load]);

  const winText = useMemo(() => {
    if (!data) return "—";
    return windowRangeText(data.request.window_start, data.request.window_end);
  }, [data]);

  const priceText = useMemo(() => {
    // treat missing/null agreed_price_cents as unknown; allow 0
    if (data == null || data.agreed_price_cents == null) return "—";
    const nis = data.agreed_price_cents / 100;
    if (Number.isNaN(nis)) return "—";
    return `₪${nis.toFixed(2)}`;
  }, [data]);

  const currentStatus = (data?.status || "created") as AssignmentStatus;
  const nextOptions: AssignmentStatus[] = useMemo(
    () => allowedNext(currentStatus),
    [currentStatus]
  );

  const onUpdateStatusPress = () => {
    if (!canUpdateStatus || !nextOptions.length) return;
    setSheetVisible(true);
  };

  const handleStatusChange = async (newStatus: AssignmentStatus) => {
    if (!token) return;

    // If we don't know assignment_id yet, we can't patch – just ignore
    const aid = assignment_id ?? data?.assignment_id;
    if (!aid) return;

    try {
      setSavingStatus(true);
      let updated;

if (newStatus === "completed") {
  const res = await fetch(
    `http://127.0.0.1:8000/match/assignments/${aid}/complete`,
    {
      method: "POST",
    }
  );

  if (!res.ok) {
    throw new Error("Failed to complete assignment");
  }

  updated = await getAssignmentById(String(aid));
} else {
  updated = await updateAssignmentStatus(
    String(token),
    String(aid),
    newStatus
  );
}
      setData(updated);
      setSheetVisible(false);
    } catch (e: any) {
      setErr(e?.message || "שגיאה בעדכון הסטטוס");
    } finally {
      setSavingStatus(false);
    }
  };

  // Customer (sender/rider) confirmation.
  const hasAnyId = !!assignment_id || !!request_id || !!data?.assignment_id;

  const canConfirmDelivered =
    !!token &&
    hasAnyId &&
    isCustomerView &&
    data?.status === "completed" &&
    (data?.payment_status === null ||
      data?.payment_status === undefined ||
      data?.payment_status === "pending_deposit" ||
      data?.payment_status === "deposited");

  const handleConfirmDelivered = async () => {
    if (!token || !data) return;
    const aid = data.assignment_id ?? assignment_id;
    if (!aid) return;

    try {
      setConfirmingDelivered(true);

      await confirmEscrowDelivered(String(token), String(aid));

      const refreshed = await getAssignmentById(String(aid));
      setData(refreshed);
    } catch (e: any) {
      setErr(
        e?.message ||
          (isSenderView ? "שגיאה באישור קבלת החבילה" : "שגיאה באישור הגעה ליעד")
      );
    } finally {
      setConfirmingDelivered(false);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <Stack.Screen
        options={{
          headerTitle: "פרטי בקשה",
          headerTintColor: "#000",
          headerTitleAlign: "center",
        }}
      />
      <LinearGradient
        colors={[COLORS.green1, COLORS.green2, COLORS.green3, COLORS.green4]}
        start={{ x: 1, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={S.gradient}
      >
        {loading ? (
          <View style={S.centerBox}>
            <ActivityIndicator color={COLORS.primaryDark} />
            <Text style={S.centerTxt}>טוען פרטי בקשה…</Text>
          </View>
        ) : err ? (
          <View style={S.centerBox}>
            <Text style={S.errorTxt}>{err}</Text>
            <TouchableOpacity style={S.retryBtn} onPress={load}>
              <Text style={S.retryTxt}>לנסות שוב</Text>
            </TouchableOpacity>
          </View>
        ) : !data ? (
          <View style={S.centerBox}>
            <Text style={S.errorTxt}>לא נמצאו נתונים לבקשה</Text>
          </View>
        ) : (
          <ScrollView contentContainerStyle={S.scrollContent}>
            {/* Page title */}
            <Text style={S.pageTitle}>פרטי בקשה</Text>

            {/* Hero card: route + quick status */}
            <View style={[S.card, S.heroCard]}>
              <View style={S.heroTopRow}>
                <View style={S.iconCircle}>
                  <Ionicons
                    name={
                      data.request.type === "package"
                        ? "cube-outline"
                        : "car-outline"
                    }
                    size={22}
                    color="#fff"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={S.title}>
                    {data.request.to_address || "יעד לא ידוע"} {ltr("←")}{" "}
                    {data.request.from_address || "מוצא לא ידוע"}
                  </Text>
                  <Text style={S.heroSub}>{winText}</Text>
                </View>
              </View>

              <View style={S.row}>
                <View style={S.rightRow}>
                  <View style={S.chip}>
                    <Text style={S.chipTxt}>
                      {statusHebrew(data.status || "")}
                    </Text>
                  </View>
                  <View style={S.chipSoft}>
                    <Text style={S.chipSoftTxt}>
                      {data.request.type === "package" ? "משלוח" : "טרמפ"}
                    </Text>
                  </View>
                </View>
                <Text style={S.meta}>
                  {paymentStatusHebrew(data.payment_status)}
                </Text>
              </View>

              {/* Type + price */}
              <DetailLine
                label="סוג"
                value={
                  data.request.type === "package"
                    ? "חבילה"
                    : data.request.type === "ride"
                      ? "טרמפ"
                      : "נוסע"
                }
              />
              <DetailLine label="מחיר מוסכם" value={priceText} />

              {/* People */}
              {data.request.pickup_contact_name ? (
                <DetailLine
                  label="איש קשר"
                  value={String(data.request.pickup_contact_name)}
                />
              ) : null}
              {data.request.pickup_contact_phone ? (
                <DetailLine
                  label="טלפון"
                  value={String(data.request.pickup_contact_phone)}
                />
              ) : null}

              {data.requester?.full_name ? (
                <DetailLine
                  label="לקוח"
                  value={String(data.requester.full_name)}
                />
              ) : null}

              {data.driver?.full_name ? (
                <DetailLine
                  label="שליח"
                  value={String(data.driver.full_name)}
                />
              ) : null}

              {data.driver ? (
                <View style={S.line}>
                  <Text style={S.lineLabel}>דירוג שליח</Text>
                  <TrustStars
                    score={data.driver.trust_score ?? data.driver.rating}
                    isNew={data.driver.is_new_courier}
                    numRatings={data.driver.num_ratings}
                    size={16}
                  />
                </View>
              ) : null}

              {typeof data.predicted_minutes === "number" ? (
                <DetailLine
                  label="זמן משלוח משוער"
                  value={`כ-${Math.round(data.predicted_minutes)} דקות`}
                />
              ) : null}

              {/* Notes */}
              {data.request.notes ? (
                <DetailLine
                  label="הערות"
                  value={String(data.request.notes)}
                  multi
                />
              ) : null}
            </View>

            {/* Timeline card */}
            <View style={S.card}>
              <Text style={S.cardTitle}>ציר זמן</Text>
              <DetailLine
                label="הוקצה"
                value={
                  data.assigned_at
                    ? `${fmtDate(data.assigned_at)} ${fmtTime(
                        data.assigned_at
                      )}`
                    : "—"
                }
              />
              <DetailLine
                label="נאסף"
                value={
                  data.picked_up_at
                    ? `${fmtDate(data.picked_up_at)} ${fmtTime(
                        data.picked_up_at
                      )}`
                    : "—"
                }
              />
              <DetailLine
                label="יצא לדרך"
                value={
                  data.in_transit_at
                    ? `${fmtDate(data.in_transit_at)} ${fmtTime(
                        data.in_transit_at
                      )}`
                    : "—"
                }
              />
              <DetailLine
                label="הושלם"
                value={
                  data.completed_at
                    ? `${fmtDate(data.completed_at)} ${fmtTime(
                        data.completed_at
                      )}`
                    : "—"
                }
              />
              <DetailLine
                label="בוטל"
                value={
                  data.cancelled_at
                    ? `${fmtDate(data.cancelled_at)} ${fmtTime(
                        data.cancelled_at
                      )}`
                    : "—"
                }
              />
              <DetailLine
                label="נכשל"
                value={
                  data.failed_at
                    ? `${fmtDate(data.failed_at)} ${fmtTime(data.failed_at)}`
                    : "—"
                }
              />
            </View>

            {/* Location debug (optional) */}
            {data.last_location ? (
              <View style={S.card}>
                <Text style={S.cardTitle}>מיקום אחרון (דיבאג)</Text>
                <DetailLine
                  label="קו רוחב"
                  value={String(data.last_location.lat)}
                />
                <DetailLine
                  label="קו אורך"
                  value={String(data.last_location.lng)}
                />
                <DetailLine
                  label="עודכן ב־"
                  value={`${fmtDate(data.last_location.updated_at)} ${fmtTime(
                    data.last_location.updated_at
                  )}`}
                />
              </View>
            ) : null}

            <View style={S.footerSpace} />
          </ScrollView>
        )}

        {/* Bottom bar: Update status for driver */}
        {data && canUpdateStatus && nextOptions.length > 0 && (
          <View style={S.bottomBarWrap}>
            <TouchableOpacity
              style={S.statusBtn}
              onPress={onUpdateStatusPress}
              disabled={savingStatus}
              activeOpacity={0.9}
            >
              <Text style={S.statusBtnTxt}>
                {savingStatus ? "מעדכן סטטוס…" : "עדכון סטטוס"}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Bottom bar: Customer confirmation (sender/rider) */}
        {data && isCustomerView && canConfirmDelivered && (
          <View style={S.bottomBarWrap}>
            <TouchableOpacity
              style={S.statusBtn}
              onPress={handleConfirmDelivered}
              disabled={confirmingDelivered}
              activeOpacity={0.9}
            >
              <Text style={S.statusBtnTxt}>
                {confirmingDelivered
                  ? isSenderView
                    ? "מאשר/ת קבלה…"
                    : "מאשר/ת הגעה…"
                  : isSenderView
                    ? "מאשר/ת שקיבלתי את החבילה"
                    : "מאשר/ת שהגעתי ליעד"}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Bottom sheet for status selection (driver only) */}
        <Modal
          transparent
          visible={sheetVisible}
          animationType="slide"
          onRequestClose={() => !savingStatus && setSheetVisible(false)}
        >
          <Pressable
            style={S.sheetBackdrop}
            onPress={() => !savingStatus && setSheetVisible(false)}
          >
            <View style={S.sheetContainer}>
              <Text style={S.sheetTitle}>בחירת סטטוס</Text>
              <Text style={S.sheetSubtitle}>
                בחרי את הסטטוס הבא למשימה לפי ההתקדמות בפועל
              </Text>

              {nextOptions.map((st) => (
                <TouchableOpacity
                  key={st}
                  style={S.sheetOption}
                  disabled={savingStatus}
                  onPress={() => handleStatusChange(st)}
                  activeOpacity={0.8}
                >
                  <Text style={S.sheetOptionTxt}>{STATUS_LABELS[st]}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity
                style={S.sheetCancel}
                disabled={savingStatus}
                onPress={() => setSheetVisible(false)}
                activeOpacity={0.8}
              >
                <Text style={S.sheetCancelTxt}>ביטול</Text>
              </TouchableOpacity>
            </View>
          </Pressable>
        </Modal>
      </LinearGradient>
    </View>
  );
}

/* ------------------------ Small UI pieces ------------------------ */

function DetailLine({
  label,
  value,
  multi = false,
}: {
  label: string;
  value: string;
  multi?: boolean;
}) {
  return (
    <View style={S.line}>
      <Text style={S.lineLabel}>{label}</Text>
      <Text
        style={[S.lineValue, multi ? { flexWrap: "wrap" } : null]}
        numberOfLines={multi ? undefined : 1}
      >
        {value || "—"}
      </Text>
    </View>
  );
}

/* ------------------------------ Styles ------------------------------ */

const S = StyleSheet.create({
  gradient: {
    flex: 1,
    paddingHorizontal: 16,
    paddingTop: 70,
    paddingBottom: 24,
  },
  scrollContent: {
    paddingTop: 12,
    paddingBottom: 96,
    gap: 12,
  },
  pageTitle: {
    fontSize: 22,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "center",
    marginTop: -10,
    marginBottom: 10,
  },
  centerBox: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
  },
  centerTxt: {
    color: COLORS.primaryDark,
    fontWeight: "700",
  },
  errorTxt: {
    color: "#b00020",
    fontWeight: "800",
    textAlign: "center",
    paddingHorizontal: 16,
  },
  retryBtn: {
    marginTop: 10,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: COLORS.primary,
  },
  retryTxt: {
    color: "#fff",
    fontWeight: "800",
  },

  card: {
    backgroundColor: COLORS.softMocha,
    borderRadius: 16,
    padding: 14,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },

  // Hero card tweaks
  heroCard: {
    borderRadius: 22,
    paddingTop: 16,
    paddingBottom: 18,
  },
  heroTopRow: {
    flexDirection: "row-reverse",
    alignItems: "center",
    gap: 12,
    marginBottom: 10,
  },
  iconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  heroSub: {
    fontSize: 13,
    color: COLORS.dim,
    fontWeight: "700",
    textAlign: "left",
  },

  title: {
    fontWeight: "900",
    color: COLORS.text,
    fontSize: 18,
    marginBottom: 2,
    textAlign: "left",
  },
  cardTitle: {
    fontWeight: "900",
    color: COLORS.text,
    fontSize: 16,
    marginBottom: 6,
    textAlign: "left",
  },
  row: {
    flexDirection: "row-reverse",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 8,
    marginBottom: 10,
  },
  rightRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    alignSelf: "flex-start",
  },
  chip: {
    backgroundColor: COLORS.primary,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
    alignSelf: "flex-start",
  },
  chipTxt: {
    color: "#fff",
    fontWeight: "900",
    fontSize: 12,
  },
  chipSoft: {
    backgroundColor: "rgba(0,0,0,0.05)",
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
  },
  chipSoftTxt: {
    color: COLORS.text,
    fontWeight: "800",
    fontSize: 12,
  },
  windowLabel: {
    color: COLORS.dim,
    fontWeight: "900",
  },
  meta: {
    flex: 1,
    minWidth: 0,
    textAlign: "left",
    color: COLORS.text,
    fontWeight: "700",
    lineHeight: 18,
  },

  line: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 4,
    gap: 8,
  },
  lineLabel: {
    color: COLORS.dim,
    fontWeight: "800",
    width: 110,
    textAlign: "left",
  },
  lineValue: {
    color: COLORS.text,
    fontWeight: "800",
    flex: 1,
    textAlign: "left",
    minWidth: 0,
  },

  footerSpace: {
    height: 40,
  },

  bottomBarWrap: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 18,
  },
  statusBtn: {
    height: 54,
    borderRadius: 28,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  statusBtnTxt: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "900",
  },

  sheetBackdrop: {
    flex: 1,
    justifyContent: "flex-end",
    backgroundColor: "rgba(0,0,0,0.3)",
  },
  sheetContainer: {
    backgroundColor: "#fff",
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 24,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    gap: 8,
  },
  sheetTitle: {
    textAlign: "center",
    fontWeight: "900",
    fontSize: 16,
    marginBottom: 2,
  },
  sheetSubtitle: {
    textAlign: "center",
    color: COLORS.dim,
    marginBottom: 10,
  },
  sheetOption: {
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.04)",
    marginVertical: 3,
    alignItems: "center",
  },
  sheetOptionTxt: {
    fontWeight: "800",
    color: COLORS.text,
  },
  sheetCancel: {
    marginTop: 10,
    paddingVertical: 10,
    alignItems: "center",
    borderRadius: 999,
    backgroundColor: "rgba(0,0,0,0.06)",
  },
  sheetCancelTxt: {
    fontWeight: "800",
    color: COLORS.dim,
  },
});
