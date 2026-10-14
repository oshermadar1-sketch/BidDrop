// app/courier_profile.tsx
// Short courier profile (age, vehicle type, vehicle condition), asked once when a user
// first chooses the courier role. These are inputs of the delivery-time ML model and make
// its predictions more accurate. Same look as profile-setup.

import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";
import {
  getCourierProfile,
  saveCourierProfile,
  type VehicleType,
} from "../lib/api";

const COLORS = {
  text: "#111827",
  dim: "#6b7280",
  primary: "#9bac70",
  border: "#e5e7eb",
  bg: "#ffffff",
};

const VEHICLES: { key: VehicleType; label: string }[] = [
  { key: "motorcycle", label: "🏍️ אופנוע" },
  { key: "scooter", label: "🛵 קטנוע" },
  { key: "electric_scooter", label: "⚡ קטנוע חשמלי" },
];

// Same scale as the training data: 0 poor, 1 ok, 2 good
const CONDITIONS: { key: 0 | 1 | 2; label: string }[] = [
  { key: 2, label: "טוב" },
  { key: 1, label: "בינוני" },
  { key: 0, label: "ישן / לא במצב טוב" },
];

export default function CourierProfile() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  const [age, setAge] = useState("");
  const [vehicle, setVehicle] = useState<VehicleType | null>(null);
  const [condition, setCondition] = useState<0 | 1 | 2 | null>(null);
  const [busy, setBusy] = useState(false);

  // Prefill when editing an existing profile
  useEffect(() => {
    if (!token) return;
    getCourierProfile(String(token))
      .then((p) => {
        if (p.age != null) setAge(String(p.age));
        if (p.vehicle_type) setVehicle(p.vehicle_type);
        if (p.vehicle_condition != null) setCondition(p.vehicle_condition);
      })
      .catch(() => {});
  }, [token]);

  const ageNum = Number(age);
  const ok =
    Number.isInteger(ageNum) &&
    ageNum >= 16 &&
    ageNum <= 80 &&
    vehicle != null &&
    condition != null;

  async function handleSave() {
    if (!token) {
      Alert.alert("שגיאה", "אסימון התחברות חסר");
      return;
    }
    if (!ok) {
      Alert.alert("שימי לב", "מלאי גיל (16-80), סוג רכב ומצב הרכב");
      return;
    }
    try {
      setBusy(true);
      await saveCourierProfile(String(token), {
        age: ageNum,
        vehicle_type: vehicle!,
        vehicle_condition: condition!,
      });
      router.replace({
        pathname: "/courier_home_page",
        params: { token: String(token) },
      });
    } catch (e: any) {
      Alert.alert("שגיאה", e?.message || "שמירת הפרטים נכשלה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ flex: 1, backgroundColor: COLORS.bg }}>
      <AnimatedBgBlobs />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.container,
          { flexGrow: 1, justifyContent: "center", alignItems: "center" },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.card}>
          <Text style={styles.title}>פרטי שליח/ה</Text>
          <Text style={styles.subtitle}>
            הפרטים עוזרים למודל לחזות בדיוק רב יותר כמה זמן ייקח לך משלוח.
          </Text>

          <View style={styles.field}>
            <Text style={styles.label}>גיל</Text>
            <TextInput
              style={styles.input}
              value={age}
              onChangeText={(t) => setAge(t.replace(/[^0-9]/g, ""))}
              keyboardType="number-pad"
              placeholder="לדוגמה: 27"
              textAlign="right"
              maxLength={2}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>סוג רכב</Text>
            <View style={styles.options}>
              {VEHICLES.map((v) => (
                <Option
                  key={v.key}
                  label={v.label}
                  active={vehicle === v.key}
                  onPress={() => setVehicle(v.key)}
                />
              ))}
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>מצב הרכב</Text>
            <View style={styles.options}>
              {CONDITIONS.map((c) => (
                <Option
                  key={c.key}
                  label={c.label}
                  active={condition === c.key}
                  onPress={() => setCondition(c.key)}
                />
              ))}
            </View>
          </View>

          <TouchableOpacity
            style={[styles.btn, { opacity: ok && !busy ? 1 : 0.6 }]}
            onPress={handleSave}
            disabled={busy}
          >
            <Text style={styles.btnText}>
              {busy ? "שומרת…" : "שמירה והמשך"}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

function Option({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.option, active && styles.optionActive]}
      activeOpacity={0.8}
    >
      <Text style={[styles.optionText, active && styles.optionTextActive]}>
        {label}
      </Text>
    </TouchableOpacity>
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
  field: { marginBottom: 14 },
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
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  option: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: "#fff",
  },
  optionActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  optionText: { color: COLORS.text, fontWeight: "600" },
  optionTextActive: { color: "#fff" },
  btn: {
    backgroundColor: COLORS.primary,
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: "center",
    marginTop: 4,
  },
  btnText: { color: "#fff", fontWeight: "800" },
});
