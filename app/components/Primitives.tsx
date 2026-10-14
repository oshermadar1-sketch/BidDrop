// app/_components/Primitives.tsx
import React from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ViewStyle,
} from "react-native";
import { COLORS, RAD, SHADOW } from "../ui/theme";
import BoxIllustration from "./BoxIllustration";

export function Header({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <View style={S.header}>
      <View style={{ flex: 1 }}>
        <Text style={S.hTitle}>{title}</Text>
        {!!subtitle && <Text style={S.hSub}>{subtitle}</Text>}
      </View>
      {right}
    </View>
  );
}

export function Chip({
  label,
  onPress,
}: {
  label: string;
  onPress?: () => void;
}) {
  return (
    <TouchableOpacity onPress={onPress} style={S.chip} activeOpacity={0.9}>
      <Text style={S.chipText}>{label}</Text>
    </TouchableOpacity>
  );
}

export function KPI({
  title,
  value,
}: {
  title: string;
  value: number | string;
}) {
  return (
    <View style={[S.kpi, SHADOW.card]}>
      <Text style={S.kpiVal}>{value}</Text>
      <Text style={S.kpiLabel}>{title}</Text>
    </View>
  );
}

export function HeroCard({
  title,
  idText,
  tone = "mocha",
  onPress,
  style,
}: {
  title: string;
  idText?: string;
  tone?: "mocha" | "primary";
  onPress?: () => void;
  style?: ViewStyle;
}) {
  const bg = tone === "mocha" ? COLORS.softMocha : COLORS.softSage;
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.95}
      style={[S.hero, { backgroundColor: bg }, style, SHADOW.card]}
    >
      <View style={{ flex: 1, paddingRight: 8 }}>
        <Text style={S.heroTitle}>{title}</Text>
        {!!idText && <Text style={S.heroId}>{idText}</Text>}
      </View>
      <BoxIllustration width={160} height={110} tone={tone} />
    </TouchableOpacity>
  );
}

export function RewardBanner({
  title = "מבצע פעיל",
  subtitle = "קיבלת שובר הנחה על פעילות מוצלחת",
  tone = "mocha",
}: {
  title?: string;
  subtitle?: string;
  tone?: "mocha" | "primary";
}) {
  const bg = tone === "mocha" ? COLORS.softMocha : COLORS.softSage;
  const fg = tone === "mocha" ? COLORS.mocha : COLORS.primaryDark;
  return (
    <View style={[S.reward, { backgroundColor: bg }, SHADOW.card]}>
      <View style={S.rewardBadge}>
        <Text style={[S.rewardBadgeText, { color: fg }]}>%</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={S.rewardTitle}>{title}</Text>
        <Text style={S.rewardSub}>{subtitle}</Text>
      </View>
    </View>
  );
}

export function ListCard({
  title,
  subtitle,
  onPress,
  tone = "primary",
}: {
  title: string;
  subtitle?: string;
  onPress?: () => void;
  tone?: "primary" | "mocha";
}) {
  const bg = tone === "mocha" ? COLORS.softMocha : COLORS.softSage;
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[S.listCard, { backgroundColor: bg }, SHADOW.card]}
    >
      <View style={S.bullet} />
      <View style={{ flex: 1 }}>
        <Text style={S.listTitle} numberOfLines={1}>
          {title}
        </Text>
        {!!subtitle && (
          <Text style={S.listSub} numberOfLines={1}>
            {subtitle}
          </Text>
        )}
      </View>
      <Text style={S.chev}>›</Text>
    </TouchableOpacity>
  );
}

/** Wide action button styled like RewardBanner (for “פתוחות/פעילות/הושלמו” etc.) */
export function ActionBanner({
  title,
  subtitle,
  active = false,
  onPress,
}: {
  title: string;
  subtitle?: string;
  active?: boolean;
  onPress?: () => void;
}) {
  const bg = active ? COLORS.primary : COLORS.softSage;
  const titleColor = active ? "#fff" : COLORS.text;
  const subColor = active ? "#f6f7f8" : COLORS.dim;
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.95}
      style={[
        S.reward,
        { backgroundColor: bg },
        SHADOW.card,
        { marginTop: 10 },
      ]}
    >
      <View style={[S.rewardBadge, { backgroundColor: "#fff" }]}>
        <Text style={[S.rewardBadgeText, { color: COLORS.primaryDark }]}>
          ●
        </Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[S.rewardTitle, { color: titleColor }]}>{title}</Text>
        {!!subtitle && (
          <Text style={[S.rewardSub, { color: subColor }]}>{subtitle}</Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

const S = StyleSheet.create({
  header: {
    flexDirection: "row-reverse",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  hTitle: {
    fontSize: 22,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "center",
    writingDirection: "rtl",
  },
  hSub: {
    marginTop: 4,
    color: COLORS.dim,
    textAlign: "center",
    writingDirection: "rtl",
  },

  chip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: COLORS.card,
    borderRadius: RAD.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },
  chipText: { fontWeight: "800", color: COLORS.text },

  // White rounded KPI tiles (match your older home design)
  kpi: {
    flex: 1,
    backgroundColor: COLORS.card,
    borderRadius: RAD.md,
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginHorizontal: 5,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
    alignItems: "center",
  },
  kpiVal: { fontWeight: "900", fontSize: 18, textAlign: "center" },
  kpiLabel: { color: COLORS.dim, marginTop: 4, textAlign: "center" },

  hero: {
    flexDirection: "row-reverse",
    alignItems: "center",
    borderRadius: RAD.lg,
    padding: 16,
    overflow: "hidden",
  },
  heroTitle: {
    fontSize: 24,
    fontWeight: "900",
    color: COLORS.text,
    textAlign: "right",
    writingDirection: "rtl",
  },
  heroId: {
    marginTop: 8,
    backgroundColor: "#fff",
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: RAD.pill,
    alignSelf: "flex-start",
    color: COLORS.dim,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: COLORS.border,
  },

  reward: {
    flexDirection: "row-reverse",
    alignItems: "center",
    borderRadius: RAD.lg,
    padding: 14,
    marginTop: 12,
  },
  rewardBadge: {
    width: 52,
    height: 52,
    borderRadius: RAD.pill,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 12,
  },
  rewardBadgeText: { fontWeight: "900", fontSize: 18 },
  rewardTitle: {
    fontWeight: "900",
    fontSize: 16,
    color: COLORS.text,
    textAlign: "right",
  },
  rewardSub: { marginTop: 4, color: COLORS.dim, textAlign: "right" },

  listCard: {
    flexDirection: "row-reverse",
    alignItems: "center",
    borderRadius: RAD.md,
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginBottom: 10,
  },
  bullet: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: COLORS.primaryDark,
    marginLeft: 10,
  },
  listTitle: { fontWeight: "800", color: COLORS.text, textAlign: "right" },
  listSub: { color: COLORS.dim, marginTop: 2, textAlign: "right" },
  chev: {
    fontSize: 22,
    fontWeight: "900",
    color: COLORS.primaryDark,
    marginRight: 8,
  },
});
