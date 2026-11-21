// lib/password.ts
// The password rules the sign-up and reset forms show live. The server enforces the same
// rules (Backend/services/passwords.py), so this is only for immediate feedback.
export const MIN_LENGTH = 8;

export type PasswordRule = { key: string; label: string; ok: (p: string) => boolean };

export const PASSWORD_RULES: PasswordRule[] = [
  { key: "length", label: `לפחות ${MIN_LENGTH} תווים`, ok: (p) => p.length >= MIN_LENGTH },
  { key: "upper", label: "אות גדולה באנגלית (A-Z)", ok: (p) => /[A-Z]/.test(p) },
  { key: "lower", label: "אות קטנה באנגלית (a-z)", ok: (p) => /[a-z]/.test(p) },
  { key: "digit", label: "ספרה אחת לפחות (0-9)", ok: (p) => /[0-9]/.test(p) },
];

export function passwordIsStrong(p: string): boolean {
  return PASSWORD_RULES.every((r) => r.ok(p));
}

export function emailLooksValid(e: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e.trim());
}
