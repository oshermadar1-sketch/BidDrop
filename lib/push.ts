// app/lib/push.ts
// Expo push notifications: permissions, token fetch, and backend sync.

import { Platform, Linking } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";

const FALLBACK_PROJECT_ID = "ba9c100f-a0df-467a-ab24-8ed14b5a8ae6";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

async function ensureAndroidChannel() {
  if (Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("default", {
    name: "Default",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
    vibrationPattern: [0, 250, 250, 250],
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
  });
}

export async function ensurePushSetup(): Promise<void> {
  if (!Device.isDevice) return;
  const before = await Notifications.getPermissionsAsync();
  let status = before.status;

  if (status !== "granted" && before.canAskAgain) {
    const req = await Notifications.requestPermissionsAsync({
      ios: { allowAlert: true, allowBadge: true, allowSound: true },
    });
    status = req.status;
    if (status !== "granted") {
      try {
        await Linking.openSettings();
      } catch {}
    }
  }
  await ensureAndroidChannel();
}

function resolveProjectId(): string {
  const fromExtra = (Constants.expoConfig as any)?.extra?.eas?.projectId;
  const fromConstants = (Constants as any)?.easConfig?.projectId;
  return fromExtra ?? fromConstants ?? FALLBACK_PROJECT_ID;
}

export async function getExpoTokenOrNull(): Promise<string | null> {
  try {
    if (!Device.isDevice) return null;
    const perms = await Notifications.getPermissionsAsync();
    if (perms.status !== "granted") return null;
    const projectId = resolveProjectId();
    const resp = await Notifications.getExpoPushTokenAsync({ projectId });
    return resp?.data ?? null;
  } catch {
    return null;
  }
}

export async function registerAndSyncPushToken(
  apiBaseUrl: string,
  jwt?: string
): Promise<string | null> {
  try {
    await ensurePushSetup();
    const expoToken = await getExpoTokenOrNull();
    if (!expoToken) return null;

    await fetch(`${apiBaseUrl}/devices/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(jwt ? { Authorization: `Bearer ${jwt}` } : {}),
      },
      body: JSON.stringify({ expo_push_token: expoToken }),
    }).catch(() => {});
    return expoToken;
  } catch {
    return null;
  }
}

export async function getPushDebugReport(): Promise<string> {
  try {
    const perms = await Notifications.getPermissionsAsync();
    return `perm=${perms.status}`;
  } catch {
    return "perm=unknown";
  }
}
