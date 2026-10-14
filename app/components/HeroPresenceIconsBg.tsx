import React, { useEffect, useRef } from "react";
import {
  Animated,
  Dimensions,
  Easing,
  StyleSheet,
  Text,
  View,
} from "react-native";

const { width, height } = Dimensions.get("window");

// צבעי מותג מודגשים אך עדינים (אפשר לחזק/להחליש)
const STRIP_SOFT = "rgba(155,172,112,0.28)"; // primarySoft
const STRIP_DARK = "rgba(71,85,48,0.22)"; // primaryDark
const HILITE = "rgba(255,255,255,0.18)";

function MovingEmoji({
  emoji,
  laneWidth,
  size = 24,
  duration = 8000,
  delay = 0,
}: {
  emoji: string;
  laneWidth: number;
  size?: number;
  duration?: number;
  delay?: number;
}) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(t, {
          toValue: 1,
          duration,
          easing: Easing.linear,
          useNativeDriver: true,
          delay,
        }),
        Animated.timing(t, { toValue: 0, duration: 0, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [t, duration, delay]);

  // נע לרוחב ה"ליין" (שהוא רחב יותר מהמסך, כדי להרגיש עומק)
  const tx = t.interpolate({
    inputRange: [0, 1],
    outputRange: [-laneWidth * 0.1, laneWidth * 1.1],
  });
  // ניעור עדין כדי לתת "חיים"
  const bob = t.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0, -6, 0],
  });

  return (
    <Animated.View
      style={[
        styles.iconWrap,
        { transform: [{ translateX: tx }, { translateY: bob }] },
      ]}
      pointerEvents="none"
    >
      <Text style={{ fontSize: size }}>{emoji}</Text>
    </Animated.View>
  );
}

function RunningHighlight({ laneWidth }: { laneWidth: number }) {
  const x = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(x, {
          toValue: 1,
          duration: 2600,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(x, { toValue: 0, duration: 0, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [x]);

  const tx = x.interpolate({
    inputRange: [0, 1],
    outputRange: [-laneWidth * 0.2, laneWidth * 0.2],
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.highlight,
        { transform: [{ translateX: tx }], width: laneWidth * 0.3 },
      ]}
    />
  );
}

function Lane({
  top,
  rotateDeg,
  color,
  thickness = 120,
  children,
  withHighlight = true,
}: {
  top: number;
  rotateDeg: number;
  color: string;
  thickness?: number;
  children?: React.ReactNode;
  withHighlight?: boolean;
}) {
  const laneWidth = width * 1.6; // רחב מהמסך לנוכחות
  return (
    <View
      pointerEvents="none"
      style={[
        styles.laneWrap,
        { top, left: -width * 0.3, transform: [{ rotate: `${rotateDeg}deg` }] },
      ]}
    >
      {/* פס הרקע העבה */}
      <View
        style={[
          styles.lane,
          { width: laneWidth, height: thickness, backgroundColor: color },
        ]}
      />
      {/* “ריצת אור” בתוך הפס */}
      {withHighlight && (
        <View
          style={[
            StyleSheet.absoluteFill,
            { alignItems: "center", justifyContent: "center" },
          ]}
        >
          <RunningHighlight laneWidth={laneWidth} />
        </View>
      )}
      {/* אייקונים נעים על הפס */}
      <View style={[StyleSheet.absoluteFill, { justifyContent: "center" }]}>
        <View style={{ position: "absolute", width: laneWidth, height: 0 }}>
          {children}
        </View>
      </View>
      {/* צל עדין להגברת עומק */}
      <View style={[styles.shadow, { width: laneWidth, height: thickness }]} />
    </View>
  );
}

export default function HeroPresenceIconsBg() {
  const laneW = width * 1.6;

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {/* ליין משלוחים (אלכסון עליון) */}
      <Lane
        top={height * 0.23}
        rotateDeg={-18}
        color={STRIP_SOFT}
        thickness={120}
      >
        <MovingEmoji emoji="📦" laneWidth={laneW} duration={8500} />
        <MovingEmoji
          emoji="📦"
          laneWidth={laneW}
          duration={9800}
          delay={600}
          size={22}
        />
        <MovingEmoji
          emoji="🚚"
          laneWidth={laneW}
          duration={11000}
          delay={1200}
          size={26}
        />
      </Lane>

      {/* ליין טרמפים/נסיעות (אלכסון תחתון) */}
      <Lane
        top={height * 0.68}
        rotateDeg={18}
        color={STRIP_DARK}
        thickness={90}
      >
        <MovingEmoji emoji="🚗" laneWidth={laneW} duration={7600} />
        <MovingEmoji
          emoji="🛵"
          laneWidth={laneW}
          duration={8200}
          delay={700}
          size={22}
        />
        <MovingEmoji
          emoji="🧍"
          laneWidth={laneW}
          duration={9000}
          delay={1400}
          size={20}
        />
      </Lane>
    </View>
  );
}

const styles = StyleSheet.create({
  laneWrap: { position: "absolute" },
  lane: {
    borderRadius: 999,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 6,
  },
  highlight: {
    height: 28,
    borderRadius: 999,
    backgroundColor: HILITE,
  },
  iconWrap: { position: "absolute", top: -14 },
  shadow: {
    position: "absolute",
    backgroundColor: "rgba(0,0,0,0.04)",
    borderRadius: 999,
    top: 10,
    left: 0,
  },
});
