// A "back" control for inner screens. Every screen is opened with router.replace,
// so there is often no history to go back to; in that case it returns to the home
// page of the current role (or to the role screen when the role is unknown).
import React from "react";
import { Pressable, Text, StyleSheet, Platform, ViewStyle } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type Home = "sender" | "rider" | "courier" | "role";

const HOME_PATH: Record<Home, string> = {
  sender: "/sender_home_page",
  rider: "/rider_home_page",
  courier: "/courier_home_page",
  role: "/role_select",
};

function homeFromParam(value?: string): Home {
  if (value === "sender" || value === "rider") return value;
  if (value === "driver" || value === "courier") return "courier";
  return "role";
}

type Props = {
  /** Where to go when there is no history; derived from the role/mode params when omitted. */
  home?: Home;
  /** Render in the flow (for a navigation header) instead of floating at the top corner. */
  inline?: boolean;
  style?: ViewStyle;
};

export default function BackButton({ home, inline, style }: Props) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { token, role, mode } = useLocalSearchParams<{
    token?: string;
    role?: string;
    mode?: string;
  }>();

  const goBack = () => {
    if (router.canGoBack()) {
      router.back();
      return;
    }
    const target = home ?? homeFromParam(role ?? mode);
    router.replace({
      pathname: HOME_PATH[target] as any,
      params: token ? { token: String(token) } : {},
    });
  };

  return (
    <Pressable
      onPress={goBack}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel="חזרה"
      style={({ pressed }) => [
        S.btn,
        inline ? S.inline : [S.floating, { top: insets.top + 10 }],
        pressed && { opacity: 0.7 },
        style,
      ]}
    >
      <Ionicons name="arrow-back" size={18} color="#2b2b2b" />
      <Text style={S.txt}>חזרה</Text>
    </Pressable>
  );
}

const S = StyleSheet.create({
  btn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.92)",
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.08)",
  },
  floating: {
    position: "absolute",
    left: 12,
    zIndex: 100,
    elevation: 6,
    ...Platform.select({
      web: { boxShadow: "0 2px 8px rgba(0,0,0,0.12)" } as any,
      default: {
        shadowColor: "#000",
        shadowOpacity: 0.12,
        shadowRadius: 6,
        shadowOffset: { width: 0, height: 2 },
      },
    }),
  },
  inline: { marginHorizontal: 8 },
  txt: { fontSize: 14, fontWeight: "700", color: "#2b2b2b" },
});
