// app/matching-await-driver.tsx
// Strict match gating: require a VALID assignment_id (UUID or positive int).
// Read-only: NO local triggers. We rely only on authoritative status.
// No navigation without a solid assignment id.

import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { deferPushForOffer, checkOfferMatchStatus } from "../lib/api";
import WaitBackground from "./components/WaitBackground";
import Hourglass from "./components/Hourglass";

const POLL_MS = 1500;
const DEFER_SECONDS = 120;
const DEFAULT_WAIT_MS = 60000;
const GRACE_MS = 30000;
const cityMap = require("../assets/images/city_map_photo.jpg");

// ---------- helpers: strong id validation ----------
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
function hasSolidAssignmentId(raw: any): string | null {
  const aid = normalizeId(raw?.assignment_id ?? raw?.assignmentId);
  if (!aid) return null;
  if (isValidUuid(aid) || isPositiveIntString(aid)) return aid;
  return null;
}

export default function MatchingAwaitDriver() {
  const router = useRouter();
  const { offerId, token, home } = useLocalSearchParams<{
    offerId: string;
    token?: string;
    home?: string;
  }>();

  const [status, setStatus] = useState<"searching" | "matched" | "timeout">(
    "searching"
  );
  const [requestId, setRequestId] = useState<string | null>(null);
  const [assignmentId, setAssignmentId] = useState<string | null>(null);

  const deadlineRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const homePath = home || "/courier_home_page";

  useEffect(() => {
    let cancelled = false;
    if (!offerId || !token) return;

    async function start() {
      // Soft deadline for polling
      if (deadlineRef.current === null) {
        deadlineRef.current = Date.now() + DEFAULT_WAIT_MS + GRACE_MS;
      }

      // Defer push notifications for this offer (optional nicety)
      try {
        const resp = await deferPushForOffer(
          String(token),
          String(offerId),
          DEFER_SECONDS
        );
        const untilIso = (resp as any)?.push_defer_until;
        if (untilIso) {
          const ts = Date.parse(untilIso);
          if (!Number.isNaN(ts)) deadlineRef.current = ts + GRACE_MS;
        }
      } catch (e) {
        console.log(
          "[await-driver] deferPushForOffer error:",
          (e as any)?.message || e
        );
      }

      // Authoritative polling only
      async function poll() {
        try {
          const raw = await checkOfferMatchStatus(
            String(token),
            String(offerId)
          );
          if (cancelled) return;

          console.log(
            "[await-driver] poll status payload:",
            JSON.stringify(raw)
          );

          const st = (raw?.status ?? "").toString().toLowerCase().trim();
          const concreteAssignmentId = hasSolidAssignmentId(raw);

          // Optional: capture requestId (nice-to-have)
          const reqIdNorm = normalizeId(raw?.request_id ?? raw?.requestId);
          if (reqIdNorm) setRequestId(reqIdNorm);

          if (st === "matched" && concreteAssignmentId) {
            setAssignmentId(concreteAssignmentId);
            setStatus("matched");
            return;
          }
        } catch (e) {
          console.log(
            "[await-driver] checkOfferMatchStatus error:",
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
  }, [offerId, token]);

  function goHome() {
    router.replace({ pathname: homePath as any, params: { token } });
  }

  function openAssignment() {
    if (!assignmentId) return;
    const params: Record<string, string> = {
      role: "driver",
      token: String(token ?? ""),
      offerId: String(offerId),
      assignmentId: assignmentId,
    };
    if (requestId) params.requestId = requestId;
    router.replace({ pathname: "/assignment_details", params });
  }

  const canOpen = status === "matched" && !!assignmentId;

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
            <Text style={S.title}>מחפשים לך משלוח מתאים…</Text>
            <Text style={S.sub}>זה עשוי לקחת מספר רגעים.</Text>
            <TouchableOpacity style={S.linkBtn} onPress={goHome}>
              <Text style={S.linkText}>חזרה לדף הבית</Text>
            </TouchableOpacity>
          </>
        )}

        {status === "matched" && (
          <>
            <Text style={S.bigEmoji}>🎉</Text>
            <Text style={S.title}>נמצאה משימה!</Text>
            <Text style={S.sub}>
              {canOpen ? "אפשר להמשיך לפרטים." : "מעדכן מזהים מהשרת…"}
            </Text>
            <TouchableOpacity
              style={[S.cta, !canOpen && { opacity: 0.5 }]}
              onPress={openAssignment}
              disabled={!canOpen}
            >
              <Text style={S.ctaText}>פתח/י את המשימה</Text>
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
            <Text style={S.sub}>נשלח לך התראה כשיימצא משלוח מתאים.</Text>
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
