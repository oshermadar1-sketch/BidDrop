// app/profile-setup.tsx
// Profile completion screen.
// If the profile is already completed (first_login_completed = true OR all fields present),
// it redirects to /role_select (sender / rider / courier). After successful save, the same.

import React, { useMemo, useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Alert,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { upsertProfile, getMe } from "../lib/api";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs"; // visual background

const COLORS = {
  text: "#111827",
  dim: "#6b7280",
  primary: "#9bac70",
  border: "#e5e7eb",
  bg: "#ffffff",
};

export default function ProfileSetup() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);

  // Guard: skip if the profile is already completed
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        if (!token) return;
        const me = await getMe(String(token));
        const completed =
          !!me?.first_login_completed ||
          (!!me?.first_name &&
            !!me?.last_name &&
            !!me?.phone &&
            !!me?.email &&
            !!me?.city);
        if (mounted && completed) {
          router.replace({ pathname: "/role_select", params: { token } });
        }
      } catch {
        // ignore; allow the user to proceed with the form
      }
    })();
    return () => {
      mounted = false;
    };
  }, [token]);

  // Require all fields to enable the button (you can relax this if you want)
  const ok = useMemo(
    () =>
      firstName.trim() &&
      lastName.trim() &&
      phone.trim() &&
      email.trim() &&
      city.trim(),
    [firstName, lastName, phone, email, city]
  );

  async function handleSave() {
    if (!ok) {
      Alert.alert("שימי לב", "נא למלא את כל השדות.");
      return;
    }
    try {
      setBusy(true);
      await upsertProfile({
        token: String(token || ""),
        first_name: firstName,
        last_name: lastName,
        phone,
        email,
        city,
      });
      setBusy(false);

      // On success, the server sets first_login_completed = true.
      router.replace({ pathname: "/role_select", params: { token } });
    } catch (e: any) {
      setBusy(false);
      Alert.alert("שגיאה", e?.message || "שמירת הפרטים נכשלה");
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: COLORS.bg }}>
      <AnimatedBgBlobs />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[
            styles.container,
            { flexGrow: 1, justifyContent: "center", alignItems: "center" },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.card}>
            <Text style={styles.title}>פרטים אישיים</Text>
            <Text style={styles.subtitle}>
              מלאי את פרטייך כדי להשלים את ההרשמה.
            </Text>

            <View style={styles.field}>
              <Text style={styles.label}>שם פרטי</Text>
              <TextInput
                style={styles.input}
                value={firstName}
                onChangeText={setFirstName}
                placeholder="לדוגמה: נועה"
                textAlign="right"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>שם משפחה</Text>
              <TextInput
                style={styles.input}
                value={lastName}
                onChangeText={setLastName}
                placeholder="לדוגמה: כהן"
                textAlign="right"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>מספר פלאפון</Text>
              <TextInput
                style={styles.input}
                value={phone}
                onChangeText={setPhone}
                keyboardType="phone-pad"
                placeholder="05x-xxxxxxx"
                textAlign="right"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>אימייל</Text>
              <TextInput
                style={styles.input}
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                placeholder="name@example.com"
                autoCapitalize="none"
                textAlign="right"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>מקום מגורים</Text>
              <TextInput
                style={styles.input}
                value={city}
                onChangeText={setCity}
                placeholder="עיר/יישוב"
                textAlign="right"
              />
            </View>

            <TouchableOpacity
              style={[styles.btn, { opacity: ok && !busy ? 1 : 0.6 }]}
              onPress={handleSave}
              disabled={!ok || busy}
            >
              <Text style={styles.btnText}>
                {busy ? "שומרת…" : "שמירה והמשך"}
              </Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, paddingBottom: 28 },
  card: {
    width: "100%",
    maxWidth: 520,
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  title: {
    fontSize: 22,
    fontWeight: "800",
    color: COLORS.text,
    textAlign: "center",
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 13,
    color: COLORS.dim,
    textAlign: "center",
    marginBottom: 16,
    writingDirection: "rtl",
  },
  field: { marginBottom: 12 },
  label: {
    fontSize: 13,
    color: COLORS.dim,
    marginBottom: 6,
    writingDirection: "rtl",
  },
  input: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
    writingDirection: "rtl",
  },
  btn: {
    backgroundColor: COLORS.primary,
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: "center",
    marginTop: 4,
  },
  btnText: { color: "#fff", fontWeight: "800" },
});
