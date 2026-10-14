// app/_components/BoxIllustration.tsx
import React from "react";
import Svg, { Rect, Polygon, Path } from "react-native-svg";

export default function BoxIllustration({
  width = 160,
  height = 110,
  tone = "mocha",
}: {
  width?: number;
  height?: number;
  tone?: "mocha" | "primary";
}) {
  const tape = tone === "mocha" ? "#7B8B52" : "#6E7F43";
  const face = tone === "mocha" ? "#CFA07C" : "#C8D39B";
  const side = tone === "mocha" ? "#B78259" : "#B6C47E";
  return (
    <Svg width={width} height={height} viewBox="0 0 240 160">
      <Rect
        x="8"
        y="16"
        width="224"
        height="128"
        rx="22"
        fill="#000"
        opacity="0.05"
      />
      <Polygon points="40,110 120,70 200,110 120,150" fill={side} />
      <Polygon points="40,50 120,10 200,50 120,90" fill={face} />
      <Path d="M120 10 L120 90" stroke={tape} strokeWidth="10" />
      <Path d="M120 70 L200 110" stroke={tape} strokeWidth="10" />
    </Svg>
  );
}
