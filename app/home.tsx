// app/home.tsx
// Login screen: email + password. SubWallet is no longer needed to sign in; it is
// linked later, the first time a payment needs it. The wallet login stays available
// for accounts that were created with a wallet.
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
  I18nManager,
} from "react-native";
import { useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import PasswordField from "./components/PasswordField";
import { authStyles as S, AUTH_COLORS } from "./ui/authStyles";
import { loginWithEmail } from "../lib/api";
import { loadSession } from "../lib/session";
import { routeAfterLogin } from "../lib/afterLogin";
import { emailLooksValid } from "../lib/password";

I18nManager.allowRTL(true);

export default function HomeScreen() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // A remembered, still-valid login goes straight to the role screen.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await loadSession();
        if (token && !cancelled) {
          router.replace({ pathname: "/role_select", params: { token } });
          return;
        }
      } catch {
        // fall through to the normal login screen
      }
      if (!cancelled) setCheckingSession(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const canSubmit = emailLooksValid(email) && password.length > 0 && !busy && !checkingSession;

  const handleLogin = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy(true);
    try {
      const { access_token } = await loginWithEmail(email.trim(), password);
      await routeAfterLogin(router, String(access_token));
    } catch (e: any) {
      setErr(e?.message || "ההתחברות נכשלה");
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
            <Text style={S.title}>ברוכ/ה הבא/ה ל-BidDrop</Text>
            <Text style={S.subtitle}>
              התחבר/י עם אימייל וסיסמה. ארנק SubWallet נדרש רק בשלב התשלום.
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
                testID="login-email"
              />
            </View>

            <PasswordField label="סיסמה" value={password} onChangeText={setPassword} />

            <TouchableOpacity
              style={[S.btnPrimary, !canSubmit && S.disabled]}
              onPress={handleLogin}
              disabled={!canSubmit}
              accessibilityRole="button"
              testID="login-submit"
            >
              <Text style={S.btnPrimaryText}>{busy ? "מתחבר/ת…" : "התחברות"}</Text>
            </TouchableOpacity>

            {!!err && (
              <View style={S.errBox}>
                <Text style={S.errText}>{err}</Text>
              </View>
            )}

            <View style={S.linksRow}>
              <TouchableOpacity onPress={() => router.push("/signup")}>
                <Text style={S.link}>אין לך חשבון? הרשמה</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => router.push("/forgot-password")}>
                <Text style={S.link}>שכחת סיסמה?</Text>
              </TouchableOpacity>
            </View>

            <View style={S.dividerRow}>
              <View style={S.dividerLine} />
              <Text style={S.dividerText}>או</Text>
              <View style={S.dividerLine} />
            </View>

            <TouchableOpacity
              style={[S.btnOutline, checkingSession && S.disabled]}
              onPress={() => router.push("/wallet-login")}
              disabled={checkingSession}
              accessibilityRole="button"
              accessibilityLabel="התחברות עם SubWallet"
              testID="btn-connect-subwallet"
            >
              <Text style={S.btnOutlineText}>התחברות עם ארנק SubWallet</Text>
            </TouchableOpacity>
            <Text style={S.note}>לחשבונות שנפתחו עם ארנק.</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
