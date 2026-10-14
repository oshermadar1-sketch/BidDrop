// app/matching-await.tsx
// Waiting screen (sender/rider) with city-map background + white card + hourglass.
// Read-only: NO local triggers. We rely solely on the chain/Backend to finalize matches.
// We only show "matched" and enable CTA if we have a solid assignment_id.
// Comments are in English; user-facing strings are in Hebrew.

import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Alert } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { deferPushForRequest, checkMatchStatus } from "../lib/api";
import WaitBackground from "./components/WaitBackground";
import Hourglass from "./components/Hourglass";

const POLL_MS = 1500;
const DEFER_SECONDS = 120;
const DEFAULT_WAIT_MS = 60000;
const GRACE_MS = 30000;
const cityMap = require("../assets/images/city_map_photo.jpg");

// ---- strong id validation (UUID or positive integer) ----
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isValidUuid(v?: unknown): boolean {
  return typeof v === "string" && UUID_RE.test(v.trim());
}
function isPositiveIntString(v?: unknown): boolean {
  if (v == null) return false;
  const s = String(v).trim();
  if (!/^\d+$/.test(s)) return false;
  return parseInt(s, 10) > 0;
}
function normalizeId(v: unknown): string | null {
  if (!v && v !== 0) return null;
  const s = String(v).trim().toLowerCase();
  if (!s || s === "null" || s === "undefined" || s === "nan" || s === "0") {
    return null;
  }
  return s;
}
function solidAssignmentId(raw: any): string | null {
  const aid = normalizeId(raw?.assignment_id ?? raw?.assignmentId);
  if (!aid) return null;
  return isValidUuid(aid) || isPositiveIntString(aid) ? aid : null;
}

export default function MatchingAwait() {
  const router = useRouter();
  const { requestId, token, role, home } = useLocalSearchParams<{
    requestId: string;
    token?: string;
    role?: "rider" | "sender";
    home?: string;
  }>();

  const [status, setStatus] = useState<"searching" | "matched" | "timeout">(
    "searching"
  );
  const [assignmentId, setAssignmentId] = useState<string | null>(null);

  const deadlineRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alertedRef = useRef(false);

  const homePath =
    home ||
    (role === "sender"
      ? "/sender_home_page"
      : role === "rider"
        ? "/rider_home_page"
        : "/home_page");

  useEffect(() => {
    let cancelled = false;
    if (!requestId || !token) return;

    async function start() {
      // Soft deadline for polling (wait window + small grace)
      if (deadlineRef.current === null) {
        deadlineRef.current = Date.now() + DEFAULT_WAIT_MS + GRACE_MS;
      }

      // Defer push notifications for this request (optional nicety)
      try {
        const resp = await deferPushForRequest(
          String(token),
          String(requestId),
          DEFER_SECONDS
        );
        const untilIso = (resp as any)?.push_defer_until;
        if (untilIso) {
          const ts = Date.parse(untilIso);
          if (!Number.isNaN(ts)) deadlineRef.current = ts + GRACE_MS;
        }
      } catch (e) {
        console.log(
          "[await] deferPushForRequest error:",
          (e as any)?.message || e
        );
      }

      // Fallback polling of authoritative server/chain status
      async function poll() {
        try {
          const res = await checkMatchStatus(String(token), String(requestId));
          if (cancelled) return;

          // Debug (can mute later)
          console.log("[await] poll payload:", JSON.stringify(res));

          if (res?.status === "matched") {
            const aid = solidAssignmentId(res);
            if (aid) {
              setAssignmentId(aid);
              setStatus("matched");
              return;
            }
          }
        } catch (e) {
          console.log(
            "[await] checkMatchStatus error:",
            (e as any)?.message || e
          );
        }

        const stopAt =
          deadlineRef.current ?? Date.now() + DEFAULT_WAIT_MS + GRACE_MS;
        if (Date.now() >= stopAt) {
          setStatus("timeout");
          return;
        }
        timerRef.current = setTimeout(poll, POLL_MS);
      }

      poll();
    }

    start();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [requestId, token]);

  useEffect(() => {
    if (status === "timeout" && !alertedRef.current) {
      alertedRef.current = true;
      Alert.alert("אין התאמה כרגע", "נשלח לך התראה כשיימצא נהג/שליח מתאים.");
    }
  }, [status]);

  function goHome() {
    router.replace({ pathname: homePath as any, params: { token } });
  }

  function openAssignment() {
    if (!assignmentId) return;
    router.replace({
      pathname: "/assignment_details",
      params: {
        requestId: String(requestId),
        token: String(token ?? ""),
        role: String(role ?? ""),
        assignmentId: String(assignmentId),
      },
    });
  }

  const ctaDisabled = !assignmentId;

  return (
    <WaitBackground
      imageUri={cityMap}
      opacity={0.7}
      blurRadius={2}
      darken={0.2}
      tintAlpha={0}
    >
      <View style={S.card}>
        {status === "searching" && (
          <>
            <Hourglass />
            <Text style={S.title}>שימי/שימו לב, מחפשים התאמה…</Text>
            <Text style={S.sub}>זה עשוי לקחת מספר רגעים.</Text>
            <TouchableOpacity style={S.linkBtn} onPress={goHome}>
              <Text style={S.linkText}>חזרה לדף הבית</Text>
            </TouchableOpacity>
          </>
        )}

        {status === "matched" && (
          <>
            <Text style={S.bigEmoji}>🎉</Text>
            <Text style={S.title}>נמצאה התאמה!</Text>
            <Text style={S.sub}>
              {assignmentId ? "אפשר להמשיך לפרטים." : "מעדכן מזהים מהשרת…"}
            </Text>
            <TouchableOpacity
              style={[S.cta, !assignmentId && { opacity: 0.6 }]}
              onPress={openAssignment}
              disabled={ctaDisabled}
            >
              <Text style={S.ctaText}>פתח/י את ההתאמה</Text>
            </TouchableOpacity>
            <TouchableOpacity style={S.linkBtn} onPress={goHome}>
              <Text style={S.linkText}>דף הבית</Text>
            </TouchableOpacity>
          </>
        )}

        {status === "timeout" && (
          <>
            <Text style={S.bigEmoji}>⌚</Text>
            <Text style={S.title}>אין התאמה כרגע</Text>
            <Text style={S.sub}>נשלח לך התראה אם תימצא התאמה מאוחר יותר.</Text>
            <TouchableOpacity style={S.cta} onPress={goHome}>
              <Text style={S.ctaText}>חזרה לדף הבית</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </WaitBackground>
  );
}

const S = StyleSheet.create({
  card: {
    width: "92%",
    maxWidth: 520,
    backgroundColor: "#fff",
    borderRadius: 16,
    paddingVertical: 22,
    paddingHorizontal: 18,
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
    gap: 10,
  },
  bigEmoji: { fontSize: 48, marginBottom: 4 },
  title: {
    fontSize: 18,
    fontWeight: "800",
    textAlign: "center",
    color: "#1f2937",
    marginTop: 4,
  },
  sub: { fontSize: 14, opacity: 0.7, textAlign: "center", color: "#334155" },
  cta: {
    backgroundColor: "#9bac70",
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 12,
    marginTop: 6,
  },
  ctaText: { color: "#fff", fontWeight: "800" },
  linkBtn: { padding: 10, marginTop: 8 },
  linkText: { color: "#475569", fontWeight: "600" },
});
