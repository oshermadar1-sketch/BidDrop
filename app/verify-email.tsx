// app/verify-email.tsx
// Opened from the link in the verification email (…/verify-email?token=…). Confirms the
// address on the server and continues to the app when a login is remembered.
import React, { useEffect, useState } from "react";
import { SafeAreaView, View, Text, TouchableOpacity, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import { authStyles as S } from "./ui/authStyles";
import { verifyEmail } from "../lib/api";
import { loadSession } from "../lib/session";

export default function VerifyEmailScreen() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) {
        setErr("הקישור חסר. פתח/י את הקישור מתוך האימייל.");
        setState("error");
        return;
      }
      try {
        await verifyEmail(String(token));
        if (!cancelled) setState("ok");
      } catch (e: any) {
        if (!cancelled) {
          setErr(e?.message || "האימות נכשל");
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const goOn = async () => {
    const saved = await loadSession().catch(() => null);
    if (saved) router.replace({ pathname: "/role_select", params: { token: saved } });
    else router.replace("/home");
  };

  return (
    <SafeAreaView style={S.screen}>
      <AnimatedBgBlobs />
      <View style={S.scroll}>
        <View style={S.card}>
          <Text style={S.title}>אימות אימייל</Text>
          {state === "working" && (
            <View style={{ marginTop: 16, alignItems: "center" }}>
              <ActivityIndicator />
              <Text style={S.subtitle}>מאמתים את הכתובת…</Text>
            </View>
          )}
          {state === "ok" && (
            <View style={S.okBox}>
              <Text style={S.okText}>כתובת האימייל אומתה. תודה!</Text>
            </View>
          )}
          {state === "error" && (
            <View style={S.errBox}>
              <Text style={S.errText}>{err}</Text>
            </View>
          )}
          {state !== "working" && (
            <TouchableOpacity style={[S.btnPrimary, { marginTop: 16 }]} onPress={goOn}>
              <Text style={S.btnPrimaryText}>להמשך</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}
