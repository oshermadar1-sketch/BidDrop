// lib/wc.ts
// WalletConnect helper with robust mobile deep linking to SubWallet
// - Android: subwallet:// (with redirectUrl) → https universal → intent:// → package VIEW → raw wc: → store
// - iOS: app.subwallet.mobile:// → wc: → subwallet:// (enc/raw) → https universal → App Store
// - Includes bringSubWalletToFront() helper

import SignClient from "@walletconnect/sign-client";
import Constants from "expo-constants";
import * as Linking from "expo-linking";
import { Platform } from "react-native";
import * as IntentLauncher from "expo-intent-launcher";

const POLKADOT_CHAIN_ID = "polkadot:91b171bb158e2d3848fa23a9f1c25182";
const PLAY_PACKAGE = "app.subwallet.mobile";
const PLAY_URL = `https://play.google.com/store/apps/details?id=${PLAY_PACKAGE}`;
const APPSTORE_URL = "https://apps.apple.com/app/id1633050285";

let _client: SignClient | null = null;

const WC_PROJECT_ID =
  process.env.EXPO_PUBLIC_WC_PROJECT_ID ??
  (Constants.expoConfig?.extra as any)?.wcProjectId;

if (!WC_PROJECT_ID) {
  throw new Error(
    "Missing EXPO_PUBLIC_WC_PROJECT_ID (WalletConnect ProjectId)"
  );
}

const log = (...a: any[]) => {
  if (__DEV__) console.log("[wc]", ...a);
};

// Return URL for bounce-back (requires app.json "scheme": "biddrop")
export function getReturnUrl(): string {
  return Linking.createURL("wc-callback"); // biddrop://wc-callback
}

function normalizeSignature(res: any): string {
  const sig = (res &&
    (res.signature ?? res.result ?? res.signed ?? res)) as any;
  if (typeof sig !== "string")
    throw new Error("Unexpected signature result from wallet");
  return sig.startsWith("0x") ? sig : `0x${sig}`;
}

export type WCSessionInfo = { topic: string; address: string; raw: any };
export type WCConnectResult =
  | { type: "approved"; session: WCSessionInfo }
  | {
      type: "needsWallet";
      uri: string;
      waitForApproval: () => Promise<WCSessionInfo>;
    };

function buildOpenUrls(wcUri: string) {
  const enc = encodeURIComponent(wcUri);
  const redirectEnc = encodeURIComponent(getReturnUrl());
  const redirectRaw = getReturnUrl();
  return {
    iosPrimary: `app.subwallet.mobile://wc?uri=${enc}&redirectUrl=${redirectEnc}`,
    iosAlt: `subwallet://wc?uri=${enc}&redirectUrl=${redirectEnc}`,
    iosAltRaw: `subwallet://wc?uri=${wcUri}&redirectUrl=${redirectRaw}`,
    iosUniversal: `https://wallet.subwallet.app/wc?uri=${enc}&redirectUrl=${redirectEnc}`,
    androidScheme: `subwallet://wc?uri=${enc}&redirectUrl=${redirectEnc}`,
    androidIntent: `intent://wc?uri=${enc}&redirectUrl=${redirectEnc}#Intent;scheme=subwallet;package=${PLAY_PACKAGE};end`,
    androidUniversal: `https://wallet.subwallet.app/wc?uri=${enc}&redirectUrl=${redirectEnc}`,
    androidSchemeRaw: `subwallet://wc?uri=${wcUri}&redirectUrl=${redirectRaw}`,
    genericWc: wcUri,
  };
}

/** Open SubWallet with wc: URI or route to store (best-effort, never throws). */
export async function openSubWalletOrStore(
  wcUri?: string
): Promise<"opened" | "store" | "noop"> {
  try {
    if (!wcUri) return "noop";
    log("openSubWalletOrStore wc:", wcUri.slice(0, 32) + "…");
    const u = buildOpenUrls(wcUri);

    if (Platform.OS === "android") {
      try {
        await Linking.openURL(u.androidScheme);
        log("android: subwallet:// (enc) opened");
        return "opened";
      } catch (e) {
        log("android: subwallet:// (enc) failed", e);
      }
      try {
        await Linking.openURL(u.androidUniversal);
        log("android: https universal opened");
        return "opened";
      } catch (e) {
        log("android: https universal failed", e);
      }
      try {
        await Linking.openURL(u.androidIntent);
        log("android: intent:// opened");
        return "opened";
      } catch (e) {
        log("android: intent:// failed", e);
      }
      try {
        await Linking.openURL(u.androidSchemeRaw);
        log("android: subwallet:// (raw) opened");
        return "opened";
      } catch (e) {
        log("android: subwallet:// (raw) failed", e);
      }
      try {
        await IntentLauncher.startActivityAsync("android.intent.action.VIEW", {
          data: wcUri,
          packageName: PLAY_PACKAGE,
          category: "android.intent.category.BROWSABLE",
          flags: 0,
        });
        log("android: VIEW wc: to package opened");
        return "opened";
      } catch (e) {
        log("android: VIEW wc: failed", e);
      }
      try {
        await Linking.openURL(u.genericWc);
        log("android: wc: opened");
        return "opened";
      } catch {}
      await Linking.openURL(PLAY_URL);
      log("android: opening Play Store");
      return "store";
    } else {
      try {
        await Linking.openURL(u.iosPrimary);
        log("ios: app.subwallet.mobile opened");
        return "opened";
      } catch (e) {
        log("ios: app.subwallet.mobile failed", e);
      }
      try {
        await Linking.openURL(u.genericWc);
        log("ios: wc: opened");
        return "opened";
      } catch {}
      try {
        await Linking.openURL(u.iosAlt);
        log("ios: subwallet:// (enc) opened");
        return "opened";
      } catch {}
      try {
        await Linking.openURL(u.iosAltRaw);
        log("ios: subwallet:// (raw) opened");
        return "opened";
      } catch {}
      try {
        await Linking.openURL(u.iosUniversal);
        log("ios: https universal opened");
        return "opened";
      } catch {}
      await Linking.openURL(APPSTORE_URL);
      log("ios: opening App Store");
      return "store";
    }
  } catch {
    return "noop";
  }
}

export async function getWCClient(): Promise<SignClient> {
  if (_client) return _client;
  _client = await SignClient.init({
    projectId: WC_PROJECT_ID,
    metadata: {
      name: "BidDrop",
      description: "Crowd-Shipping with Auction-Based Consensus",
      url: "https://bidrop.app",
      icons: [
        "https://raw.githubusercontent.com/yaelhaim/Auction_Based_consensus_for_crowd_shipping/main/assets/images/icon.png",
      ],
    },
  });
  return _client;
}

export async function connect(): Promise<WCConnectResult> {
  const client = await getWCClient();

  const ns = {
    methods: ["polkadot_signMessage"],
    chains: [POLKADOT_CHAIN_ID],
    events: [],
  };

  const { uri, approval } = await client.connect({
    requiredNamespaces: { polkadot: ns },
    optionalNamespaces: { polkadot: ns },
  });

  const resolveSession = async () => {
    const s = await approval();
    const acct = s.namespaces?.polkadot?.accounts?.[0] as string | undefined;
    if (!acct) {
      throw new Error(
        "No Polkadot account returned by wallet. In SubWallet add a Polkadot account (mainnet) and try again."
      );
    }
    const address = acct.split(":")[2];
    return { topic: s.topic, address, raw: s };
  };

  if (!uri) return { type: "approved", session: await resolveSession() };
  return { type: "needsWallet", uri, waitForApproval: resolveSession };
}

export async function signMessage(
  topic: string,
  address: string,
  message: string
): Promise<string> {
  const client = await getWCClient();
  const res = await client.request({
    topic,
    chainId: POLKADOT_CHAIN_ID,
    request: { method: "polkadot_signMessage", params: { address, message } },
  });
  return normalizeSignature(res);
}

/** Bring SubWallet app to foreground (helps surface sign prompts). */
export async function bringSubWalletToFront(): Promise<"opened" | "noop"> {
  try {
    if (Platform.OS === "android") {
      try {
        await Linking.openURL("subwallet://");
        log("bringToFront: subwallet:// opened");
        return "opened";
      } catch {}
      try {
        await IntentLauncher.startActivityAsync("android.intent.action.VIEW", {
          packageName: PLAY_PACKAGE,
          category: "android.intent.category.BROWSABLE",
          flags: 0,
        });
        log("bringToFront: package VIEW opened");
        return "opened";
      } catch {}
      return "noop";
    } else {
      try {
        await Linking.openURL("app.subwallet.mobile://");
        log("bringToFront: ios primary opened");
        return "opened";
      } catch {}
      try {
        await Linking.openURL("subwallet://");
        log("bringToFront: ios alt opened");
        return "opened";
      } catch {}
      return "noop";
    }
  } catch {
    return "noop";
  }
}
