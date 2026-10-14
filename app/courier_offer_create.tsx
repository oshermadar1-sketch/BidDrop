// Courier - Create Availability Offer
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
import {
  createCourierOffer,
  runMatchingForOffer,
} from "../lib/api";
import {
  AddressAutocomplete,
  type PickedAddress,
} from "../components/AddressAutocomplete";
dayjs.locale("he");

const fmt = (d?: Date | null) => (d ? dayjs(d).format("DD.MM.YYYY HH:mm") : "");

export default function CourierOfferCreate() {
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();

  // טופס
  const [fromAddress, setFromAddress] = useState("");
  const [toAddress, setToAddress] = useState<string>("");
  // Exact coordinates when the user picked a suggestion (null = free text, server geocodes)
  const [fromPick, setFromPick] = useState<PickedAddress | null>(null);
  const [toPick, setToPick] = useState<PickedAddress | null>(null);
  const [anyDestination, setAnyDestination] = useState(false);

  const [startDT, setStartDT] = useState<Date | null>(null);
  const [endDT, setEndDT] = useState<Date | null>(null);

  const [minPrice, setMinPrice] = useState<string>("");
  const [types, setTypes] = useState<("package" | "passenger")[]>(["package"]);
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);

  // מודל תאריך/שעה
  const [dtOpen, setDtOpen] = useState(false);
  const [dtTarget, setDtTarget] = useState<"start" | "end">("start");
  const [tempDT, setTempDT] = useState<Date>(new Date());

  const מוכן =
    !!fromAddress.trim() &&
    (!!anyDestination || !!toAddress.trim()) &&
    !!startDT &&
    !!endDT &&
    Number(minPrice) > 0 &&
    types.length > 0;

  function החלףסוג(t: "package" | "passenger") {
    setTypes((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]
    );
  }

  function פתחתאריך(יעד: "start" | "end") {
    setDtTarget(יעד);
    setTempDT((יעד === "start" ? startDT : endDT) || new Date());
    setDtOpen(true);
  }
  function אשרתאריך() {
    if (dtTarget === "start") setStartDT(new Date(tempDT));
    else setEndDT(new Date(tempDT));
    setDtOpen(false);
  }

  async function שליחה() {
    if (!token) {
      Alert.alert("שגיאה", "אסימון התחברות חסר");
      return;
    }
    if (!מוכן) {
      Alert.alert("שימי לב", "מלאי את כל השדות החיוניים לפני פרסום ההצעה");
      return;
    }
    try {
      setSubmitting(true);
      const payload = {
        from_address: fromAddress.trim(),
        to_address: anyDestination ? null : toAddress.trim(),
        window_start: startDT!.toISOString(),
        window_end: endDT!.toISOString(),
        min_price: Number(minPrice),
        types,
        notes: notes.trim() || undefined,
        from_lat: fromPick?.lat ?? null,
        from_lon: fromPick?.lon ?? null,
        to_lat: anyDestination ? null : (toPick?.lat ?? null),
        to_lon: anyDestination ? null : (toPick?.lon ?? null),
      };
      const { id: createdOfferId } = await createCourierOffer(
        String(token),
        payload
      );
      
      try {
        await runMatchingForOffer(String(token), createdOfferId);
      } catch (e) {
      console.log("Immediate offer matching failed", e);
      }
      
      Alert.alert("בוצע", "הצעת השליח פורסמה בהצלחה");
      router.replace({
        pathname: "/matching-await-driver",
        params: { offerId: createdOfferId, token },
      });
    } catch (e: any) {
      Alert.alert("שגיאה", e?.message || "יצירת הצעת שליח נכשלה");
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

  // צעדים
  const שלב1 = !!fromAddress && (anyDestination || !!toAddress);
  const שלב2 = !!(startDT && endDT);
  const שלב3 = Number(minPrice) > 0 && types.length > 0;

  return (
    <LinearGradient
      colors={[COLORS.green1, COLORS.green2, COLORS.green3, COLORS.green4]}
      start={{ x: 1, y: 0 }}
      end={{ x: 0, y: 1 }}
      style={{ flex: 1 }}
    >
      <SafeAreaView style={S.safe}>
        <Header
          title="הצעת שליח חדשה"
          subtitle="אזור וזמן • סוגי משימות • מחיר מינימלי"
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
              <Text style={S.label}>נקודת מוצא *</Text>
              <AddressAutocomplete
                inputStyle={S.input}
                placeholder="התחילי להקליד, לדוגמה: דרך השלום 10, תל אביב"
                value={fromAddress}
                onChangeText={(t) => {
                  setFromAddress(t);
                  setFromPick(null);
                }}
                onPick={setFromPick}
              />
            </View>

            <View style={[S.row2, { marginBottom: 8 }]}>
              <TouchableOpacity
                style={[S.segmentBtn, anyDestination && S.segmentBtnActive]}
                onPress={() => setAnyDestination(true)}
                activeOpacity={0.8}
              >
                <Text
                  style={[S.segmentTxt, anyDestination && S.segmentTxtActive]}
                >
                  פתוח לכל יעד
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[S.segmentBtn, !anyDestination && S.segmentBtnActive]}
                onPress={() => setAnyDestination(false)}
                activeOpacity={0.8}
              >
                <Text
                  style={[S.segmentTxt, !anyDestination && S.segmentTxtActive]}
                >
                  יעד ספציפי
                </Text>
              </TouchableOpacity>
            </View>

            {!anyDestination && (
              <View style={S.field}>
                <Text style={S.label}>יעד *</Text>
                <AddressAutocomplete
                  inputStyle={S.input}
                  placeholder="התחילי להקליד, לדוגמה: חיפה"
                  value={toAddress}
                  onChangeText={(t) => {
                    setToAddress(t);
                    setToPick(null);
                  }}
                  onPick={setToPick}
                />
              </View>
            )}
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
                  {startDT ? fmt(startDT) : "בחרו תאריך ושעה"}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={S.pickerBtn}
                onPress={() => פתחתאריך("end")}
              >
                <Text style={S.pickerLabel}>סיום *</Text>
                <Text style={S.pickerValue}>
                  {endDT ? fmt(endDT) : "בחרו תאריך ושעה"}
                </Text>
              </TouchableOpacity>
            </View>
            <Text style={S.hint}>
              טיפ: חלון רחב מגדיל התאמות עם בקשות פתוחות.
            </Text>
          </View>

          {/* סוגי משימות ומחיר */}
          <View style={S.card}>
            <Text style={S.cardTitle}>סוגי משימות ומחיר</Text>

            <Text style={S.label}>אני מעוניין לבצע *</Text>
            <View style={[S.row2, { marginTop: 8 }]}>
              <TouchableOpacity
                style={[
                  S.segmentBtn,
                  types.includes("package") && S.segmentBtnActive,
                ]}
                onPress={() => החלףסוג("package")}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    S.segmentTxt,
                    types.includes("package") && S.segmentTxtActive,
                  ]}
                >
                  חבילות
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[
                  S.segmentBtn,
                  types.includes("passenger") && S.segmentBtnActive,
                ]}
                onPress={() => החלףסוג("passenger")}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    S.segmentTxt,
                    types.includes("passenger") && S.segmentTxtActive,
                  ]}
                >
                  טרמפיסטים
                </Text>
              </TouchableOpacity>
            </View>

            <View style={[S.field, { marginTop: 10 }]}>
              <Text style={S.label}>מחיר מינימלי (₪) *</Text>
              <TextInput
                style={S.input}
                placeholder="לדוגמה: 30"
                keyboardType="numeric"
                value={minPrice}
                onChangeText={setMinPrice}
                textAlign="right"
              />
              <Text style={S.hint}>זהו המחיר המינימלי לנסיעה/משלוח.</Text>
            </View>
          </View>

          {/* הערות */}
          <View style={S.card}>
            <Text style={S.cardTitle}>הערות (אופציונלי)</Text>
            <View style={S.field}>
              <TextInput
                style={[S.input, { height: 100, textAlignVertical: "top" }]}
                placeholder="פרטים רלוונטיים (ציוד, זמנים, העדפות...)"
                value={notes}
                onChangeText={setNotes}
                multiline
                textAlign="right"
              />
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
            <Text style={S.bottomBarText}>פרסום הצעת שליח</Text>
          )}
        </TouchableOpacity>

        <Modal
          isVisible={dtOpen}
          onBackdropPress={() => setDtOpen(false)}
          onBackButtonPress={() => setDtOpen(false)}
          style={{ justifyContent: "flex-end", margin: 0 }}
        >
          <View style={S.modalSheet}>
            <Text style={S.modalTitle}>
              {dtTarget === "start"
                ? "בחרו תאריך ושעה - התחלה"
                : "בחרו תאריך ושעה - סיום"}
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
                onPress={() => setDtOpen(false)}
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

  segmentBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: "center",
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "rgba(0,0,0,0.08)",
  },
  segmentBtnActive: { backgroundColor: COLORS.primary },
  segmentTxt: { color: COLORS.primaryDark, fontWeight: "800" },
  segmentTxtActive: { color: "#fff" },

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
