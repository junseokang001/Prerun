"use client";

import { direction, pct, price, signed } from "@/lib/format";

export function Move({
  value,
  currency,
  withPrice = false,
  className = "",
}: {
  value: number | null | undefined;
  currency?: string;
  withPrice?: boolean;
  className?: string;
}) {
  const dir = direction(value);
  const color = dir === "up" ? "text-up" : dir === "down" ? "text-down" : "text-sub";
  const mark = dir === "up" ? "▲" : dir === "down" ? "▼" : "—";
  const text = withPrice && currency ? `${signed(value, currency)}  ${pct(value)}` : pct(value);
  return (
    <span className={`num inline-flex items-center gap-1 font-semibold ${color} ${className}`}>
      <span aria-hidden>{mark}</span>
      {withPrice && currency ? (
        <>
          <span>{signed(value, currency)}</span>
          <span>{pct(dir === "flat" ? 0 : value)}</span>
        </>
      ) : (
        text
      )}
    </span>
  );
}

export function SentimentMark({
  sentiment,
  onClick,
}: {
  sentiment: "positive" | "negative" | "neutral";
  onClick?: () => void;
}) {
  const map = {
    positive: { mark: "▲", cls: "text-up" },
    negative: { mark: "▼", cls: "text-down" },
    neutral: { mark: "—", cls: "text-sub" },
  }[sentiment];
  return (
    <button
      type="button"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick?.();
      }}
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#f2f4f6] text-[14px] font-bold ${map.cls}`}
      aria-label="뉴스 심리 설명"
    >
      {map.mark}
    </button>
  );
}

export function Spark({ values, up }: { values: number[]; up: boolean }) {
  if (!values || values.length < 2) return null;
  const w = 88;
  const h = 36;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * w;
      const y = h - 3 - ((value - min) / (max - min || 1)) * (h - 6);
      return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <path d={d} fill="none" stroke={up ? "#f04452" : "#3182f6"} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <p className={`leading-relaxed text-sub ${compact ? "text-[12px]" : "text-[13px]"}`}>
      프리런은 투자 조언이 아닙니다. 확률은 과거 데이터에서 센 빈도이고, 예측은 빗나갈 수 있습니다. 손실이 날 수 있습니다.
    </p>
  );
}
