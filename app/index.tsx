// app/index.tsx
import React, { useEffect, useCallback } from "react";
import {
  SafeAreaView,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
  useWindowDimensions,
} from "react-native";
import { useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import BubblesBg from "./components/AnimatedBgBlobs";

SplashScreen.preventAutoHideAsync().catch(() => {});

// עדכני לנתיב האייקון השקוף שלך
const appIcon = require("../assets/images/icon_without_background.png");

const COLORS = {
  bg: "#ffffff",
  text: "#0b0b0b",
  dim: "#6b7280",
  primary: "#9bac70",
};

export default function Index() {
  const router = useRouter();
  const { height } = useWindowDimensions();

  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);
  const start = useCallback(() => router.replace("/home"), [router]);

  const topOffset = Math.max(28, Math.round(height * 0.12));
  const iconBoxHeight = Math.max(260, Math.round(height * 0.44));
  const iconTopShift = Math.round(height * 0.02); // האייקון מעט למטה

  // ⬆️ מרימים את הכפתור מעלה (כ-14% מגובה המסך). אפשר לכוון 0.12–0.18
  const bottomLift = Math.max(40, Math.round(height * 0.14));

  return (
    <SafeAreaView style={styles.safe}>
      <BubblesBg />

      <View style={[styles.top, { marginTop: topOffset }]}>
        <Text style={styles.h1}>טרמפים ומשלוחים — על הדרך</Text>
        <Text style={styles.lead}>
          נהגים מרוויחים תוך כדי נסיעה, נוסעים מצטרפים בקלות, וחבילות מגיעות מהר
          — במחיר הוגן ובשקיפות מלאה.
        </Text>
      </View>

      <View
        style={[
          styles.center,
          { height: iconBoxHeight, marginTop: iconTopShift },
        ]}
      >
        <Image
          source={appIcon}
          style={styles.icon}
          resizeMode="contain"
          accessibilityIgnoresInvertColors
        />
      </View>

      {/* כפתור מוצמד אבסולוטית ומורם מעלה */}
      <View style={[styles.bottomAbs, { bottom: bottomLift }]}>
        <TouchableOpacity style={styles.cta} onPress={start}>
          <Text style={styles.ctaText}>נתחיל</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  top: { alignItems: "center", paddingHorizontal: 18 },
  h1: {
    fontSize: 24,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "center",
    writingDirection: "rtl",
  },
  lead: {
    marginTop: 8,
    fontSize: 14,
    lineHeight: 21,
    color: COLORS.dim,
    textAlign: "center",
    writingDirection: "rtl",
    width: "92%",
    maxWidth: 560,
  },
  center: { alignItems: "center", justifyContent: "center", width: "100%" },
  icon: { width: "100%", height: "100%" },
  bottomAbs: {
    position: "absolute",
    left: 18,
    right: 18,
    alignItems: "center",
  },
  cta: {
    backgroundColor: COLORS.primary,
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderRadius: 22,
    minWidth: 220,
    alignItems: "center",
  },
  ctaText: { color: "#fff", fontWeight: "800", fontSize: 16 },
});
