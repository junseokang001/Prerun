export function price(value: number | null | undefined, currency: string) {
  if (value == null || Number.isNaN(value)) return "—";
  if (currency === "USD") {
    return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

export function pct(value: number | null | undefined, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  const n = value * 100;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

export function signed(value: number | null | undefined, currency: string) {
  if (value == null || Number.isNaN(value)) return "—";
  const core = price(Math.abs(value), currency);
  if (value > 0) return `+${core}`;
  if (value < 0) return `-${core}`;
  return core;
}

export function direction(value: number | null | undefined): "up" | "down" | "flat" {
  if (value == null || Math.abs(value) < 0.0000001) return "flat";
  return value > 0 ? "up" : "down";
}

export function when(iso: string | null | undefined) {
  if (!iso) return "시각 없음";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 16);
  const now = Date.now();
  const diff = Math.max(0, now - date.getTime());
  const min = Math.floor(diff / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function kstClock(iso: string | null | undefined) {
  const date = iso ? new Date(iso) : new Date();
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function qty(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString("ko-KR")}`;
}

export function marketLabel(market: string) {
  if (market === "KOSPI") return "코스피";
  if (market === "KOSDAQ") return "코스닥";
  if (market === "US") return "미국";
  return market;
}
