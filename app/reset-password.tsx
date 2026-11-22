// app/reset-password.tsx
// Opened from the link in the reset email (…/reset-password?token=…). Sets a new
// password through the one-time token and sends the user back to the login screen.
import React, { useState } from "react";
import { SafeAreaView, View, Text, TouchableOpacity, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import PasswordField from "./components/PasswordField";
import { authStyles as S } from "./ui/authStyles";
import { resetPassword } from "../lib/api";
import { passwordIsStrong } from "../lib/password";

export default function ResetPasswordScreen() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit = !!token && passwordIsStrong(password) && confirm === password && !busy;

  const handleReset = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy(true);
    try {
      await resetPassword(String(token), password);
      setDone(true);
    } catch (e: any) {
      setErr(e?.message || "האיפוס נכשל");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={S.screen}>
      <AnimatedBgBlobs />
      <ScrollView contentContainerStyle={S.scroll} keyboardShouldPersistTaps="handled">
        <View style={S.card}>
          <Text style={S.title}>בחירת סיסמה חדשה</Text>

          {!token ? (
            <View style={S.errBox}>
              <Text style={S.errText}>הקישור חסר. פתח/י את הקישור מתוך האימייל.</Text>
            </View>
          ) : done ? (
            <View style={S.okBox}>
              <Text style={S.okText}>הסיסמה עודכנה. אפשר להתחבר עם הסיסמה החדשה.</Text>
            </View>
          ) : (
            <>
              <Text style={S.subtitle}>הסיסמה החדשה תחליף את הקודמת בכל המכשירים.</Text>
              <PasswordField label="סיסמה חדשה" value={password} onChangeText={setPassword} showRules />
              <PasswordField label="אימות סיסמה" value={confirm} onChangeText={setConfirm} onSubmit={handleReset} />
              {confirm.length > 0 && confirm !== password && (
                <Text style={[S.errText, { marginTop: -6, marginBottom: 8 }]}>הסיסמאות אינן זהות</Text>
              )}
              <TouchableOpacity
                style={[S.btnPrimary, !canSubmit && S.disabled]}
                onPress={handleReset}
                disabled={!canSubmit}
              >
                <Text style={S.btnPrimaryText}>{busy ? "מעדכן/ת…" : "עדכון הסיסמה"}</Text>
              </TouchableOpacity>
            </>
          )}

          {!!err && (
            <View style={S.errBox}>
              <Text style={S.errText}>{err}</Text>
            </View>
          )}

          <View style={S.linksRow}>
            <TouchableOpacity onPress={() => router.replace("/home")}>
              <Text style={S.link}>{done ? "להתחברות" : "חזרה להתחברות"}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
