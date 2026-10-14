// Rider - Create Ride Request
// Visuals: mocha cards + CTA identical to home button

import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ScrollView,
  ActivityIndicator,
  SafeAreaView,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import Modal from "react-native-modal";
import UIDatePicker, { useDefaultStyles } from "react-native-ui-datepicker";
import { LinearGradient } from "expo-linear-gradient";
import dayjs from "dayjs";
import "dayjs/locale/he";

import { Header } from "./components/Primitives";
import { COLORS } from "./ui/theme";
import { createRiderRequest, type CreateRiderPayload } from "../lib/api";
import {
  AddressAutocomplete,
  type PickedAddress,
} from "../components/AddressAutocomplete";

dayjs.locale("he");

const fmt = (d?: Date | null) => (d ? dayjs(d).format("DD.MM.YYYY HH:mm") : "");

// נסיון לחלץ מזהה בקשה ממבני תשובה שונים
function pickRequestId(res: any): string | null {
  if (!res) return null;
  if (typeof res === "string") return res;
  if (res?.id != null) return String(res.id);
  if (res?.request_id != null) return String(res.request_id);
  if (res?.requestId != null) return String(res.requestId);
  if (res?.data?.id != null) return String(res.data.id);
  if (res?.data?.request_id != null) return String(res.data.request_id);
  return null;
}

export default function RiderRequestCreate() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  // טופס
  const [fromAddress, setFromAddress] = useState("");
  const [toAddress, setToAddress] = useState("");
  // Exact coordinates when the user picked a suggestion (null = free text, server geocodes)
  const [fromPick, setFromPick] = useState<PickedAddress | null>(null);
  const [toPick, setToPick] = useState<PickedAddress | null>(null);
  const [startDT, setStartDT] = useState<Date | null>(null);
  const [endDT, setEndDT] = useState<Date | null>(null);
  const [seats, setSeats] = useState<string>("1");
  const [notes, setNotes] = useState("");
  const [maxPrice, setMaxPrice] = useState<string>("");

  // מודל תאריך/שעה
  const [dtModalOpen, setDtModalOpen] = useState(false);
  const [dtTarget, setDtTarget] = useState<"start" | "end">("start");
  const [tempDT, setTempDT] = useState<Date>(new Date());

  const [submitting, setSubmitting] = useState(false);

  const seatsNum = Math.max(1, Number.isFinite(+seats) ? +seats : 0);
  const מוכן =
    !!fromAddress.trim() &&
    !!toAddress.trim() &&
    !!startDT &&
    !!endDT &&
    seatsNum >= 1 &&
    Number(maxPrice) > 0;

  function פתחתאריך(יעד: "start" | "end") {
    setDtTarget(יעד);
    setTempDT((יעד === "start" ? startDT : endDT) || new Date());
    setDtModalOpen(true);
  }
  function אשרתאריך() {
    if (dtTarget === "start") setStartDT(new Date(tempDT));
    else setEndDT(new Date(tempDT));
    setDtModalOpen(false);
  }

  async function שליחה() {
    if (!token) {
      Alert.alert("שגיאה", "אסימון התחברות חסר");
      return;
    }
    if (!מוכן) {
      Alert.alert("שימי לב", "מלאי את כל השדות החיוניים לפני פרסום הבקשה");
      return;
    }
    try {
      setSubmitting(true);
      const payload: CreateRiderPayload = {
        from_address: fromAddress.trim(),
        to_address: toAddress.trim(),
        window_start: startDT!.toISOString(),
        window_end: endDT!.toISOString(),
        passengers: seatsNum,
        notes: notes.trim() || null,
        max_price: Number(maxPrice),
        from_lat: fromPick?.lat ?? null,
        from_lon: fromPick?.lon ?? null,
        to_lat: toPick?.lat ?? null,
        to_lon: toPick?.lon ?? null,
      };

      const res = await createRiderRequest(String(token), payload);
      const requestId = pickRequestId(res);
      if (!requestId) {
        Alert.alert("בקשה נשמרה", "לא קיבלנו מזהה בקשה. חוזרים לדף הבית.");
        router.replace({ pathname: "/rider_home_page", params: { token } });
        return;
      }
      router.replace({
        pathname: "/matching-await",
        params: { requestId, token, role: "rider" },
      });
    } catch (e: any) {
      Alert.alert("שגיאה", e?.message || "יצירת בקשת טרמפ נכשלה");
    } finally {
      setSubmitting(false);
    }
  }

  // עיצוב רכיב בחירת תאריך
  const dpBase = useDefaultStyles();
  const dpStyles = {
    ...dpBase,
    selected: { backgroundColor: COLORS.primary, borderRadius: 8 },
    selected_label: { color: "#fff", fontWeight: "900" },
    today: { borderColor: COLORS.primary, borderWidth: 1, borderRadius: 8 },
  } as const;

  // מצב צעדים
  const שלב1 = !!(fromAddress.trim() && toAddress.trim());
  const שלב2 = !!(startDT && endDT);
  const שלב3 = Number(maxPrice) > 0 && seatsNum >= 1;

  return (
    <LinearGradient
      colors={[COLORS.green1, COLORS.green2, COLORS.green3, COLORS.green4]}
      start={{ x: 1, y: 0 }}
      end={{ x: 0, y: 1 }}
      style={{ flex: 1 }}
    >
      <SafeAreaView style={S.safe}>
        <Header
          title="בקשת טרמפ חדשה"
          subtitle="פרטי נסיעה • זמנים וכתובות • תקציב ואישור"
        />

        <View style={S.stepbar}>
          {[
            { label: "פרטים", done: שלב1 },
            { label: "זמנים", done: שלב2 },
            { label: "אישור", done: שלב3 },
          ].map((s, i) => (
            <View style={S.stepItem} key={s.label}>
              <View style={[S.stepCircle, s.done && S.stepCircleDone]}>
                <Text style={[S.stepIndex, s.done && S.stepIndexDone]}>
                  {i + 1}
                </Text>
              </View>
              <Text style={S.stepLabel}>{s.label}</Text>
              {i < 2 && (
                <View
                  style={[
                    S.stepDivider,
                    (i === 0 ? שלב1 : שלב2) && S.stepDividerDone,
                  ]}
                />
              )}
            </View>
          ))}
        </View>

        <ScrollView contentContainerStyle={{ paddingBottom: 160 }}>
          {/* כתובות */}
          <View style={S.card}>
            <Text style={S.cardTitle}>כתובות</Text>
            <View style={S.field}>
              <Text style={S.label}>נקודת יציאה *</Text>
<AddressAutocomplete
                inputStyle={S.input}
                placeholder="התחילי להקליד, לדוגמה: בן גוריון 10, תל אביב"
                value={fromAddress}
                onChangeText={(t) => {
                  setFromAddress(t);
                  setFromPick(null);
                }}
                onPick={setFromPick}
              />
            </View>
            <View style={S.field}>
              <Text style={S.label}>יעד *</Text>
<AddressAutocomplete
                inputStyle={S.input}
                placeholder="התחילי להקליד, לדוגמה: הרצל 5, ראשון לציון"
                value={toAddress}
                onChangeText={(t) => {
                  setToAddress(t);
                  setToPick(null);
                }}
                onPick={setToPick}
              />
            </View>
          </View>

          {/* חלון זמן */}
          <View style={S.card}>
            <Text style={S.cardTitle}>חלון זמן</Text>
            <View style={S.row2}>
              <TouchableOpacity
                style={S.pickerBtn}
                onPress={() => פתחתאריך("start")}
              >
                <Text style={S.pickerLabel}>התחלה *</Text>
                <Text style={S.pickerValue}>
                  {startDT ? fmt(startDT) : "בחרי תאריך ושעה"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={S.pickerBtn}
                onPress={() => פתחתאריך("end")}
              >
                <Text style={S.pickerLabel}>סיום *</Text>
                <Text style={S.pickerValue}>
                  {endDT ? fmt(endDT) : "בחרי תאריך ושעה"}
                </Text>
              </TouchableOpacity>
            </View>
            <Text style={S.hint}>טיפ: חלון רחב מגדיל סיכוי להתאמה מהירה.</Text>
          </View>

          {/* נוסעים */}
          <View style={S.card}>
            <Text style={S.cardTitle}>נוסעים</Text>
            <View style={S.field}>
              <Text style={S.label}>מספר נוסעים *</Text>
              <TextInput
                style={S.input}
                placeholder="1"
                keyboardType="numeric"
                value={seats}
                onChangeText={setSeats}
                textAlign="right"
              />
              <Text style={S.hint}>
                מינימום 1. הזיני את מספר המקומות הנדרש.
              </Text>
            </View>
          </View>

          {/* פרטים נוספים */}
          <View style={S.card}>
            <Text style={S.cardTitle}>פרטים נוספים</Text>
            <View style={S.field}>
              <Text style={S.label}>הערות (אופציונלי)</Text>
              <TextInput
                style={[S.input, { height: 100, textAlignVertical: "top" }]}
                placeholder="עם כלב / ציוד / העדפות מיוחדות..."
                multiline
                value={notes}
                onChangeText={setNotes}
                textAlign="right"
              />
            </View>
          </View>

          {/* תקציב */}
          <View style={S.card}>
            <Text style={S.cardTitle}>תקציב</Text>
            <View style={S.field}>
              <Text style={S.label}>תקציב מקסימלי (₪) *</Text>
              <TextInput
                style={S.input}
                placeholder="לדוגמה: 40"
                keyboardType="numeric"
                value={maxPrice}
                onChangeText={setMaxPrice}
                textAlign="right"
              />
              <Text style={S.hint}>
                זהו הסכום המקסימלי שאת/ה מוכנ/ה לשלם על הטרמפ.
              </Text>
            </View>
          </View>
        </ScrollView>

        <TouchableOpacity
          style={[S.bottomBar, !מוכן || submitting ? { opacity: 0.6 } : null]}
          activeOpacity={0.9}
          onPress={שליחה}
          disabled={!מוכן || submitting}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={S.bottomBarText}>פרסום בקשה</Text>
          )}
        </TouchableOpacity>

        <Modal
          isVisible={dtModalOpen}
          onBackdropPress={() => setDtModalOpen(false)}
          onBackButtonPress={() => setDtModalOpen(false)}
          style={{ justifyContent: "flex-end", margin: 0 }}
        >
          <View style={S.modalSheet}>
            <Text style={S.modalTitle}>
              {dtTarget === "start"
                ? "בחרי תאריך ושעה - התחלה"
                : "בחרי תאריך ושעה - סיום"}
            </Text>
            <UIDatePicker
              mode="single"
              date={tempDT}
              onChange={(p: any) => p?.date && setTempDT(p.date)}
              timePicker
              locale="he"
              firstDayOfWeek={0}
              navigationPosition="around"
              styles={dpStyles}
            />
            <View style={S.modalRow}>
              <TouchableOpacity
                style={[S.modalBtn, S.modalCancel]}
                onPress={() => setDtModalOpen(false)}
              >
                <Text style={[S.modalBtnTxt, S.modalCancelTxt]}>ביטול</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[S.modalBtn, S.modalConfirm]}
                onPress={אשרתאריך}
              >
                <Text style={[S.modalBtnTxt, S.modalConfirmTxt]}>אישור</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
    </LinearGradient>
  );
}

const S = StyleSheet.create({
  safe: { flex: 1, paddingHorizontal: 16, paddingTop: 45 },

  stepbar: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 6,
    marginBottom: 12,
  },
  stepItem: { flexDirection: "row", alignItems: "center", flex: 1 },
  stepCircle: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: COLORS.primary,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
  },
  stepCircleDone: { backgroundColor: COLORS.primary },
  stepIndex: { color: COLORS.primary, fontWeight: "900" },
  stepIndexDone: { color: "#fff" },
  stepLabel: { marginHorizontal: 6, color: COLORS.text, fontWeight: "800" },
  stepDivider: {
    flex: 1,
    height: 2,
    backgroundColor: COLORS.border,
    marginHorizontal: 6,
    borderRadius: 2,
  },
  stepDividerDone: { backgroundColor: COLORS.primary },

  card: {
    backgroundColor: COLORS.softMocha,
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    borderWidth: 0,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  cardTitle: {
    fontWeight: "900",
    color: COLORS.primaryDark,
    marginBottom: 8,
    textAlign: "left",
  },

  field: { marginBottom: 10 },
  label: { fontWeight: "800", color: COLORS.text, textAlign: "left" },
  input: {
    marginTop: 6,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(0,0,0,0.08)",
    paddingVertical: 12,
    paddingHorizontal: 12,
    color: COLORS.text,
  },
  hint: { marginTop: 6, color: COLORS.dim, textAlign: "left" },

  row2: { flexDirection: "row-reverse", gap: 10 },
  pickerBtn: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(0,0,0,0.08)",
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  pickerLabel: { color: COLORS.dim, fontWeight: "700", textAlign: "left" },
  pickerValue: {
    marginTop: 4,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "right",
  },

  bottomBar: {
    position: "absolute",
    left: 16,
    right: 16,
    bottom: 18,
    height: 54,
    backgroundColor: COLORS.primary,
    borderRadius: 28,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  bottomBarText: { color: "#fff", fontWeight: "900", fontSize: 16 },

  modalSheet: {
    backgroundColor: "#fff",
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    padding: 16,
  },
  modalTitle: {
    fontWeight: "900",
    fontSize: 16,
    textAlign: "center",
    color: COLORS.primaryDark,
    marginBottom: 8,
  },
  modalRow: { flexDirection: "row-reverse", gap: 12, marginTop: 8 },
  modalBtn: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
  },
  modalCancel: { backgroundColor: "#F3F3F3" },
  modalConfirm: { backgroundColor: COLORS.primary },
  modalBtnTxt: { fontWeight: "900" },
  modalCancelTxt: { color: COLORS.text },
  modalConfirmTxt: { color: "#fff" },
});
