// app/components/Hourglass.tsx
import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, Text } from "react-native";

export default function Hourglass({ size = 64 }: { size?: number }) {
  const [face, setFace] = useState<"full" | "flow">("flow"); // ⌛ / ⏳
  const spin = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const tick = setInterval(() => {
      setFace((f) => (f === "flow" ? "full" : "flow"));
      spin.setValue(0);
      Animated.timing(spin, {
        toValue: 1,
        duration: 500,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
    }, 800);
    return () => clearInterval(tick);
  }, []);

  const rotate = spin.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "180deg"],
  });

  return (
    <Animated.View style={{ transform: [{ rotate }], alignItems: "center" }}>
      <Text style={{ fontSize: size }}>{face === "flow" ? "⏳" : "⌛"}</Text>
    </Animated.View>
  );
}
