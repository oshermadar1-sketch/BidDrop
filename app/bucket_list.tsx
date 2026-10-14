// app/bucket_list.tsx
// Bucket list screen (Sender / Rider / Courier)

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  FlatList,
  RefreshControl,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import {
  listSenderRequests,
  listRiderRequests,
  listCourierJobs,
  listMyCourierOffers,
  type RequestRow,
  type RiderRequestRow,
  type CourierJobRow,
  type CourierOfferRow,
} from "../lib/api";
import { COLORS } from "./ui/theme";

type RoleKey = "sender" | "rider" | "courier";
type SenderBucket = "open" | "active" | "delivered";
type RiderBucket = "open" | "active" | "completed";
type CourierBucket = "available" | "active" | "delivered";

type Params = {
  token?: string;
  role?: RoleKey;
  bucket?: string;
  title?: string;
};

/* ---------------- helpers: pick + date/time + RTL-safe text ---------------- */

// Force LTR segments inside RTL (dates, times, arrows)
const LRM = "\u200E";
const ltr = (seg: string) => `${LRM}${seg}${LRM}`;
const arrow = (from: string, to: string) => {
  const fromSafe = from || "";
  const toSafe = to || "";
  return `${ltr(toSafe)} ${ltr("←")} ${ltr(fromSafe)}`;
};

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

// Range text only (without the word "חלון")
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

// Safe pick from multiple possible keys; supports deep paths with dots
function pickAny(obj: any, keys: string[]): any {
  for (const k of keys) {
    const parts = k.split(".");
    let cur: any = obj;
    let ok = true;
    for (const p of parts) {
      if (cur && typeof cur === "object" && p in cur) cur = cur[p];
      else {
        ok = false;
        break;
      }
    }
    if (ok && cur != null) return cur;
  }
  return null;
}

// Status labels (Hebrew)
function statusLabelSender(s: RequestRow["status"]) {
  return s === "open"
    ? "פתוחה"
    : s === "assigned"
      ? "שובץ שליח"
      : s === "in_transit"
        ? "בדרך"
        : s === "completed"
          ? "הושלם"
          : "בוטל";
}
function statusLabelRider(s: RiderRequestRow["status"]) {
  return s === "open"
    ? "פתוחה"
    : s === "assigned"
      ? "שובץ נהג"
      : s === "in_transit"
        ? "בדרך"
        : s === "completed"
          ? "הושלם"
          : "בוטל";
}
function statusLabelCourier(s: CourierJobRow["status"]) {
  return s === "open"
    ? "פתוח"
    : s === "assigned"
      ? "שובצת"
      : s === "in_transit"
        ? "בדרך"
        : s === "completed"
          ? "הושלם"
          : "בוטל";
}

/* ---------------- main screen ---------------- */

export default function BucketListScreen() {
  const { token, role, bucket, title } = useLocalSearchParams<Params>();
  const router = useRouter();
  const roleKey = (role as RoleKey) ?? "sender";
  const bucketKey = (bucket as string) ?? "open";

  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const screenTitle = useMemo(() => {
    if (title) return title;
    if (roleKey === "sender") {
      return bucketKey === "open"
        ? "בקשות פתוחות"
        : bucketKey === "active"
          ? "בקשות בפעילות"
          : "בקשות שהושלמו";
    }
    if (roleKey === "rider") {
      return bucketKey === "open"
        ? "בקשות פתוחות"
        : bucketKey === "active"
          ? "בקשות פעילות"
          : "בקשות שהושלמו";
    }
    return bucketKey === "available"
      ? "זמינויות"
      : bucketKey === "active"
        ? "משימות פעילות"
        : "משימות שהושלמו";
  }, [roleKey, bucketKey, title]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      if (roleKey === "sender") {
        const rows = await listSenderRequests(
          String(token),
          bucketKey as SenderBucket
        );
        // Filter out ride-type rows; sender bucket is only for packages
        setItems((rows ?? []).filter((r: any) => r?.type !== "ride"));
        return;
      }
      if (roleKey === "rider") {
        const rows = await listRiderRequests(
          String(token),
          (bucketKey as RiderBucket) === "completed"
            ? "completed"
            : (bucketKey as RiderBucket)
        );
        setItems(rows ?? []);
        return;
      }
      if (bucketKey === "available") {
        const rows = await listMyCourierOffers(String(token), {
          status: "active",
          limit: 200,
          offset: 0,
        });
        setItems(rows ?? []);
      } else {
        const rows = await listCourierJobs(
          String(token),
          bucketKey as CourierBucket
        );
        setItems(rows ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, [token, roleKey, bucketKey]);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const renderItem = useCallback(
    ({ item }: { item: any }) => {
      // Courier view
      if (roleKey === "courier") {
        if (bucketKey === "available") {
          return <OfferCard it={item as CourierOfferRow} />;
        }

        // Courier ACTIVE/DELIVERED jobs are tappable → go to request_details as driver
        const job = item as CourierJobRow;
        const assignmentId = (job as any).assignment_id ?? job.id;
        const requestId = (job as any).request_id ?? job.id;

        const onPress = () => {
          if (!assignmentId && !requestId) return;
          router.push({
            pathname: "/request_details",
            params: {
              assignment_id: assignmentId ? String(assignmentId) : undefined,
              request_id: requestId ? String(requestId) : undefined,
              token: token ? String(token) : undefined,
              mode: "driver",
            },
          });
        };

        return <CourierJobCard it={job} onPress={onPress} />;
      }

      // Rider view – active/completed are tappable for details/confirm
      if (roleKey === "rider") {
        const it = item as RiderRequestRow;
        const isTappable = bucketKey === "active" || bucketKey === "completed";

        if (!isTappable) {
          return <RiderCard it={it} />;
        }

        const onPress = () => {
          router.push({
            pathname: "/request_details",
            params: {
              request_id: String(it.id),
              token: token ? String(token) : undefined,
              mode: "rider",
            },
          });
        };

        return (
          <TouchableOpacity
            onPress={onPress}
            activeOpacity={0.9}
            style={{ flex: 1 }}
          >
            <RiderCard it={it} />
          </TouchableOpacity>
        );
      }

      // Sender view – active/delivered are tappable for details/confirm
      const it = item as RequestRow;
      const isTappable = bucketKey === "active" || bucketKey === "delivered";

      if (!isTappable) {
        return <SenderCard it={it} />;
      }

      const onPress = () => {
        router.push({
          pathname: "/request_details",
          params: {
            request_id: String(it.id),
            token: token ? String(token) : undefined,
            mode: "sender",
          },
        });
      };

      return (
        <TouchableOpacity
          onPress={onPress}
          activeOpacity={0.9}
          style={{ flex: 1 }}
        >
          <SenderCard it={it} />
        </TouchableOpacity>
      );
    },
    [roleKey, bucketKey, router, token]
  );

  return (
    <LinearGradient
      colors={[COLORS.green1, COLORS.green2, COLORS.green3, COLORS.green4]}
      start={{ x: 1, y: 0 }}
      end={{ x: 0, y: 1 }}
      style={{ flex: 1 }}
    >
      <SafeAreaView style={S.safe}>
        <Text style={S.header}>{screenTitle}</Text>

        {loading && items.length === 0 ? (
          <View style={S.loadingBox}>
            <ActivityIndicator color={COLORS.primaryDark} />
            <Text style={S.loadingTxt}>טוען…</Text>
          </View>
        ) : null}

        <FlatList
          data={items}
          keyExtractor={(it: any) => String(it.id)}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
          renderItem={renderItem}
          ListEmptyComponent={
            !loading ? <Text style={S.empty}>אין פריטים להצגה</Text> : null
          }
          contentContainerStyle={{ paddingBottom: 24 }}
        />
      </SafeAreaView>
    </LinearGradient>
  );
}

/* ---------------- cards per role ---------------- */

function SenderCard({ it }: { it: RequestRow }) {
  const status = statusLabelSender(it.status);
  const win = windowRangeText(it.window_start, it.window_end);

  const driverName =
    pickAny(it, [
      "driver_name",
      "driver_full_name",
      "courier_name",
      "courier_full_name",
    ]) ?? pickAny(it, ["assignment.driver.full_name"]);
  const senderName = pickAny(it, ["sender_name", "requester_name"]);
  const riderName = pickAny(it, ["rider_name"]);

  // Price logic:
  // 1) Prefer agreed_price_cents (DB+chain agreed price, in cents)
  // 2) Fallback to agreed_price / price / max_price / min_price (in NIS)
  const agreedCents = pickAny(it, ["agreed_price_cents"]);
  let priceValue: number | null = null;

  if (agreedCents != null) {
    priceValue = Number(agreedCents) / 100;
  } else {
    const fallback = pickAny(it, [
      "agreed_price",
      "price",
      "max_price",
      "min_price",
    ]);
    priceValue = fallback != null ? Number(fallback) : null;
  }

  const priceText =
    priceValue != null && !Number.isNaN(priceValue)
      ? `₪${priceValue.toFixed(2)}`
      : "—";

  return (
    <View style={S.wrap}>
      <View style={S.card}>
        <Text style={S.title}>{arrow(it.from_address, it.to_address)}</Text>

        <View style={S.row}>
          <View style={S.rightRow}>
            <View style={S.chip}>
              <Text style={S.chipTxt}>{status}</Text>
            </View>
          </View>
          <Text style={S.meta}>{win}</Text>
        </View>

        <Line label="סוג" value={it.type === "package" ? "חבילה" : "טרמפ"} />
        <Line label="מחיר" value={priceText} />
        {driverName ? <Line label="שליח" value={String(driverName)} /> : null}
        {senderName ? <Line label="שולח" value={String(senderName)} /> : null}
        {riderName ? <Line label="נוסע" value={String(riderName)} /> : null}
        {it?.notes ? (
          <Line label="הערות" value={String(it.notes)} multi />
        ) : null}
      </View>
    </View>
  );
}

function RiderCard({ it }: { it: RiderRequestRow }) {
  const status = statusLabelRider(it.status);
  const win = windowRangeText(it.window_start, it.window_end);

  // Price logic identical to SenderCard
  const agreedCents = pickAny(it, ["agreed_price_cents"]);
  let priceValue: number | null = null;

  if (agreedCents != null) {
    priceValue = Number(agreedCents) / 100;
  } else {
    const fallback = pickAny(it, [
      "agreed_price",
      "price",
      "max_price",
      "min_price",
    ]);
    priceValue = fallback != null ? Number(fallback) : null;
  }

  const priceText =
    priceValue != null && !Number.isNaN(priceValue)
      ? `₪${priceValue.toFixed(2)}`
      : "—";

  const driverName = pickAny(it, [
    "driver_name",
    "driver_full_name",
    "assignment.driver.full_name",
  ]);
  const riderName = pickAny(it, ["rider_name"]);

  return (
    <View style={S.wrap}>
      <View style={S.card}>
        <Text style={S.title}>{arrow(it.from_address, it.to_address)}</Text>

        <View style={S.row}>
          <View style={S.rightRow}>
            <View style={S.chip}>
              <Text style={S.chipTxt}>{status}</Text>
            </View>
          </View>
          <Text style={S.meta}>{win}</Text>
        </View>

        <Line label="סוג" value="טרמפ" />
        <Line
          label="נוסעים"
          value={it?.passengers != null ? String(it.passengers) : "—"}
        />
        <Line label="מחיר" value={priceText} />
        {driverName ? <Line label="נהג" value={String(driverName)} /> : null}
        {riderName ? <Line label="נוסע" value={String(riderName)} /> : null}
        {it?.notes ? (
          <Line label="הערות" value={String(it.notes)} multi />
        ) : null}
      </View>
    </View>
  );
}

function CourierJobCard({
  it,
  onPress,
}: {
  it: CourierJobRow;
  onPress: () => void;
}) {
  const status = statusLabelCourier(it.status);
  const win = windowRangeText(it.window_start, it.window_end);

  // Price logic identical: prefer agreed_price_cents, fallback to other fields
  const agreedCents = pickAny(it, ["agreed_price_cents"]);
  let priceValue: number | null = null;

  if (agreedCents != null) {
    priceValue = Number(agreedCents) / 100;
  } else {
    const fallback = pickAny(it, [
      "agreed_price",
      "price",
      "suggested_pay",
      "min_price",
      "max_price",
    ]);
    priceValue = fallback != null ? Number(fallback) : null;
  }

  const priceText =
    priceValue != null && !Number.isNaN(priceValue)
      ? `₪${priceValue.toFixed(2)}`
      : "—";

  const driverName = pickAny(it, [
    "courier_name",
    "driver_name",
    "driver_full_name",
    "assignment.driver.full_name",
  ]);
  const customerName = pickAny(it, [
    "customer_name",
    "sender_name",
    "rider_name",
  ]);

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.9} style={S.wrap}>
      <View style={S.card}>
        <Text style={S.title}>{arrow(it.from_address, it.to_address)}</Text>

        <View style={S.row}>
          <View style={S.rightRow}>
            <View style={S.chip}>
              <Text style={S.chipTxt}>{status}</Text>
            </View>
          </View>
          <Text style={S.meta}>{win}</Text>
        </View>

        <Line label="סוג" value={it.type === "package" ? "חבילה" : "טרמפ"} />
        <Line label="מחיר" value={priceText} />
        {driverName ? <Line label="שליח" value={String(driverName)} /> : null}
        {customerName ? (
          <Line label="לקוח" value={String(customerName)} />
        ) : null}
        {it?.notes ? (
          <Line label="הערות" value={String(it.notes)} multi />
        ) : null}
      </View>
    </TouchableOpacity>
  );
}

function OfferCard({ it }: { it: CourierOfferRow }) {
  const range = windowRangeText(it.window_start, it.window_end);
  const types =
    Array.isArray(it.types) && it.types.length
      ? it.types
          .map((t) => (t === "package" ? "חבילות" : "טרמפיסטים"))
          .join(", ")
      : "—";
  const dst = it.to_address || "כל יעד";
  const min = pickAny(it, ["min_price"]);

  return (
    <View style={S.wrap}>
      <View style={S.card}>
        <Text style={S.title}>{arrow(it.from_address, dst)}</Text>

        <View style={S.row}>
          <View style={S.rightRow}>
            <View style={S.chip}>
              <Text style={S.chipTxt}>זמינות פעילה</Text>
            </View>
          </View>
          <Text style={S.meta}>{range}</Text>
        </View>

        <Line label="סוגים" value={types} />
        <Line label="מחיר מינימלי" value={min != null ? `₪${min}` : "—"} />
        {it?.notes ? (
          <Line label="הערות" value={String(it.notes)} multi />
        ) : null}
      </View>
    </View>
  );
}

/* ---------------- small UI parts ---------------- */

function Line({
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
        {value}
      </Text>
    </View>
  );
}

/* ---------------- styles ---------------- */
const S = StyleSheet.create({
  safe: { flex: 1, paddingHorizontal: 16, paddingTop: 45 },

  header: {
    fontSize: 20,
    fontWeight: "900",
    color: COLORS.primaryDark,
    paddingTop: 4,
    paddingBottom: 8,
    textAlign: "left",
  },

  loadingBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 4,
    paddingBottom: 6,
  },
  loadingTxt: { color: COLORS.primaryDark, fontWeight: "700" },

  wrap: { paddingVertical: 8 },
  card: {
    backgroundColor: COLORS.softMocha,
    borderRadius: 16,
    padding: 14,
    borderWidth: 0,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },

  title: {
    fontWeight: "900",
    color: COLORS.text,
    fontSize: 16,
    marginBottom: 8,
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
  windowLabel: { color: COLORS.dim, fontWeight: "900", textAlign: "left" },

  meta: {
    flex: 1,
    minWidth: 0,
    textAlign: "left",
    color: COLORS.text,
    fontWeight: "700",
    lineHeight: 18,
  },

  chip: {
    backgroundColor: COLORS.primary,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 999,
    alignSelf: "flex-start",
  },
  chipTxt: { color: "#fff", fontWeight: "900", fontSize: 12 },

  line: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 4,
    gap: 8,
  },
  lineLabel: {
    color: COLORS.dim,
    fontWeight: "800",
    width: 96,
    textAlign: "left",
  },
  lineValue: {
    color: COLORS.text,
    fontWeight: "800",
    flex: 1,
    textAlign: "left",
    minWidth: 0,
  },

  empty: {
    textAlign: "center",
    color: COLORS.dim,
    marginTop: 18,
    fontWeight: "700",
  },
});
