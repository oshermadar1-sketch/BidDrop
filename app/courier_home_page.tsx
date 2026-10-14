// app/courier_home_page.tsx
// Courier Home — gradient, two-line headline, RTL, mocha translucent cards.
// Hides Expo Router header.

import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams, useRouter, Stack } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import {
  getMyProfile,
  getCourierMetrics,
  listMyCourierOffers,
  type CourierMetrics,
} from "../lib/api";

const GREEN_1 = "#DDECCB";
const GREEN_2 = "#CBE1B4";
const GREEN_3 = "#BFD8A0";
const GREEN_4 = "#9BAC70";
const CARD_BG = "rgba(181,133,94,0.22)";
const CARD_BORDER = "rgba(181,133,94,0.35)";
const TXT = "#0b0b0b";

export default function CourierHome() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  const [firstName, setFirstName] = useState("");
  const [metrics, setMetrics] = useState<CourierMetrics | null>(null);
  const [activeOffers, setActiveOffers] = useState<number>(0);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    const meP = getMyProfile(String(token)).catch(() => null);
    const mP = getCourierMetrics(String(token)).catch(() => null);
    const offersP = listMyCourierOffers(String(token), {
      status: "active",
      limit: 200,
      offset: 0,
    }).catch(() => []);
    const [me, m, offers] = await Promise.all([meP, mP, offersP]);
    setFirstName(me?.first_name || "");
    setMetrics(m ?? null);
    setActiveOffers(offers.length);
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const goAvailable = () =>
    router.push({
      pathname: "/bucket_list",
      params: { token: String(token), role: "courier", bucket: "available" },
    });
  const goActive = () =>
    router.push({
      pathname: "/bucket_list",
      params: { token: String(token), role: "courier", bucket: "active" },
    });
  const goDone = () =>
    router.push({
      pathname: "/bucket_list",
      params: { token: String(token), role: "courier", bucket: "delivered" },
    });
  const newAvailability = () =>
    router.push({ pathname: "/courier_offer_create", params: { token } });

  return (
    <View style={{ flex: 1 }}>
      <Stack.Screen options={{ headerShown: false }} />

      <LinearGradient
        colors={[GREEN_1, GREEN_2, GREEN_3, GREEN_4]}
        start={{ x: 1, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={S.gradient}
      >
        <ScrollView
          contentContainerStyle={S.scroll}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        >
          <View style={S.userBar}>
            <Text style={S.userName} numberOfLines={1}>
              {firstName ? `היי, ${firstName}` : "היי!"}
            </Text>
            <TouchableOpacity
              style={S.switchBtn}
              onPress={() =>
                router.push({ pathname: "/role_select", params: { token } })
              }
              activeOpacity={0.85}
            >
              <Ionicons name="swap-horizontal" size={16} color={TXT} />
              <Text style={S.switchLabel}>החלפת תפקיד</Text>
            </TouchableOpacity>
          </View>

          <View style={S.titleWrap}>
            <Text style={S.titleLine1}>הופכים כל נסיעה</Text>
            <Text style={S.titleLine2}>
              להזדמנות משתלמת<Text style={S.spark}>✨</Text>
            </Text>
          </View>

          <View style={S.cardsRow}>
            <StatusCard
              title="הושלמו"
              subtitle="משימות שסיימת"
              count={metrics?.delivered_count ?? 0}
              onPress={goDone}
              icon="checkmark-done"
            />
            <StatusCard
              title="בטיפול"
              subtitle="משימות פעילות"
              count={metrics?.active_count ?? 0}
              onPress={goActive}
              icon="bicycle"
            />
            <StatusCard
              title="זמינות"
              subtitle="הצעות פעילות שלך"
              count={activeOffers}
              onPress={goAvailable}
              icon="notifications"
            />
          </View>

          <View style={S.linksCol}>
            <LinkBtn
              label="כל הזמינויות שלך"
              onPress={goAvailable}
              icon="notifications"
            />
            <LinkBtn
              label="כל המשימות שבביצוע"
              onPress={goActive}
              icon="bicycle"
            />
            <LinkBtn
              label="משימות שהושלמו"
              onPress={goDone}
              icon="checkmark-done"
            />
          </View>
        </ScrollView>

        <TouchableOpacity
          style={S.ctaBar}
          onPress={newAvailability}
          activeOpacity={0.9}
        >
          <Text style={S.ctaText}>הוספת זמינות</Text>
          <Ionicons
            name="chevron-back"
            size={18}
            color="#fff"
            style={{ transform: [{ rotate: "180deg" }] }}
          />
        </TouchableOpacity>
      </LinearGradient>
    </View>
  );
}

function StatusCard({
  title,
  subtitle,
  count,
  onPress,
  icon,
}: {
  title: string;
  subtitle: string;
  count: number;
  onPress: () => void;
  icon: keyof typeof Ionicons.glyphMap;
}) {
  return (
    <TouchableOpacity style={S.card} onPress={onPress} activeOpacity={0.85}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <Ionicons name={icon} size={18} color={TXT} />
        <Text style={S.cardTitle}>{title}</Text>
      </View>
      <Text style={S.cardSub} numberOfLines={2}>
        {subtitle}
      </Text>
      <Text style={S.cardCount}>{count}</Text>
    </TouchableOpacity>
  );
}

function LinkBtn({
  label,
  onPress,
  icon,
}: {
  label: string;
  onPress: () => void;
  icon: keyof typeof Ionicons.glyphMap;
}) {
  return (
    <TouchableOpacity style={S.linkBtn} onPress={onPress} activeOpacity={0.85}>
      <Ionicons name={icon} size={16} color={TXT} />
      <Text style={S.linkLabel}>{label}</Text>
      <Ionicons
        name="chevron-back"
        size={16}
        color={TXT}
        style={{ transform: [{ rotate: "180deg" }] }}
      />
    </TouchableOpacity>
  );
}

const S = StyleSheet.create({
  gradient: {
    flex: 1,
    paddingTop: 24,
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  scroll: { paddingBottom: 96 },

  userBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingTop: 12,
  },
  userName: { color: TXT, fontSize: 16, fontWeight: "800", textAlign: "right" },

  titleWrap: {
    marginTop: 10,
    alignItems: "flex-start",
    paddingHorizontal: 4,
    marginBottom: 14,
  },
  titleLine1: {
    fontSize: 30,
    fontWeight: "900",
    color: TXT,
    textAlign: "left",
  },
  titleLine2: {
    fontSize: 26,
    fontWeight: "600",
    fontStyle: "italic",
    color: "#1a1a1a",
    textAlign: "left",
    marginTop: -4,
  },
  spark: { fontStyle: "normal" },

  cardsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    justifyContent: "space-between",
  },
  card: {
    width: "48%",
    backgroundColor: CARD_BG,
    borderRadius: 16,
    padding: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: CARD_BORDER,
  },
  cardTitle: { color: TXT, fontSize: 14, fontWeight: "800" },
  cardSub: {
    color: TXT,
    opacity: 0.85,
    fontSize: 12,
    marginTop: 6,
    minHeight: 32,
  },
  cardCount: { color: TXT, fontSize: 28, fontWeight: "900", marginTop: 6 },

  switchBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.7)",
  },
  switchLabel: {
    fontSize: 12,
    fontWeight: "700",
    color: TXT,
  },

  linksCol: { marginTop: 16, gap: 10 },
  linkBtn: {
    backgroundColor: CARD_BG,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: CARD_BORDER,
  },
  linkLabel: { color: TXT, fontSize: 14, fontWeight: "700" },

  ctaBar: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 18,
    height: 54,
    backgroundColor: "#C19A6B",
    borderRadius: 28,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "900" },
});
