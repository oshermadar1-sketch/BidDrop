// lib/afterLogin.ts
// What every login path does once the server has issued a token: remember it on the
// device, then go to the profile form (new user) or the role screen (profile done).
import { getMyProfile } from "./api";
import { saveSession } from "./session";

type RouterLike = { replace: (to: any) => void };

export async function routeAfterLogin(router: RouterLike, token: string): Promise<void> {
  await saveSession(token).catch(() => {});

  let completed = false;
  try {
    const me = await getMyProfile(token);
    completed =
      !!me?.first_login_completed ||
      (!!me?.first_name && !!me?.last_name && !!me?.phone && !!me?.email && !!me?.city);
  } catch {
    completed = false;
  }

  router.replace({
    pathname: completed ? "/role_select" : "/profile-setup",
    params: { token },
  });
}
