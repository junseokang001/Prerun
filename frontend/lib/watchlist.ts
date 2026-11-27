export type WatchItem = { symbol: string; savedAt: string };

const KEY = "prerun-watch";

export function readWatch(): WatchItem[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || "[]") as WatchItem[];
    return Array.isArray(parsed) ? parsed.filter((item) => item?.symbol && item?.savedAt) : [];
  } catch {
    return [];
  }
}

export function writeWatch(items: WatchItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
}
