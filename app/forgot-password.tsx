// app/forgot-password.tsx
// Ask for a password-reset link. The server answers the same whether or not the email
// has an account, so the form cannot be used to find out who is registered.
import React, { useState } from "react";
import { SafeAreaView, View, Text, TextInput, TouchableOpacity, ScrollView } from "react-native";
import { useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import { authStyles as S, AUTH_COLORS } from "./ui/authStyles";
import { forgotPassword } from "../lib/api";
import { emailLooksValid } from "../lib/password";

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit = emailLooksValid(email) && !busy;

  const handleSend = async () => {
    if (!canSubmit) return;
    setErr(null);
    setBusy(true);
    try {
      await forgotPassword(email.trim());
      setSent(true);
    } catch (e: any) {
      setErr(e?.message || "השליחה נכשלה, נסה/י שוב");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={S.screen}>
      <AnimatedBgBlobs />
      <ScrollView contentContainerStyle={S.scroll} keyboardShouldPersistTaps="handled">
        <View style={S.card}>
          <Text style={S.title}>איפוס סיסמה</Text>
          <Text style={S.subtitle}>
            נשלח לאימייל קישור לבחירת סיסמה חדשה. הקישור תקף לשעה.
          </Text>

          {sent ? (
            <View style={S.okBox}>
              <Text style={S.okText}>
                אם קיים חשבון עם הכתובת {email.trim()}, נשלח אליה עכשיו קישור לאיפוס.
                בדוק/י גם בתיקיית הספאם.
              </Text>
            </View>
          ) : (
            <>
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
                  onSubmitEditing={handleSend}
                  returnKeyType="send"
                />
              </View>
              <TouchableOpacity
                style={[S.btnPrimary, !canSubmit && S.disabled]}
                onPress={handleSend}
                disabled={!canSubmit}
              >
                <Text style={S.btnPrimaryText}>{busy ? "שולח/ת…" : "שליחת קישור"}</Text>
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
              <Text style={S.link}>חזרה להתחברות</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
