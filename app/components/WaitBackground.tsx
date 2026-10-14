// app/components/WaitBackground.tsx
import React from "react";
import { ImageBackground, View, StyleSheet } from "react-native";

export default function WaitBackground({
  children,
  imageUri, // חובה להעביר מבחוץ: require("...") או { uri: "..." }
  opacity = 0.6, // כמה "חזקה" התמונה (0..1). ↑ כדי לראות יותר את המפה.
  blurRadius = 2, // טשטוש עדין; אפשר 0 לראות שזה עובד ואז לעלות מעט.
  tintAlpha = 0, // הלבנה לבנה מעל (0..1). השארי 0 כדי לא "לשטוף" את התמונה.
  darken = 0.22, // הכהיה שחורה עדינה (0..1). נותנת קונטרסט לטקסט.
}: {
  children: React.ReactNode;
  imageUri?: any;
  opacity?: number;
  blurRadius?: number;
  tintAlpha?: number; // לבן
  darken?: number; // שחור
}) {
  const src = imageUri ?? {
    uri: "https://images.unsplash.com/photo-1465447142348-e9952c393450?q=80&w=1600&auto=format&fit=crop",
  };

  return (
    <View style={S.screen}>
      <ImageBackground
        source={src}
        resizeMode="cover"
        blurRadius={blurRadius}
        style={S.bg}
        imageStyle={{ opacity }}
      >
        {/* שכבת הכהיה (שחור) */}
        {darken > 0 && (
          <View
            pointerEvents="none"
            style={[S.overlay, { backgroundColor: `rgba(0,0,0,${darken})` }]}
          />
        )}
        {/* שכבת הלבנה (לבן) — אם ממש צריך */}
        {tintAlpha > 0 && (
          <View
            pointerEvents="none"
            style={[
              S.overlay,
              { backgroundColor: `rgba(255,255,255,${tintAlpha})` },
            ]}
          />
        )}
        <View style={S.content}>{children}</View>
      </ImageBackground>
    </View>
  );
}

const S = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#000" },
  bg: { flex: 1 },
  overlay: { ...StyleSheet.absoluteFillObject },
  content: {
    flex: 1,
    padding: 16,
    alignItems: "center",
    justifyContent: "center",
  },
});
