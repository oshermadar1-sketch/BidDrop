// app/components/PasswordField.tsx
// Password input with a show/hide toggle and, when asked, the live list of rules
// (one tick per rule, like Google's sign-up form).
import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { authStyles as S, AUTH_COLORS } from "../ui/authStyles";
import { PASSWORD_RULES } from "../../lib/password";

export default function PasswordField({
  label,
  value,
  onChangeText,
  showRules,
  placeholder,
  onSubmit,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  showRules?: boolean;
  placeholder?: string;
  /** Called when the user presses Enter (web) or the keyboard's go key (phone). */
  onSubmit?: () => void;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <View style={S.field}>
      <Text style={S.label}>{label}</Text>
      <View style={S.inputRow}>
        <TextInput
          style={[S.input, { paddingLeft: 52 }]}
          value={value}
          onChangeText={onChangeText}
          secureTextEntry={!visible}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder={placeholder ?? "••••••••"}
          placeholderTextColor={AUTH_COLORS.dim}
          onSubmitEditing={onSubmit}
          returnKeyType={onSubmit ? "go" : "default"}
        />
        <TouchableOpacity
          style={S.eyeBtn}
          onPress={() => setVisible((v) => !v)}
          accessibilityRole="button"
          accessibilityLabel={visible ? "הסתרת הסיסמה" : "הצגת הסיסמה"}
        >
          <Text style={S.eyeText}>{visible ? "הסתרה" : "הצגה"}</Text>
        </TouchableOpacity>
      </View>

      {showRules && (
        <View style={S.rules}>
          {PASSWORD_RULES.map((r) => {
            const ok = r.ok(value);
            return (
              <View key={r.key} style={S.ruleRow}>
                <Ionicons
                  name={ok ? "checkmark-circle" : "ellipse-outline"}
                  size={16}
                  color={ok ? AUTH_COLORS.good : AUTH_COLORS.dim}
                />
                <Text style={[S.ruleText, { color: ok ? AUTH_COLORS.good : AUTH_COLORS.dim }]}>
                  {r.label}
                </Text>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}
