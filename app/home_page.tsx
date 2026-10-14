// app/home_page.tsx
// Home screen in the style you requested (no search bar).
// Removed "Settings" navigation (replaced with a simple Help alert).
// All comments are in English.

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  ScrollView,
  Platform,
  Alert,
  ImageBackground,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { getMe, UserRow, BASE_URL } from "../lib/api";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs"; // optional background

const COLORS = {
  text: "#111827",
  dim: "#6b7280",
  primary: "#9bac70",
  primaryDark: "#475530",
  border: "#e5e7eb",
  bg: "#ffffff",
  card: "#ffffff",
  chipBg: "#f3f4f6",
};

export default function HomeScreen() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  const [me, setMe] = useState<UserRow | null>(null);
  const [loading, setLoading] = useState(true);

  const shortWallet = (wa?: string | null) =>
    wa ? `${wa.slice(0, 6)}…${wa.slice(-4)}` : "";

  const greetingName =
    (me && [me.first_name || "", me.last_name || ""].join(" ").trim()) ||
    shortWallet(me?.wallet_address) ||
    "משתמשת";

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        if (!token) throw new Error("Missing token");
        const user = await getMe(String(token));
        if (mounted) setMe(user);
      } catch (e: any) {
        console.log("[Home] getMe error:", e?.message || e);
        Alert.alert("שגיאה", "נכשל לטעון משתמש. נסי להתחבר מחדש.", [
          { text: "אישור", onPress: () => router.replace("/wallet-login") },
        ]);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [token]);

  function goProfile() {
    router.push({ pathname: "/profile-setup", params: { token } });
  }

  function goChat() {
    Alert.alert("בקרוב", "מסך צ׳אט יתווסף כאן ✨");
  }

  function goCreate() {
    Alert.alert("פעולה", "CTA ראשי — למשל יצירת משלוח חדש.");
  }

  function goMyItems() {
    Alert.alert("פעולה", "המסכים האישיים שלי — הזמנות/משימות.");
  }

  function enableLocation() {
    Alert.alert("מיקום", "נוסיף בקשת הרשאה עם expo-location כשתרצי.");
  }

  function openHelp() {
    Alert.alert("עזרה", "צריך עזרה? כתבי לנו: support@biddrop.example");
  }

  return (
    <View style={styles.screen}>
      <AnimatedBgBlobs />

      <ScrollView
        contentContainerStyle={{ paddingBottom: 28 }}
        style={{ flex: 1 }}
        showsVerticalScrollIndicator={false}
      >
        {/* HERO */}
        <View style={styles.heroWrap}>
          <ImageBackground
            source={{
              uri: "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=800&auto=format&fit=crop",
            }}
            resizeMode="cover"
            imageStyle={styles.heroImage}
            style={styles.hero}
          >
            <View style={styles.heroOverlay} />
            <Text style={styles.helloTitle}>היי, {greetingName}</Text>
            <Text style={styles.helloSubtitle}>
              שמחות לראות אותך שוב ב־BidDrop
            </Text>

            {/* Primary floating action */}
            <TouchableOpacity style={styles.cta} onPress={goCreate}>
              <Text style={styles.ctaText}>+ יצירת בקשה</Text>
            </TouchableOpacity>
          </ImageBackground>
        </View>

        {/* LOCATION CARD */}
        <View style={styles.card}>
          <View style={{ gap: 4 }}>
            <Text style={styles.cardTitle}>נקודות קרובות</Text>
            <Text style={styles.cardSub}>
              הפעלת מיקום תציג הצעות/שליחים בקרבתך.
            </Text>
          </View>
          <TouchableOpacity onPress={enableLocation} style={styles.cardBtn}>
            <Text style={styles.cardBtnText}>הפעלת מיקום</Text>
          </TouchableOpacity>
        </View>

        {/* QUICK ACTIONS (chips) */}
        <View style={styles.section}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 12 }}
          >
            <Chip label="הבקשות שלי" onPress={goMyItems} />
            <Chip label="צ׳אט" onPress={goChat} />
            <Chip label="עריכת פרופיל" onPress={goProfile} />
            <Chip
              label="ארנק"
              onPress={() => Alert.alert("ארנק", me?.wallet_address || "—")}
            />
            <Chip label="עזרה" onPress={openHelp} />
          </ScrollView>
        </View>

        {/* RECOMMENDATIONS STRIP */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>המלצות</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 12 }}
          >
            <RecCard
              title="מסלול פופולרי"
              onPress={() => Alert.alert("המלצה", "מסלול מוצע")}
            />
            <RecCard
              title="שליחים פעילים"
              onPress={() => Alert.alert("המלצה", "רשימת שליחים")}
            />
            <RecCard
              title="מבצעים קרובים"
              onPress={() => Alert.alert("המלצה", "דילים")}
            />
          </ScrollView>
        </View>

        {/* META / DEBUG (optional) */}
        <Text style={styles.metaText}>{`API: ${BASE_URL}`}</Text>
      </ScrollView>

      {/* BOTTOM ACTION BAR (no Settings – replaced with Help) */}
      <View style={styles.bottomBar}>
        <BarBtn label="בית" active onPress={() => {}} />
        <BarBtn label="גלריה" onPress={() => Alert.alert("בקרוב", "גלריה")} />
        <TouchableOpacity style={styles.centerFab} onPress={goCreate}>
          <Text style={{ color: "#fff", fontWeight: "900", fontSize: 18 }}>
            ＋
          </Text>
        </TouchableOpacity>
        <BarBtn label="צ׳אט" onPress={goChat} />
        <BarBtn label="עזרה" onPress={openHelp} />
      </View>

      {loading && (
        <View style={styles.loading}>
          <ActivityIndicator size="large" />
        </View>
      )}
    </View>
  );
}

/* --------------------------- Small UI helpers --------------------------- */

function Chip({ label, onPress }: { label: string; onPress?: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.chip}>
      <Text style={styles.chipText}>{label}</Text>
    </TouchableOpacity>
  );
}

function RecCard({ title, onPress }: { title: string; onPress?: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.recCard}>
      <View style={{ flex: 1, justifyContent: "space-between" }}>
        <Text style={styles.recTitle}>{title}</Text>
        <Text style={styles.recHint}>פרטים</Text>
      </View>
      <View style={styles.recThumb} />
    </TouchableOpacity>
  );
}

function BarBtn({
  label,
  onPress,
  active,
}: {
  label: string;
  onPress?: () => void;
  active?: boolean;
}) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.barBtn}>
      <Text
        style={[styles.barBtnText, active && { color: COLORS.primaryDark }]}
      >
        {label}
      </Text>
    </TouchableOpacity>
  );
}

/* -------------------------------- Styles -------------------------------- */

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  heroWrap: {
    paddingHorizontal: 12,
    paddingTop: Platform.select({ ios: 8, android: 6, default: 8 }),
  },
  hero: {
    height: 180,
    borderRadius: 20,
    overflow: "hidden",
    padding: 16,
    justifyContent: "center",
  },
  heroImage: { borderRadius: 20 },
  heroOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.25)",
  },
  helloTitle: {
    fontSize: 28,
    fontWeight: "900",
    color: "#fff",
    textAlign: "center",
    writingDirection: "rtl",
  },
  helloSubtitle: {
    marginTop: 6,
    fontSize: 14,
    color: "#f3f4f6",
    textAlign: "center",
    writingDirection: "rtl",
  },
  cta: {
    position: "absolute",
    bottom: 14,
    alignSelf: "center",
    backgroundColor: COLORS.primary,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 999,
    borderWidth: 2,
    borderColor: "rgba(255,255,255,0.75)",
  },
  ctaText: { color: "#fff", fontWeight: "900" },

  card: {
    marginTop: 14,
    marginHorizontal: 12,
    backgroundColor: COLORS.card,
    borderRadius: 16,
    padding: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
    flexDirection: "row-reverse",
    alignItems: "center",
    justifyContent: "space-between",
  },
  cardTitle: {
    color: COLORS.text,
    fontWeight: "800",
    fontSize: 16,
    writingDirection: "rtl",
  },
  cardSub: { color: COLORS.dim, fontSize: 12, writingDirection: "rtl" },
  cardBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  cardBtnText: { color: "#fff", fontWeight: "800" },

  section: { marginTop: 14 },
  sectionTitle: {
    marginRight: 16,
    marginBottom: 8,
    color: COLORS.text,
    fontWeight: "800",
    fontSize: 16,
    writingDirection: "rtl",
  },

  chip: {
    backgroundColor: COLORS.chipBg,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    marginHorizontal: 4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  chipText: { color: COLORS.text, fontWeight: "700" },

  recCard: {
    width: 260,
    height: 110,
    backgroundColor: "#fff",
    borderRadius: 18,
    marginHorizontal: 6,
    padding: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
    flexDirection: "row-reverse",
    alignItems: "center",
  },
  recTitle: {
    color: COLORS.text,
    fontWeight: "800",
    fontSize: 16,
    writingDirection: "rtl",
  },
  recHint: { color: COLORS.dim, fontSize: 12, writingDirection: "rtl" },
  recThumb: {
    width: 70,
    height: 70,
    borderRadius: 14,
    backgroundColor: COLORS.primary,
    opacity: 0.8,
    marginLeft: 12,
  },

  metaText: {
    marginTop: 10,
    textAlign: "center",
    color: COLORS.dim,
    fontSize: 12,
  },

  bottomBar: {
    position: "absolute",
    left: 12,
    right: 12,
    bottom: 12 + (Platform.OS === "ios" ? 10 : 0),
    backgroundColor: "#fff",
    borderRadius: 22,
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
  },
  barBtn: { paddingHorizontal: 6, paddingVertical: 6 },
  barBtnText: { color: COLORS.dim, fontWeight: "800" },
  centerFab: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    marginHorizontal: 4,
  },

  loading: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.6)",
  },
});
