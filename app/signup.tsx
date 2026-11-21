// app/signup.tsx
// Create an account with email and password. A verification link is emailed; the
// account can be used right away and the role screen reminds until it is verified.
import React, { useEffect, useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import PasswordField from "./components/PasswordField";
import { authStyles as S, AUTH_COLORS } from "./ui/authStyles";
import { registerWithEmail } from "../lib/api";
import { routeAfterLogin } from "../lib/afterLogin";
import { emailLooksValid, passwordIsStrong } from "../lib/password";

export default function SignupScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // The free server sleeps when idle; the first request can take up to a minute
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) {
      setSlow(false);
      return;
    }
    const t = setTimeout(() => setSlow(true), 4000);
    return () => clearTimeout(t);
  }, [busy]);
  const [info, setInfo] = useState<string | null>(null);

  const passwordsMatch = confirm.length === 0 || confirm === password;
  const canSubmit =
    emailLooksValid(email) &&
    passwordIsStrong(password) &&
    confirm === password &&
    !busy;

  const handleSignup = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy(true);
    try {
      const res = await registerWithEmail(email.trim(), password);
      if (res.existing_wallet_account || !res.access_token) {
        setInfo(res.detail || "כתובת האימייל שייכת לחשבון קיים.");
        setBusy(false);
        return;
      }
      await routeAfterLogin(router, String(res.access_token));
    } catch (e: any) {
      setErr(e?.message || "ההרשמה נכשלה");
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={S.screen}>
      <AnimatedBgBlobs />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView contentContainerStyle={S.scroll} keyboardShouldPersistTaps="handled">
          <View style={S.card}>
            <Text style={S.title}>הרשמה ל-BidDrop</Text>
            <Text style={S.subtitle}>
              נשלח קישור אימות לאימייל. את הפרטים האישיים ממלאים בשלב הבא.
            </Text>

            <View style={S.field}>
              <Text style={S.label}>אימייל</Text>
              <TextInput
                style={S.input}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="name@example.com"
                placeholderTextColor={AUTH_COLORS.dim}
                testID="signup-email"
              />
            </View>

            <PasswordField label="סיסמה" value={password} onChangeText={setPassword} showRules />
            <PasswordField label="אימות סיסמה" value={confirm} onChangeText={setConfirm} />
            {!passwordsMatch && (
              <Text style={[S.errText, { marginTop: -6, marginBottom: 8 }]}>
                הסיסמאות אינן זהות
              </Text>
            )}

            <TouchableOpacity
              style={[S.btnPrimary, !canSubmit && S.disabled]}
              onPress={handleSignup}
              disabled={!canSubmit}
              accessibilityRole="button"
              testID="signup-submit"
            >
              <Text style={S.btnPrimaryText}>{busy ? "נרשם/ת…" : "יצירת חשבון"}</Text>
            </TouchableOpacity>

            {busy && slow && (
              <Text style={S.note}>השרת מתעורר, זה יכול לקחת עד דקה…</Text>
            )}
            {!!err && (
              <View style={S.errBox}>
                <Text style={S.errText}>{err}</Text>
              </View>
            )}
            {!!info && (
              <View style={S.okBox}>
                <Text style={S.okText}>{info}</Text>
              </View>
            )}

            <View style={S.linksRow}>
              {!!info && (
                <TouchableOpacity onPress={() => router.push("/wallet-login")}>
                  <Text style={S.link}>התחברות עם SubWallet</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity onPress={() => router.replace("/home")}>
                <Text style={S.link}>יש לך כבר חשבון? התחברות</Text>
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
