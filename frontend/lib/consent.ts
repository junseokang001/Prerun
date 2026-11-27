const KEY = "prerun-consent";

type StoredConsent = { agreed?: boolean; agreedAt?: string };

export function readConsent(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as StoredConsent;
    return parsed?.agreed === true;
  } catch {
    return false;
  }
}

export function writeConsent() {
  const payload: StoredConsent = { agreed: true, agreedAt: new Date().toISOString() };
  localStorage.setItem(KEY, JSON.stringify(payload));
}
