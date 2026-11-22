// app/set-password.tsx
// Gives the logged-in account a password, so it can also sign in with email + password.
// Reached from the role screen; wallet accounts have no password yet, so only the new
// password is asked for. An account that already has one must type the current one too.
import React, { useState } from "react";
import { SafeAreaView, View, Text, TouchableOpacity, ScrollView } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import PasswordField from "./components/PasswordField";
import { authStyles as S } from "./ui/authStyles";
import { setPassword as apiSetPassword } from "../lib/api";
import { passwordIsStrong } from "../lib/password";

export default function SetPasswordScreen() {
  const router = useRouter();
  const { token, hasPassword, email } = useLocalSearchParams<{
    token?: string;
    hasPassword?: string;
    email?: string;
  }>();
  const changing = hasPassword === "1";
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit =
    !!token && passwordIsStrong(password) && confirm === password && (!changing || current.length > 0) && !busy;

  const handleSave = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy(true);
    try {
      await apiSetPassword(String(token), password, changing ? current : undefined);
      setDone(true);
    } catch (e: any) {
      setErr(e?.message || "השמירה נכשלה");
    } finally {
      setBusy(false);
    }
  };

  const back = () => router.replace({ pathname: "/role_select", params: { token: String(token) } });

  return (
    <SafeAreaView style={S.screen}>
      <AnimatedBgBlobs />
      <ScrollView contentContainerStyle={S.scroll} keyboardShouldPersistTaps="handled">
        <View style={S.card}>
          <Text style={S.title}>{changing ? "שינוי סיסמה" : "קביעת סיסמה"}</Text>

          {done ? (
            <>
              <View style={S.okBox}>
                <Text style={S.okText}>
                  הסיסמה נשמרה. מעכשיו אפשר להתחבר גם עם האימייל {email || ""} והסיסמה, בלי הארנק.
                </Text>
              </View>
              <TouchableOpacity style={[S.btnPrimary, { marginTop: 16 }]} onPress={back}>
                <Text style={S.btnPrimaryText}>חזרה</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <Text style={S.subtitle}>
                {changing
                  ? "הסיסמה החדשה תחליף את הקודמת."
                  : `החשבון נפתח עם ארנק. עם סיסמה אפשר להתחבר גם עם האימייל ${email || ""} בלי לפתוח את הארנק.`}
              </Text>
              {changing && (
                <PasswordField label="סיסמה נוכחית" value={current} onChangeText={setCurrent} />
              )}
              <PasswordField label="סיסמה חדשה" value={password} onChangeText={setPassword} showRules />
              <PasswordField label="אימות סיסמה" value={confirm} onChangeText={setConfirm} onSubmit={handleSave} />
              {confirm.length > 0 && confirm !== password && (
                <Text style={[S.errText, { marginTop: -6, marginBottom: 8 }]}>הסיסמאות אינן זהות</Text>
              )}
              <TouchableOpacity
                style={[S.btnPrimary, !canSubmit && S.disabled]}
                onPress={handleSave}
                disabled={!canSubmit}
              >
                <Text style={S.btnPrimaryText}>{busy ? "שומר/ת…" : "שמירת הסיסמה"}</Text>
              </TouchableOpacity>
              {!!err && (
                <View style={S.errBox}>
                  <Text style={S.errText}>{err}</Text>
                </View>
              )}
              <View style={S.linksRow}>
                <TouchableOpacity onPress={back}>
                  <Text style={S.link}>ביטול</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
