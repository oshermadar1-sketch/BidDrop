// app/_layout.tsx
import "react-native-get-random-values";
import "react-native-url-polyfill/auto";
import "../lib/webAlert";

import React, { useEffect } from "react";
import { Stack } from "expo-router";
import { ensurePushSetup } from "../lib/push";

export default function Layout() {
  useEffect(() => {
    ensurePushSetup();
  }, []);

  return (
    <Stack screenOptions={{ headerTitleAlign: "center" }}>
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="home" options={{ headerShown: false }} />
      <Stack.Screen name="wallet-login" options={{ headerShown: false }} />
      <Stack.Screen name="profile-setup" options={{ headerShown: false }} />
      <Stack.Screen name="role_select" options={{ headerShown: false }} />
      <Stack.Screen name="courier_profile" options={{ headerShown: false }} />
      <Stack.Screen name="sender_home_page" options={{ headerShown: false }} />
      <Stack.Screen name="rider_home_page" options={{ headerShown: false }} />
      <Stack.Screen name="courier_home_page" options={{ headerShown: false }} />
      <Stack.Screen name="bucket_list" options={{ headerShown: false }} />
      <Stack.Screen name="payment_details" options={{ headerShown: false }} />
      <Stack.Screen name="request_details" options={{ headerShown: false }} />
      <Stack.Screen
        name="sender_request_create"
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="rider_request_create"
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="courier_offer_create"
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="matching-await-driver"
        options={{ headerShown: false }}
      />
      <Stack.Screen name="matching-await" options={{ headerShown: false }} />
      <Stack.Screen
        name="assignment_details"
        options={{ headerShown: false }}
      />
    </Stack>
  );
}
