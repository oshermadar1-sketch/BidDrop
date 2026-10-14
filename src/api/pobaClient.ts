const BASE = process.env.EXPO_PUBLIC_POBA_API || "http://localhost:8000";


// הערות חשובות:
// - iOS Simulator: localhost עובד כרגיל.
// - Android Emulator (בעתיד): החליפי ל- http://10.0.2.2:3001
// - מכשיר אמיתי: שימי את IP של המחשב במקום localhost.

export type CreateShipmentInput = {
  detailsURI: string; // תיאור/קישור/IPFS
  deadline: number; // Unix time בשניות
  creator?: string; // אופציונלי (זהות במערכת permissioned)
};

export async function createShipment(input: CreateShipmentInput) {
  const res = await fetch(`${BASE}/shipments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ id: number }>;
}

export async function placeBid(id: number, price: number, courier?: string) {
  const res = await fetch(`${BASE}/shipments/${id}/bids`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ price, courier }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function closeAuction(id: number) {
  const res = await fetch(`${BASE}/shipments/${id}/close`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function declareWinner(id: number) {
  const res = await fetch(`${BASE}/shipments/${id}/declare`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ ok: true; winner: string; price: number }>;
}

export async function getShipment(id: number) {
  const res = await fetch(`${BASE}/shipments/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{
    shipment: any;
    bids: Array<{ courier: string; price: number }>;
  }>;
}
