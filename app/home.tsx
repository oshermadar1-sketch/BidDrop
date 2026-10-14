import React, { useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Modal,
  Pressable,
  Linking,
  I18nManager,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import AnimatedBgBlobs from "./components/AnimatedBgBlobs";

I18nManager.allowRTL(true);

const COLORS = {
  bg: "#ffffff",
  primary: "#475530",
  primarySoft: "#9bac70",
  text: "#060606",
  textDim: "#6b7280",
  border: "#e5e7eb",
};

export default function HomeScreen() {
  const router = useRouter();
  const [helpVisible, setHelpVisible] = useState(false);

  return (
    <SafeAreaView style={styles.safe}>
      {/* Dynamic background */}
      <AnimatedBgBlobs />

      {/* Centered content wrapper */}
      <View style={styles.centerWrap}>
        <Text style={styles.title}>ברוכ/ה הבאה ל-BidDrop</Text>
        <Text style={styles.subtitle}>
          כדי להמשיך נדרש זיהוי מאובטח באמצעות ארנק SubWallet.
        </Text>

        <TouchableOpacity
          style={[styles.buttonPrimary, { marginTop: 10 }]}
          onPress={() => router.push("/wallet-login")}
          accessibilityRole="button"
          accessibilityLabel="התחברות או הרשמה עם SubWallet"
          testID="btn-connect-subwallet"
        >
          <Text
            style={styles.buttonPrimaryText}
            numberOfLines={1} // keep on a single line
            adjustsFontSizeToFit // auto-shrink to fit width
            minimumFontScale={0.9} // do not shrink below 90%
            allowFontScaling // respect OS accessibility
            maxFontSizeMultiplier={1.2} // cap extreme system font sizes
          >
            התחברות / הרשמה עם SubWallet
          </Text>
        </TouchableOpacity>

        {/* Help trigger */}
        <Pressable
          onPress={() => setHelpVisible(true)}
          style={{ marginTop: 18 }}
        >
          <Text style={styles.helpText}>אין לך ארנק? צריך/ה עזרה בהתחברות</Text>
        </Pressable>
      </View>

      {/* Help modal */}
      <Modal
        visible={helpVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setHelpVisible(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>איך מתחברים עם SubWallet?</Text>
            <Text style={styles.modalBody}>
              התקיני את SubWallet. במסך הבא נפתח את הארנק; אם לא — תוכלי לסרוק
              QR.
            </Text>

            <View style={styles.linkList}>
              <Pressable
                onPress={() => Linking.openURL("https://www.subwallet.app")}
              >
                <Text style={styles.modalLink}>הורדת SubWallet</Text>
              </Pressable>
              <Pressable
                onPress={() => Linking.openURL("https://support.subwallet.app")}
              >
                <Text style={styles.modalLink}>מדריכים ותמיכה – SubWallet</Text>
              </Pressable>
              <Text style={styles.noteText}>
                {Platform.OS === "web"
                  ? "טיפ: אם התוסף לא מזוהה, רענני את הדף לאחר ההתקנה."
                  : "טיפ: במובייל נפתח את SubWallet; אם לא — סרקי QR."}
              </Text>
            </View>

            <TouchableOpacity
              style={styles.buttonSecondary}
              onPress={() => setHelpVisible(false)}
            >
              <Text style={styles.buttonSecondaryText}>סגירה</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },

  // Fully centered content (no dead space below)
  centerWrap: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 22,
  },

  title: {
    fontSize: 26,
    fontWeight: "800",
    color: COLORS.text,
    textAlign: "center",
    writingDirection: "rtl",
  },
  subtitle: {
    fontSize: 14,
    color: COLORS.textDim,
    textAlign: "center",
    marginTop: 8,
    marginBottom: 18,
    lineHeight: 20,
    writingDirection: "rtl",
  },

  buttonPrimary: {
    backgroundColor: COLORS.primarySoft,
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderRadius: 16,
    width: "90%",
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  buttonPrimaryText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
    textAlign: "center",
    writingDirection: "rtl",
    includeFontPadding: false, // Android: avoids extra top/bottom space
    textAlignVertical: "center",
  },

  // Small help link below the button
  helpText: {
    color: COLORS.primary,
    fontSize: 13,
    textDecorationLine: "underline",
  },

  // modal
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.35)",
    alignItems: "center",
    justifyContent: "center",
    padding: 18,
  },
  modalCard: {
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 16,
    padding: 18,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: COLORS.text,
    marginBottom: 8,
    textAlign: "center",
  },
  modalBody: {
    fontSize: 14,
    color: COLORS.textDim,
    lineHeight: 20,
    textAlign: "center",
    writingDirection: "rtl",
  },
  linkList: { marginTop: 12, gap: 8 },
  modalLink: {
    fontSize: 15,
    color: COLORS.primary,
    textDecorationLine: "underline",
    marginVertical: 4,
    textAlign: "center",
  },
  noteText: {
    marginTop: 8,
    fontSize: 12,
    color: COLORS.textDim,
    textAlign: "center",
  },
  buttonSecondary: {
    marginTop: 16,
    backgroundColor: "#fff",
    borderWidth: 2,
    borderColor: COLORS.primary,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
  },
  buttonSecondaryText: {
    color: COLORS.primary,
    fontSize: 15,
    fontWeight: "700",
  },
});
