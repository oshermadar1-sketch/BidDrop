// lib/session.ts
// Remembers the login token on the device, so the wallet is needed once per token
// lifetime instead of on every visit. The token itself is still issued and checked by
// the server (routes_auth.py); this only stores it between visits.
import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY = "biddrop_session_token";
// Treat a token as gone a minute before it really expires, to avoid a request that
// fails on arrival.
const SAFETY_MS = 60_000;

/** Expiry of a JWT in ms since epoch, or null when it cannot be read. */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = JSON.parse(json)?.exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export async function saveSession(token: string): Promise<void> {
  await AsyncStorage.setItem(KEY, token);
}

/** The remembered token, or null when there is none or it has expired. */
export async function loadSession(): Promise<string | null> {
  const token = await AsyncStorage.getItem(KEY);
  if (!token) return null;
  const exp = tokenExpiresAt(token);
  if (exp !== null && exp - Date.now() < SAFETY_MS) {
    await clearSession();
    return null;
  }
  return token;
}

export async function clearSession(): Promise<void> {
  await AsyncStorage.removeItem(KEY);
}
