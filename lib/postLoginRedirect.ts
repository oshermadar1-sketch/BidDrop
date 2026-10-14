// lib/postLoginRedirect.ts
// After a successful login (you have a JWT), decide where to go.
// If first_login_completed === true -> /home
// else -> /profile-setup
import { getMe } from "./api";
import type { Router } from "expo-router";

export async function postLoginRedirect(token: string, router: Router) {
  // Fetch the user; server resolves wallet via JWT 'sub'
  const me = await getMe(token);

  if (me.first_login_completed) {
    // Pass token as param if Home reads it from route params
    router.replace({ pathname: "/home", params: { token } });
  } else {
    router.replace({ pathname: "/profile-setup", params: { token } });
  }
}
