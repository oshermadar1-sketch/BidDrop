// app/role_select.tsx
// Role selection → navigates to "/[role]_home_page".

import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  SafeAreaView,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  useWindowDimensions,
  Alert,
  Platform,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useRouter, useLocalSearchParams } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";

import { registerAndSyncPushToken, getPushDebugReport } from "../lib/push";
import {
  BASE_URL,
  updateUserRole,
  getMyProfile,
  getCourierProfile,
  type BackendRole,
} from "../lib/api";
const COLORS = {
  bg: "#ffffff",
  text: "#0b0b0b",
  dim: "#6b7280",
  primary: "#9bac70",
  primaryDark: "#475530",
  mocha: "#8b5e3c",
  border: "#e5e7eb",
  card: "#ffffff",
};

type RoleKey = "sender" | "rider" | "courier";

export default function RoleSelectScreen() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [name, setName] = useState<string>("");

  // למנוע רישום כפול אם המסך נטען שוב
  const didRegisterRef = useRef(false);

  // רוחב כרטיס רספונסיבי
  const { width } = useWindowDimensions();
  const CARD_W = Math.min(width * 0.92, 480);

useEffect(() => {
  (async () => {
    if (!token) return;

    try {
      const user = await getMyProfile(String(token));
      const displayName =
        `${user.first_name || ""} ${user.last_name || ""}`.trim();

      setName(displayName);
    } catch (e) {
      console.log("Failed loading user name", e);
    }
  })();
}, [token]);

  // רישום טוקן לשרת אחרי התחברות (פעם אחת)
  useEffect(() => {
    (async () => {
      if (!token || didRegisterRef.current) return;
      didRegisterRef.current = true;
      try {
        console.log(
          "[PUSH] Post-login: registering Expo token… (platform:",
          Platform.OS,
          ")"
        );
        const synced = await registerAndSyncPushToken(BASE_URL, String(token));
        console.log("[PUSH] registerAndSyncPushToken →", synced ?? "(null)");
        if (!synced) {
          console.log(
            "[PUSH] Registration returned null (no token or server error)."
          );
        }
      } catch (e) {
        console.log("[PUSH] Post-login push registration failed:", e);
      }
    })();
  }, [token]);

  const goNext = useCallback(
    async (role: RoleKey) => {
      // Map UI role -> backend role
      // - courier → driver
      // - sender / rider → sender
      const backendRole: BackendRole = role === "courier" ? "driver" : "sender";

      try {
        await AsyncStorage.setItem("role_today", role);
      } catch {}

      // If we have a token, try to update role in DB (but do not block navigation on failure)
      if (token) {
        try {
          await updateUserRole(String(token), backendRole);
        } catch (e) {
          console.log("[RoleSelect] Failed to update backend role:", e);
        }
      }

      // Couriers without age/vehicle first fill in the short courier profile
      if (role === "courier" && token) {
        try {
          const profile = await getCourierProfile(String(token));
          if (!profile.completed) {
            router.replace({
              pathname: "/courier_profile",
              params: { token: String(token) },
            });
            return;
          }
        } catch (e) {
          console.log("[RoleSelect] Courier profile check failed:", e);
        }
      }

      // Navigate to the chosen home page (UI role)
      router.replace({
        pathname: `/${role}_home_page`,
        params: token ? { token: String(token) } : {},
      });
    },
    [router, token]
  );

  // כפתור בדיקה שמציג דו"ח מלא ב-Alert (ללא תלות בלוגים)
  const runPushDebug = useCallback(async () => {
    try {
      const report = await getPushDebugReport();
      Alert.alert("Push Debug", report);
    } catch (e) {
      Alert.alert("Push Debug", String(e));
    }
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <AnimatedBgBlobs />
      <View style={styles.center}>
        <View style={[styles.card, { width: CARD_W }]}>
          <Text style={styles.title}>
            {name
              ? `היי ${name}, בתור מי תרצו להתקדם מכאן?`
              : "היי, בתור מי תרצו להתקדם מכאן?"}
          </Text>
          <Text style={styles.subtitle}>
            אפשר לשנות בכל רגע מהפרופיל. הבחירה תתאים את דף הבית והתפריטים.
          </Text>

          <RoleItem
            emoji="📦"
            title="שולח/ת חבילה"
            desc="צרו משלוח חדש, עקבו אחרי משלוחים קיימים"
            accent={COLORS.mocha}
            onPress={() => goNext("sender")}
          />
          <RoleItem
            emoji="🚗"
            title="מחפש/ת טרמפ"
            desc="מצאו טרמפ במסלולים קרובים והצטרפו אליו"
            accent={COLORS.primary}
            onPress={() => goNext("rider")}
          />
          <RoleItem
            emoji="🛵"
            title="שליח/ה"
            desc="קבלו בקשות חדשות, מסלולים מומלצים"
            accent={COLORS.primaryDark}
            onPress={() => goNext("courier")}
          />

          {/* כפתור בדיקת פוש – מציג דו״ח מלא */}
          <TouchableOpacity
            onPress={runPushDebug}
            style={{
              marginTop: 12,
              alignSelf: "center",
              paddingVertical: 10,
              paddingHorizontal: 14,
              borderWidth: 1,
              borderRadius: 10,
              borderColor: COLORS.border,
            }}
          >
            <Text style={{ color: COLORS.text }}>בדיקת פוש (מציג דו״ח)</Text>
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
}

function RoleItem({
  emoji,
  title,
  desc,
  accent,
  onPress,
}: {
  emoji: string;
  title: string;
  desc: string;
  accent: string;
  onPress?: () => void;
}) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.roleRow, { borderColor: accent }]}
      activeOpacity={0.9}
    >
      <View
        style={[
          styles.roleEmoji,
          { backgroundColor: accent + "22", borderColor: accent },
        ]}
      >
        <Text style={{ fontSize: 22 }}>{emoji}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.roleTitle}>{title}</Text>
        <Text style={styles.roleDesc}>{desc}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  card: {
    backgroundColor: COLORS.card,
    borderRadius: 16,
    padding: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
    shadowColor: "#000",
    shadowOpacity: 0.07,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  title: {
    fontSize: 20,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "center",
    writingDirection: "rtl",
  },
  subtitle: {
    marginTop: 6,
    fontSize: 13,
    color: COLORS.dim,
    textAlign: "center",
    writingDirection: "rtl",
    marginBottom: 10,
  },
  roleRow: {
    flexDirection: "row-reverse",
    alignItems: "center",
    gap: 12,
    borderWidth: 2,
    borderRadius: 14,
    padding: 12,
    marginTop: 10,
    backgroundColor: "#fff",
  },
  roleEmoji: {
    width: 44,
    height: 44,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1.5,
  },
  roleTitle: {
    fontSize: 16,
    fontWeight: "800",
    color: COLORS.text,
    writingDirection: "rtl",
  },
  roleDesc: {
    fontSize: 12,
    color: COLORS.dim,
    writingDirection: "rtl",
  },
});
