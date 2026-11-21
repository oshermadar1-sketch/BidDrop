// app/signup.tsx
// Create an account with email and password. A verification link is emailed; the
// account can be used right away and the role screen reminds until it is verified.
import React, { useState } from "react";
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
      const { access_token } = await registerWithEmail(email.trim(), password);
      await routeAfterLogin(router, String(access_token));
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

            {!!err && (
              <View style={S.errBox}>
                <Text style={S.errText}>{err}</Text>
              </View>
            )}

            <View style={S.linksRow}>
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
