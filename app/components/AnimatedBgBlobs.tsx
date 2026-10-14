// app/components/AnimatedBgBlobs.tsx
import React, { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, View } from "react-native";

// צבעי המותג בגווני שקיפות עדינים
const C1 = "rgba(155, 172, 112, 0.25)"; // primarySoft
const C2 = "rgba(71, 85, 48, 0.18)"; // primaryDark
const C3 = "rgba(155, 172, 112, 0.15)";

function Blob({
  size,
  color,
  duration = 6500,
  delay = 0,
  style,
}: {
  size: number;
  color: string;
  duration?: number;
  delay?: number;
  style?: any;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(t, {
          toValue: 1,
          duration,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
          delay,
        }),
        Animated.timing(t, {
          toValue: 0,
          duration,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [t, duration, delay]);

  const translateY = t.interpolate({
    inputRange: [0, 1],
    outputRange: [-16, 16],
  });
  const translateX = t.interpolate({
    inputRange: [0, 1],
    outputRange: [8, -8],
  });
  const rotate = t.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "18deg"],
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.blob,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: color,
          transform: [{ translateY }, { translateX }, { rotate }],
        },
        style,
      ]}
    />
  );
}

export default function AnimatedBgBlobs() {
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {/* שלוש צורות גדולות זזות לאט ליצירת עומק "חי" ועדין */}
      <Blob
        size={340}
        color={C1}
        duration={7000}
        style={{ top: -70, left: -40 }}
      />
      <Blob
        size={300}
        color={C2}
        duration={8000}
        delay={600}
        style={{ top: 20, right: -60 }}
      />
      <Blob
        size={280}
        color={C3}
        duration={9000}
        delay={1200}
        style={{ bottom: -80, left: -20 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  blob: {
    position: "absolute",
  },
});
