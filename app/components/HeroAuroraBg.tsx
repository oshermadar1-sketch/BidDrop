// app/components/HeroAuroraBg.tsx
import React, { useEffect } from "react";
import {
  Canvas,
  Group,
  Rect,
  Circle,
  LinearGradient,
  RadialGradient,
  Blur,
  vec,
} from "@shopify/react-native-skia";
import { Dimensions, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useDerivedValue,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";

const { width: W, height: H } = Dimensions.get("window");

// צבעי המותג
const STRIP_SOFT = "rgba(155,172,112,0.28)";
const STRIP_DARK = "rgba(71,85,48,0.20)";

export default function HeroAuroraBg() {
  // t רץ קדימה-אחורה 0→1→0 בלולאה
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withRepeat(
      withTiming(1, { duration: 6000, easing: Easing.linear }),
      -1 /*infinite*/,
      true /*reverse*/
    );
  }, [t]);

  // היסט פסי המסלול
  const stripeShift = useDerivedValue(
    () => Math.sin(t.value * Math.PI * 2) * 60
  );

  // “ענני” אורורה זזים לאט
  const p1x = useDerivedValue(
    () => W * 0.22 + Math.sin(t.value * 2.2 * Math.PI) * 40
  );
  const p1y = H * 0.25;
  const p2x = useDerivedValue(
    () => W * 0.78 + Math.sin(t.value * 2.0 * Math.PI + Math.PI / 3) * 50
  );
  const p2y = H * 0.36;
  const p3x = useDerivedValue(
    () => W * 0.5 + Math.sin(t.value * 1.6 * Math.PI + Math.PI / 5) * 70
  );
  const p3y = H * 0.74;

  return (
    <Canvas style={StyleSheet.absoluteFill}>
      {/* רקע לבן נקי */}
      <Rect x={0} y={0} width={W} height={H} color="#ffffff" />

      {/* פס עליון עבה + היילייט נע */}
      <Group
        transform={[
          { translateX: -W * 0.25 },
          { translateY: H * 0.18 },
          { rotate: -0.32 },
        ]}
      >
        <Rect x={0} y={0} width={W * 1.5} height={120} color={STRIP_SOFT} />
        <Group
          transform={[{ translateX: stripeShift.value /* Reanimated value */ }]}
        >
          <Rect x={W * 0.2} y={18} width={W * 0.35} height={84} opacity={0.22}>
            <LinearGradient
              start={vec(0, 0)}
              end={vec(W * 0.35, 0)}
              colors={[
                "rgba(255,255,255,0)",
                "rgba(255,255,255,0.35)",
                "rgba(255,255,255,0)",
              ]}
            />
          </Rect>
        </Group>
        <Blur blur={6} />
      </Group>

      {/* פס תחתון עבה + היילייט נע הפוך */}
      <Group
        transform={[
          { translateX: -W * 0.25 },
          { translateY: H * 0.65 },
          { rotate: 0.3 },
        ]}
      >
        <Rect x={0} y={0} width={W * 1.5} height={95} color={STRIP_DARK} />
        <Group transform={[{ translateX: -stripeShift.value }]}>
          <Rect x={W * 0.35} y={14} width={W * 0.34} height={62} opacity={0.2}>
            <LinearGradient
              start={vec(0, 0)}
              end={vec(W * 0.34, 0)}
              colors={[
                "rgba(255,255,255,0)",
                "rgba(255,255,255,0.28)",
                "rgba(255,255,255,0)",
              ]}
            />
          </Rect>
        </Group>
        <Blur blur={5} />
      </Group>

      {/* "ענני" אורורה — משתמשים ב־cx/cy כדי להעביר ערכים נגזרים */}
      <Group>
        <Circle cx={p1x} cy={p1y} r={180}>
          <RadialGradient
            c={vec(0, 0)} // המרכז של הגרדיאנט בתוך האלמנט; לא חייב להיות מונפש
            r={220}
            colors={[
              "rgba(155,172,112,0.35)",
              "rgba(155,172,112,0.18)",
              "rgba(155,172,112,0.0)",
            ]}
          />
        </Circle>
        <Circle cx={p2x} cy={p2y} r={160}>
          <RadialGradient
            c={vec(0, 0)}
            r={200}
            colors={[
              "rgba(71,85,48,0.35)",
              "rgba(71,85,48,0.16)",
              "rgba(71,85,48,0.0)",
            ]}
          />
        </Circle>
        <Circle cx={p3x} cy={p3y} r={220}>
          <RadialGradient
            c={vec(0, 0)}
            r={280}
            colors={[
              "rgba(155,172,112,0.30)",
              "rgba(155,172,112,0.14)",
              "rgba(155,172,112,0.0)",
            ]}
          />
        </Circle>
        <Blur blur={18} />
      </Group>
    </Canvas>
  );
}
