// app/lib/api.ts
// Unified API client for BidDrop (Expo).
// Comments are in English (as requested). User-facing strings are in Hebrew.

import Constants from "expo-constants";

// --------------------------- Base URL & bootstrap ---------------------------

export const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  process.env.EXPO_PUBLIC_POBA_API ??
  (Constants.expoConfig?.extra as any)?.apiUrl ??
  "";

if (!BASE_URL) {
  console.log(
    "[API] Missing BASE_URL: set EXPO_PUBLIC_API_URL or EXPO_PUBLIC_POBA_API"
  );
  throw new Error(
    "Missing API base URL. Set EXPO_PUBLIC_API_URL (or EXPO_PUBLIC_POBA_API) in your env."
  );
}

console.log("[API] BASE_URL →", BASE_URL);

// ------------------------------- Common types -------------------------------

export interface NonceResponse {
  wallet_address: string;
  nonce: string;
  message_to_sign: string;
  expires_at: string;
}

export interface VerifyResponse {
  token: string; // normalized: prefer access_token/token
  is_new_user?: boolean;
  access_token?: string;
  token_type?: string;
  user?: any;
}

/** Server 'users' row. */
export interface UserRow {
  id: string;
  wallet_address: string;
  role: string;
  email: string | null;
  phone: string | null;
  city: string | null;
  first_name: string | null;
  last_name: string | null;
  rating: number | null;
  first_login_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProfileInput {
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  city: string;
}

/** Common list options (offset pagination). */
export type ListOpts = { limit?: number; offset?: number };

/** Unified status type across app. */
export type CommonStatus =
  | "open"
  | "assigned" // we use 'assigned' instead of legacy 'matched'
  | "in_transit"
  | "completed"
  | "cancelled";

/** Shared payment status used by assignments.payment_status and escrows.status. */
export type PaymentStatus =
  | "pending_deposit"
  | "deposited"
  | "released"
  | "refunded"
  | "failed"
  | "cancelled";

function normalizeStatus(s: string): CommonStatus {
  return s === "matched" ? "assigned" : (s as CommonStatus);
}

// ------------------------------ Fetch helpers ------------------------------

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchWithTimeout(
  input: string,
  init: RequestInit & { timeoutMs?: number } = {}
) {
  const { timeoutMs = 12000, ...rest } = init;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);

  console.log("[API] →", rest.method || "GET", input);
  if (rest.body) {
    try {
      console.log(
        "[API]   body:",
        typeof rest.body === "string" ? rest.body : "(non-string)"
      );
    } catch {}
  }

  try {
    const res = await fetch(input, { ...rest, signal: ctrl.signal });
    console.log("[API] ←", res.status, res.statusText);
    return res;
  } catch (err: any) {
    console.log("[API] ✖ fetch error:", err?.name, err?.message || err);
    if (err?.name === "AbortError") {
      throw new Error("Request timeout. Check API URL / connectivity / CORS.");
    }
    throw err;
  } finally {
    clearTimeout(t);
  }
}

async function jsonFetch<T = any>(
  url: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<T> {
  const res = await fetchWithTimeout(url, init);
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    try {
      const txt = await res.text();
      console.log("[API] non-JSON response:", txt.slice(0, 200));
    } catch {}
  }
  if (!res.ok) {
    const detail =
      (data && (data.detail || data.error)) ??
      (data && JSON.stringify(data)) ??
      `HTTP ${res.status}`;
    console.log("[API] error payload:", detail);
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
  }
  return data as T;
}

// --------------------------------- Auth ------------------------------------

export async function getNonce(address: string): Promise<NonceResponse> {
  return jsonFetch(`${BASE_URL}/auth/nonce`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    timeoutMs: 12000,
    body: JSON.stringify({ wallet_address: address }),
  });
}

export async function verifySignature(params: {
  address: string;
  message: string;
  signature: string;
}): Promise<VerifyResponse> {
  const data = await jsonFetch(`${BASE_URL}/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    timeoutMs: 12000,
    body: JSON.stringify({
      wallet_address: params.address,
      signed_message: params.message,
      signature: params.signature,
    }),
  });

  return {
    token: data.access_token ?? data.token,
    is_new_user: data.is_new_user,
    access_token: data.access_token,
    token_type: data.token_type,
    user: data.user,
  };
}

// --------------------------------- Users -----------------------------------

/** Get the current user using the JWT. */
export async function getMyProfile(token: string): Promise<UserRow> {
  return jsonFetch<UserRow>(`${BASE_URL}/users/me`, {
    headers: { ...authHeaders(token) },
    timeoutMs: 10000,
  });
}

/** Alias for screens that import getMe. */
export const getMe = getMyProfile;

/** Upsert the current user's profile. */
export async function upsertProfile(
  input: { token: string } & ProfileInput
): Promise<UserRow> {
  const { token, ...payload } = input;
  return jsonFetch<UserRow>(`${BASE_URL}/users/me`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    timeoutMs: 12000,
    body: JSON.stringify(payload),
  });
}

/** Backend roles as stored in users.role */
export type BackendRole = "sender" | "driver" | "admin";

/**
 * Update the current user's backend role (sender/driver/admin).
 * UI "courier"/"rider" will be mapped to these values in the screens.
 */
export async function updateUserRole(
  token: string,
  role: BackendRole
): Promise<UserRow> {
  return jsonFetch<UserRow>(`${BASE_URL}/users/me/role`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    timeoutMs: 10000,
    body: JSON.stringify({ role }),
  });
}

// --------------------------- Sender (packages) ------------------------------

/** A request created by a sender or rider. */
export type RequestRow = {
  id: string;
  owner_user_id: string;
  type: "package" | "ride" | "passenger";
  from_address: string;
  from_lat?: number | null;
  from_lon?: number | null;
  to_address: string;
  to_lat?: number | null;
  to_lon?: number | null;
  passengers?: number | null;
  notes?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  status: CommonStatus;
  created_at: string;
  updated_at: string;

  max_price?: number | null;
  pickup_contact_name?: string | null;
  pickup_contact_phone?: string | null;
};

export type SenderMetrics = {
  open_count: number;
  active_count: number;
  delivered_count: number;
  cancelled_count?: number;
};

export type SenderBucket = "open" | "active" | "delivered";

export async function getSenderMetrics(token: string): Promise<SenderMetrics> {
  return jsonFetch<SenderMetrics>(`${BASE_URL}/sender/metrics`, {
    headers: { ...authHeaders(token) },
  });
}

export async function listSenderRequests(
  token: string,
  bucket: SenderBucket,
  opts: ListOpts = {}
): Promise<RequestRow[]> {
  const q = new URLSearchParams({
    status: bucket,
    limit: String(opts.limit ?? 50),
    offset: String(opts.offset ?? 0),
  });
  const rows = await jsonFetch<any[]>(
    `${BASE_URL}/sender/requests?${q.toString()}`,
    { headers: { ...authHeaders(token) } }
  );
  return rows.map((r) => ({
    ...r,
    status: normalizeStatus(r.status),
  })) as RequestRow[];
}

// ------------------------------ Courier (driver) ----------------------------

/** Courier job row shown to drivers (may originate from sender/rider requests). */
export type CourierJobRow = {
  // Backward-compat job id – still equals request_id for now
  id: string;

  // New ids for details screen:
  assignment_id?: string; // assignment.id (for active/delivered)
  request_id?: string; // requests.id (for all buckets)

  type: "package" | "passenger";
  status: CommonStatus;
  from_address: string;
  to_address: string;
  window_start?: string | null;
  window_end?: string | null;

  // Price computed from assignments.agreed_price_cents (float currency units)
  agreed_price?: number | null;

  distance_km?: number | null;
  suggested_pay?: string | number | null;
  notes?: string | null;
  created_at: string;
};

export type CourierMetrics = {
  available_count: number;
  active_count: number;
  delivered_count: number;
};

export type CourierBucket = "available" | "active" | "delivered";

export async function getCourierMetrics(
  token: string
): Promise<CourierMetrics> {
  return jsonFetch<CourierMetrics>(`${BASE_URL}/courier/metrics`, {
    headers: { ...authHeaders(token) },
  });
}

export async function listCourierJobs(
  token: string,
  bucket: CourierBucket,
  opts: ListOpts = {}
): Promise<CourierJobRow[]> {
  const q = new URLSearchParams({
    status: bucket,
    limit: String(opts.limit ?? 50),
    offset: String(opts.offset ?? 0),
  });
  const rows = await jsonFetch<any[]>(
    `${BASE_URL}/courier/jobs?${q.toString()}`,
    { headers: { ...authHeaders(token) } }
  );
  // Backend already normalizes status + exposes assignment_id / request_id / agreed_price
  return rows.map((r) => ({
    ...r,
    status: normalizeStatus(r.status),
  })) as CourierJobRow[];
}

export async function courierAcceptJob(token: string, jobId: string) {
  return jsonFetch<{ ok: true; job_id: string }>(
    `${BASE_URL}/courier/jobs/${encodeURIComponent(jobId)}/accept`,
    { method: "POST", headers: { ...authHeaders(token) } }
  );
}
export async function courierStartJob(token: string, jobId: string) {
  return jsonFetch<{ ok: true; job_id: string }>(
    `${BASE_URL}/courier/jobs/${encodeURIComponent(jobId)}/start`,
    { method: "POST", headers: { ...authHeaders(token) } }
  );
}
export async function courierMarkDelivered(token: string, jobId: string) {
  return jsonFetch<{ ok: true; job_id: string }>(
    `${BASE_URL}/courier/jobs/${encodeURIComponent(jobId)}/delivered`,
    { method: "POST", headers: { ...authHeaders(token) } }
  );
}

export async function createCourierOffer(
  token: string,
  body: {
    from_address: string;
    to_address?: string | null;
    window_start: string;
    window_end: string;
    min_price: number;
    types: ("package" | "passenger")[];
    notes?: string | null;
    from_lat?: number | null;
    from_lon?: number | null;
    to_lat?: number | null;
    to_lon?: number | null;
  }
) {
  return jsonFetch<{ id: string; status: string; created_at: string }>(
    `${BASE_URL}/offers`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
      timeoutMs: 12000,
    }
  );
}

// ---------------------------- Courier Offers (driver availability) ----------------------------

export type CourierOfferRow = {
  id: string;
  driver_user_id?: string;
  from_address: string;
  to_address?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  min_price: string;
  types: ("package" | "passenger")[];
  notes?: string | null;
  status: "active" | "assigned" | "paused" | "completed" | "cancelled";
  created_at: string;
  updated_at: string;
};

export async function listMyCourierOffers(
  token: string,
  opts: { status?: string; limit?: number; offset?: number } = {}
): Promise<CourierOfferRow[]> {
  const q = new URLSearchParams({
    ...(opts.status ? { status: opts.status } : {}),
    limit: String(opts.limit ?? 50),
    offset: String(opts.offset ?? 0),
  });
  return jsonFetch<CourierOfferRow[]>(`${BASE_URL}/offers?${q.toString()}`, {
    headers: { ...authHeaders(token) },
    timeoutMs: 12000,
  });
}

// ------------------------------- Rider (rides) ------------------------------

export type RiderRequestRow = {
  id: string;
  status: CommonStatus;
  from_address: string;
  to_address: string;
  window_start?: string | null;
  window_end?: string | null;
  passengers?: number | null;
  notes?: string | null;
  max_price?: number | null;
  created_at: string;
};

export type RiderMetrics = {
  open_count: number;
  active_count: number;
  completed_count: number;
  cancelled_count?: number;
};

export type RiderBucket = "open" | "active" | "completed";

export async function getRiderMetrics(token: string): Promise<RiderMetrics> {
  return jsonFetch<RiderMetrics>(`${BASE_URL}/rider/metrics`, {
    headers: { ...authHeaders(token) },
  });
}

export async function listRiderRequests(
  token: string,
  bucket: RiderBucket,
  opts: ListOpts = {}
): Promise<RiderRequestRow[]> {
  const q = new URLSearchParams({
    status: bucket,
    limit: String(opts.limit ?? 50),
    offset: String(opts.offset ?? 0),
  });
  const rows = await jsonFetch<any[]>(
    `${BASE_URL}/rider/requests?${q.toString()}`,
    { headers: { ...authHeaders(token) } }
  );
  return rows.map((r) => ({
    ...r,
    status: normalizeStatus(r.status),
  })) as RiderRequestRow[];
}

export type CreateRiderPayload = {
  from_address: string;
  to_address: string;
  window_start: string;
  window_end: string;
  passengers: number;
  notes?: string | null;
  max_price?: number | null;
  from_lat?: number | null;
  from_lon?: number | null;
  to_lat?: number | null;
  to_lon?: number | null;
};

export async function createRiderRequest(
  token: string,
  payload: CreateRiderPayload
) {
  const body = { type: "ride", ...payload };
  return jsonFetch<CreateRequestResponse>(`${BASE_URL}/requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body),
    timeoutMs: 12000,
  });
}

export async function riderCancelRequest(token: string, requestId: string) {
  return jsonFetch<{ ok: true; id: string }>(
    `${BASE_URL}/rider/requests/${encodeURIComponent(requestId)}/cancel`,
    { method: "POST", headers: { ...authHeaders(token) } }
  );
}

// ---------------------------- Create Request API -----------------------------

export type CreateRequestInput = {
  type: "package" | "ride" | "passenger";
  from_address: string;
  to_address: string;
  window_start: string;
  window_end: string;
  notes?: string;
  max_price: number;
  pickup_contact_name?: string | null;
  pickup_contact_phone?: string | null;
  from_lat?: number | null;
  from_lon?: number | null;
  to_lat?: number | null;
  to_lon?: number | null;
  passengers?: number | null;
};

export type CreateRequestResponse = {
  id: string;
  status: string;
  created_at: string;
};

export async function createSenderRequest(
  token: string,
  body: CreateRequestInput
): Promise<CreateRequestResponse> {
  return jsonFetch<CreateRequestResponse>(`${BASE_URL}/requests`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    timeoutMs: 12000,
    body: JSON.stringify(body),
  });
}

// -------------------------------- Auctions ----------------------------------

export type AuctionClearResult = {
  cleared: boolean;
  matches?: { request_id: string; driver_user_id: string }[];
  reason?: string;
  debug?: any;
  debug_counts?: any;
  objective?: { total_weighted_penalty: number };
};

export async function clearAuctions(
  payload: { request_ids?: string[]; now_ts?: number } = {}
): Promise<AuctionClearResult> {
  return jsonFetch<AuctionClearResult>(`${BASE_URL}/auction/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: 12000,
  });
}

export async function closeAuctionOnchain(payload: {
  auction_id: string;
  winner_ss58?: string;
}): Promise<{ ok: boolean; job_id: string }> {
  return jsonFetch<{ ok: boolean; job_id: string }>(
    `${BASE_URL}/auctions/close`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeoutMs: 12000,
    }
  );
}

// --------------------------------- Utilities --------------------------------

export async function pingApi(): Promise<{ ok: true }> {
  try {
    await jsonFetch(`${BASE_URL}/healthz`, { timeoutMs: 6000 });
  } catch (e) {
    try {
      await jsonFetch(`${BASE_URL}/health/db`, { timeoutMs: 6000 });
    } catch (e2) {}
  }
  return { ok: true };
}

/** Defer push notifications for a request and return the defer-until timestamp (ISO) */
export async function deferPushForRequest(
  token: string,
  requestId: string,
  seconds = 60
) {
  const url = `${BASE_URL}/requests/${encodeURIComponent(
    requestId
  )}/defer_push?seconds=${seconds}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  try {
    return (await res.json()) as { ok: boolean; push_defer_until?: string };
  } catch {
    return null;
  }
}

/** Poll match status for a given request (owner side). */
export async function checkMatchStatus(token: string, requestId: string) {
  const url = `${BASE_URL}/requests/${encodeURIComponent(requestId)}/match_status`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { status: "pending" as const };
  try {
    return await res.json();
  } catch {
    return { status: "pending" as const };
  }
}

/** Defer push notifications for an offer and return the defer-until timestamp (ISO) */
export async function deferPushForOffer(
  token: string,
  offerId: string,
  seconds = 60
) {
  const url = `${BASE_URL}/offers/${encodeURIComponent(
    offerId
  )}/defer_push?seconds=${seconds}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  try {
    return (await res.json()) as { ok: boolean; push_defer_until?: string };
  } catch {
    return null;
  }
}

/** Poll match status for a given offer (driver side). */
export async function checkOfferMatchStatus(token: string, offerId: string) {
  const url = `${BASE_URL}/offers/${encodeURIComponent(offerId)}/match_status`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return { status: "pending" as const };
  try {
    return await res.json();
  } catch {
    return { status: "pending" as const };
  }
}

/* ----------------------------- Courier profile ----------------------------- */
// Age and vehicle of a courier: inputs of the delivery-time model.

export type VehicleType = "motorcycle" | "scooter" | "electric_scooter";

export type CourierProfile = {
  age: number | null;
  vehicle_type: VehicleType | null;
  vehicle_condition: 0 | 1 | 2 | null;
  completed: boolean;
};

export async function getCourierProfile(token: string): Promise<CourierProfile> {
  return jsonFetch<CourierProfile>(`${BASE_URL}/users/me/courier-profile`, {
    headers: { ...authHeaders(token) },
    timeoutMs: 12000,
  });
}

export async function saveCourierProfile(
  token: string,
  body: { age: number; vehicle_type: VehicleType; vehicle_condition: 0 | 1 | 2 }
): Promise<CourierProfile> {
  return jsonFetch<CourierProfile>(`${BASE_URL}/users/me/courier-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    timeoutMs: 12000,
    body: JSON.stringify(body),
  });
}

/* ---------------------------- Assignment Details ---------------------------- */

export type DriverBrief = {
  id: string;
  full_name?: string | null;
  phone?: string | null;
  rating?: number | null;
  vehicle_type?: string | null;
  avatar_url?: string | null;
  /** Trust score 1..5 (customer ratings + ML punctuality). */
  trust_score?: number | null;
  num_ratings?: number | null;
  is_new_courier?: boolean | null;
  /** How the trust score was computed. */
  customer_part?: number | null;
  model_part?: number | null;
  customer_weight?: number | null;
  model_weight?: number | null;
  num_timed_deliveries?: number | null;
};

export type RequestBrief = {
  id: string;
  type: "package" | "ride" | "passenger";
  from_address?: string | null;
  to_address?: string | null;
  passengers?: number | null;
  pickup_contact_name?: string | null;
  pickup_contact_phone?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  notes?: string | null;
};

export type LastLocation = {
  lat: number;
  lng: number;
  updated_at: string; // ISO
};

export type AssignmentDetailOut = {
  assignment_id: string;
  request_id: string;
  status: string;

  payment_status?: PaymentStatus;
  agreed_price_cents?: number | null;

  assigned_at: string; // ISO
  picked_up_at?: string | null;
  in_transit_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  cancelled_at?: string | null;
  onchain_tx_hash?: string | null;

  driver: DriverBrief;
  requester?: DriverBrief | null;
  last_location?: LastLocation | null;
  request: RequestBrief;

  /** ML-predicted delivery time for this courier and route (minutes). */
  predicted_minutes?: number | null;
  /** Score the customer gave the driver for this assignment (null = not rated yet). */
  driver_rating_score?: number | null;
};

// Assignment logistics status options (must match backend)
export type AssignmentStatus =
  | "created"
  | "picked_up"
  | "in_transit"
  | "completed"
  | "cancelled"
  | "failed";

/** Get assignment by request; backend will usually return only active one. */
export async function getAssignmentByRequest(
  requestId: string,
  offerId?: string
): Promise<AssignmentDetailOut> {
  const url =
    `${BASE_URL}/assignments/by-request/${encodeURIComponent(requestId)}` +
    (offerId ? `?offer_id=${encodeURIComponent(offerId)}` : "");
  return jsonFetch<AssignmentDetailOut>(url, { timeoutMs: 12000 });
}

/** Get assignment by its ID (preferred when we know the assignment_id). */
export async function getAssignmentById(
  assignmentId: string
): Promise<AssignmentDetailOut> {
  return jsonFetch<AssignmentDetailOut>(
    `${BASE_URL}/assignments/${encodeURIComponent(assignmentId)}`,
    { timeoutMs: 12000 }
  );
}

/** Customer rates the driver of a completed assignment (1..5). */
export async function rateDriver(
  assignmentId: string,
  score: number
): Promise<{ status: string; new_rating: number }> {
  return jsonFetch(
    `${BASE_URL}/assignments/${encodeURIComponent(assignmentId)}/rate-driver`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      timeoutMs: 12000,
      body: JSON.stringify({ score }),
    }
  );
}

/**
 * Update assignment logistics status (driver side).
 * Mirrors PATCH /assignments/{id}/status in the backend.
 */
export async function updateAssignmentStatus(
  token: string,
  assignmentId: string,
  status: AssignmentStatus
): Promise<AssignmentDetailOut> {
  return jsonFetch<AssignmentDetailOut>(
    `${BASE_URL}/assignments/${encodeURIComponent(assignmentId)}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(token),
      },
      timeoutMs: 12000,
      body: JSON.stringify({ status }),
    }
  );
}

/**
 * Rider-side logical confirmation that arrival/delivery was acknowledged.
 * Backend endpoint: POST /assignments/{id}/confirm-delivered.
 */
export async function confirmAssignmentDelivered(
  token: string,
  assignmentId: string
): Promise<AssignmentDetailOut> {
  return jsonFetch<AssignmentDetailOut>(
    `${BASE_URL}/assignments/${encodeURIComponent(
      assignmentId
    )}/confirm-delivered`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(token),
      },
      timeoutMs: 12000,
    }
  );
}

/* ----------------------------- Matching triggers ---------------------------- */
/** Ask server to try and create a REAL assignment for a driver offer (atomic). */
function ensureMatchTriggerAllowed() {
  // Never allow from production mobile by default:
  const flag =
    process.env.EXPO_PUBLIC_ALLOW_MATCH_TRIGGERS ??
    (Constants.expoConfig?.extra as any)?.ALLOW_MATCH_TRIGGERS ??
    "false";
  if (String(flag).toLowerCase() !== "true") {
    throw new Error(
      "Client-side matching trigger is disabled. Wait for on-chain finalization."
    );
  }
}

/** Ask server to try and create a REAL assignment for a driver offer (atomic). */
export async function runMatchingForOffer(token: string, offerId: string) {
  ensureMatchTriggerAllowed();
  return jsonFetch<
    | {
        status: "matched";
        message: string;
        assignment_id: string;
        request_id: string;
      }
    | { status: "no_match"; message: string }
  >(`${BASE_URL}/match/offers/${encodeURIComponent(offerId)}/run`, {
    method: "POST",
    headers: { ...authHeaders(token) },
  });
}

/** Ask server to try and create a REAL assignment for a request (atomic). */
export async function runMatchingForRequest(token: string, requestId: string) {
  ensureMatchTriggerAllowed();
  return jsonFetch<
    | {
        status: "matched";
        message: string;
        assignment_id: string;
        request_id: string;
      }
    | { status: "no_match"; message: string }
  >(`${BASE_URL}/match/requests/${encodeURIComponent(requestId)}/run`, {
    method: "POST",
    headers: { ...authHeaders(token) },
  });
}

/* ------------------------------- Escrows (payments) ------------------------------- */

export type EscrowRow = {
  id: string;
  assignment_id: string;
  payer_user_id: string;
  payee_user_id: string;
  amount_cents: number;
  status: PaymentStatus;
  created_at: string;
  updated_at: string;
  driver_marked_completed_at?: string | null;
  sender_confirmed_at?: string | null;
  auto_release_at?: string | null;
};

/**
 * Initiate an escrow for a given assignment.
 * Called when the sender taps "Pay" (or similar).
 * Only the request owner is allowed by the backend.
 */
export async function initiateEscrow(
  token: string,
  assignmentId: string
): Promise<EscrowRow> {
  return jsonFetch<EscrowRow>(`${BASE_URL}/escrows/initiate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    timeoutMs: 12000,
    body: JSON.stringify({ assignment_id: assignmentId }),
  });
}

/**
 * Sender-side confirmation that triggers escrow release on-chain.
 * Calls POST /escrows/confirm-delivered with { assignment_id } and returns Escrow row.
 */
export async function confirmEscrowDelivered(
  token: string,
  assignmentId: string
): Promise<EscrowRow> {
  return jsonFetch<EscrowRow>(`${BASE_URL}/escrows/confirm-delivered`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
    },
    timeoutMs: 12000,
    body: JSON.stringify({ assignment_id: assignmentId }),
  });
}
