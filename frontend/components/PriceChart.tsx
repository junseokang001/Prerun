"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { TabButton } from "@/components/Motion";
import type { Bar, Explain, Line } from "@/lib/types";
import { price as fmtPrice } from "@/lib/format";

type Tool = "cursor" | "trend" | "hline" | "erase";
type Drawing =
  | { id: string; type: "h"; price: number }
  | { id: string; type: "t"; t1: string; p1: number; t2: string; p2: number };

const RANGES = [
  { id: "1d", label: "1일" },
  { id: "1w", label: "1주" },
  { id: "1m", label: "1달" },
  { id: "3m", label: "3달" },
  { id: "1y", label: "1년" },
];

export default function PriceChart({
  bars,
  series,
  lines,
  currency,
  range,
  onRange,
  explains,
  onExplain,
  storageKey,
}: {
  bars: Bar[];
  series: {
    ma5?: (number | null)[];
    ma20?: (number | null)[];
    ma60?: (number | null)[];
    bb_upper?: (number | null)[];
    bb_mid?: (number | null)[];
    bb_lower?: (number | null)[];
    rsi?: (number | null)[];
    macd?: (number | null)[];
    macd_signal?: (number | null)[];
    macd_hist?: (number | null)[];
  };
  lines: Line[];
  currency: string;
  range: string;
  onRange: (range: string) => void;
  explains: Record<string, Explain>;
  onExplain: (item: Explain) => void;
  storageKey: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(360);
  const [show, setShow] = useState({ ma: true, bb: false, rsi: false, macd: false, auto: true });
  const [tool, setTool] = useState<Tool>("cursor");
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [draft, setDraft] = useState<Drawing | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [chartShown, setChartShown] = useState(true);
  const reduceMotion = useReducedMotion();
  const rangeFadeReady = useRef(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      setDrawings(raw ? (JSON.parse(raw) as Drawing[]) : []);
    } catch {
      setDrawings([]);
    }
    setDraft(null);
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(drawings));
  }, [drawings, storageKey]);

  useEffect(() => {
    if (!rangeFadeReady.current) {
      rangeFadeReady.current = true;
      return;
    }
    if (reduceMotion) {
      setChartShown(true);
      return;
    }
    setChartShown(false);
    const timer = window.setTimeout(() => setChartShown(true), 40);
    return () => window.clearTimeout(timer);
  }, [range, reduceMotion]);

  useEffect(() => {
    const node = wrapRef.current;
    if (!node) return;
    const observer = new ResizeObserver(() => setWidth(node.clientWidth));
    observer.observe(node);
    setWidth(node.clientWidth);
    return () => observer.disconnect();
  }, []);

  const height = (show.rsi ? 78 : 0) + (show.macd ? 78 : 0) + 292;

  const layout = useMemo(() => {
    const pad = { l: 8, r: 58, t: 12, b: 22 };
    const volumeH = 54;
    const osc = (show.rsi ? 78 : 0) + (show.macd ? 78 : 0);
    const priceH = height - pad.t - pad.b - volumeH - osc;
    return { pad, volumeH, priceH, osc };
  }, [height, show.macd, show.rsi]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || bars.length < 2) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    drawChart(ctx, {
      bars,
      series,
      lines: [
        ...lines.filter((line) => line.id.startsWith("plan-")),
        ...(show.auto ? lines.filter((line) => !line.id.startsWith("plan-")) : []),
      ],
      drawings,
      draft,
      width,
      height,
      layout,
      show,
      hover,
      currency,
    });
  }, [bars, currency, draft, drawings, height, hover, layout, lines, series, show, width]);

  function xOf(index: number) {
    const inner = width - layout.pad.l - layout.pad.r;
    return layout.pad.l + (index + 0.5) * (inner / bars.length);
  }
  function indexOf(x: number) {
    const inner = width - layout.pad.l - layout.pad.r;
    const slot = inner / bars.length;
    return Math.max(0, Math.min(bars.length - 1, Math.floor((x - layout.pad.l) / slot)));
  }
  function priceOf(y: number) {
    const highs = bars.map((bar) => bar.h);
    const lows = bars.map((bar) => bar.l);
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    const span = max - min || 1;
    const pad = span * 0.08;
    const top = max + pad;
    const bot = min - pad;
    return top - ((y - layout.pad.t) / layout.priceH) * (top - bot);
  }

  function pointer(event: React.PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function onPointer(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!bars.length) return;
    const { x, y } = pointer(event);
    const index = indexOf(x);
    setHover(index);
    if (tool === "cursor" || y > layout.pad.t + layout.priceH) return;
    const level = priceOf(y);
    if (tool === "hline") {
      setDrawings((prev) => [...prev, { id: `h-${Date.now()}`, type: "h", price: level }]);
      setTool("cursor");
    } else if (tool === "trend") {
      const bar = bars[index];
      if (!draft) {
        setDraft({ id: "draft", type: "t", t1: bar.t, p1: level, t2: bar.t, p2: level });
      } else if (draft.type === "t") {
        setDrawings((prev) => [...prev, { ...draft, id: `t-${Date.now()}`, t2: bar.t, p2: level }]);
        setDraft(null);
        setTool("cursor");
      }
    } else if (tool === "erase") {
      setDrawings((prev) => prev.filter((item) => !nearDrawing(item, bars, xOf, level, index)));
    }
  }

  const hoverBar = hover != null ? bars[hover] : null;

  return (
    <div>
      <div className="flex gap-1.5 overflow-x-auto pb-3">
        {RANGES.map((item) => (
          <TabButton key={item.id} active={range === item.id} layoutId="chart-range" idleClass="bg-[#f2f4f6]" onClick={() => onRange(item.id)}>
            {item.label}
          </TabButton>
        ))}
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        <Toggle name="이평선" on={show.ma} set={() => setShow((s) => ({ ...s, ma: !s.ma }))} info={() => onExplain(explains.ma)} />
        <Toggle name="볼린저" on={show.bb} set={() => setShow((s) => ({ ...s, bb: !s.bb }))} info={() => onExplain(explains.bollinger)} />
        <Toggle name="RSI" on={show.rsi} set={() => setShow((s) => ({ ...s, rsi: !s.rsi }))} info={() => onExplain(explains.rsi)} />
        <Toggle name="MACD" on={show.macd} set={() => setShow((s) => ({ ...s, macd: !s.macd }))} info={() => onExplain(explains.macd)} />
        <Toggle name="자동선" on={show.auto} set={() => setShow((s) => ({ ...s, auto: !s.auto }))} info={() => onExplain(explains.ma)} />
        <button type="button" onClick={() => onExplain(explains.obv)} className="rounded-full bg-[#f2f4f6] px-3 py-1.5 text-[13px] font-semibold text-sub">
          OBV 설명
        </button>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {(
          [
            ["cursor", "보기"],
            ["trend", "추세선"],
            ["hline", "수평선"],
            ["erase", "지우기"],
          ] as [Tool, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              setTool(id);
              setDraft(null);
            }}
            className={`rounded-xl px-3 py-1.5 text-[13px] font-semibold transition duration-300 ease-out ${
              tool === id ? "bg-[#e8f3ff] text-down" : "text-sub hover:bg-[#f2f4f6]"
            }`}
          >
            {label}
          </button>
        ))}
        <button type="button" onClick={() => setDrawings([])} className="rounded-xl px-3 py-1.5 text-[13px] font-semibold text-sub">
          내 선 모두 삭제
        </button>
      </div>
      <p className="mb-2 text-[12px] text-sub">
        {tool === "trend" ? "추세선은 차트에서 두 점을 차례로 누르세요." : tool === "hline" ? "수평선은 가격 위치를 한 번 누르세요." : "캔들을 누르면 그 봉의 값이 위에 나옵니다."}
      </p>
      {hoverBar && (
        <p className="num mb-2 text-[12px] text-[#333d4b]">
          {hoverBar.t} · 시 {fmtPrice(hoverBar.o, currency)} 고 {fmtPrice(hoverBar.h, currency)} 저 {fmtPrice(hoverBar.l, currency)} 종 {fmtPrice(hoverBar.c, currency)}
        </p>
      )}
      <div ref={wrapRef} className={`transition-opacity duration-300 ease-out ${chartShown ? "opacity-100" : "opacity-0"}`}>
        {bars.length < 2 ? (
          <p className="rounded-2xl bg-[#f7f8fa] px-4 py-10 text-center text-[14px] text-sub">이 구간 봉이 없습니다.</p>
        ) : (
          <canvas
            ref={canvasRef}
            onPointerDown={onPointer}
            onPointerMove={(event) => {
              if (tool !== "cursor") return;
              const { x } = pointer(event);
              setHover(indexOf(x));
            }}
            onPointerLeave={() => setHover(null)}
            className="w-full touch-none"
          />
        )}
      </div>
      {lines.filter((line) => line.explain).length > 0 && (
        <div className="mt-3 flex flex-col gap-2">
          {lines
            .filter((line) => line.explain)
            .map((line) => (
              <button
                key={line.id}
                type="button"
                onClick={() => line.explain && onExplain(line.explain)}
                className="rounded-2xl bg-[#f7f8fa] px-3 py-2 text-left text-[13px] font-medium leading-relaxed transition hover:bg-[#eef1f4]"
              >
                {line.label}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

function Toggle({ name, on, set, info }: { name: string; on: boolean; set: () => void; info: () => void }) {
  return (
    <span className={`inline-flex items-center rounded-full ${on ? "bg-[#e8f3ff]" : "bg-[#f2f4f6]"}`}>
      <button type="button" onClick={set} className={`px-3 py-1.5 text-[13px] font-semibold ${on ? "text-down" : "text-sub"}`}>
        {on ? "● " : "○ "}
        {name}
      </button>
      <button type="button" onClick={info} className="pr-2.5 text-[12px] font-semibold text-sub" aria-label={`${name} 설명`}>
        설명
      </button>
    </span>
  );
}

function nearDrawing(item: Drawing, bars: Bar[], xOf: (i: number) => number, price: number, index: number) {
  if (item.type === "h") return Math.abs(item.price - price) / price < 0.012;
  const i1 = Math.max(0, bars.findIndex((bar) => bar.t === item.t1));
  const i2 = Math.max(0, bars.findIndex((bar) => bar.t === item.t2));
  return Math.abs(index - i1) < 2 || Math.abs(index - i2) < 2 || Math.abs(item.p1 - price) / price < 0.01;
}

function drawChart(
  ctx: CanvasRenderingContext2D,
  opts: {
    bars: Bar[];
    series: {
      ma5?: (number | null)[];
      ma20?: (number | null)[];
      ma60?: (number | null)[];
      bb_upper?: (number | null)[];
      bb_mid?: (number | null)[];
      bb_lower?: (number | null)[];
      rsi?: (number | null)[];
      macd?: (number | null)[];
      macd_signal?: (number | null)[];
      macd_hist?: (number | null)[];
    };
    lines: Line[];
    drawings: Drawing[];
    draft: Drawing | null;
    width: number;
    height: number;
    layout: { pad: { l: number; r: number; t: number; b: number }; volumeH: number; priceH: number };
    show: { ma: boolean; bb: boolean; rsi: boolean; macd: boolean };
    hover: number | null;
    currency: string;
  },
) {
  const { bars, series, width, layout, show, hover, currency } = opts;
  const { pad, priceH, volumeH } = layout;
  const highs = bars.map((bar) => bar.h);
  const lows = bars.map((bar) => bar.l);
  let max = Math.max(...highs);
  let min = Math.min(...lows);
  const span = max - min || 1;
  max += span * 0.08;
  min -= span * 0.08;
  const inner = width - pad.l - pad.r;
  const slot = inner / bars.length;
  const xOf = (i: number) => pad.l + (i + 0.5) * slot;
  const yOf = (p: number) => pad.t + ((max - p) / (max - min)) * priceH;
  const volMax = Math.max(...bars.map((bar) => bar.v), 1);

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, opts.height);

  ctx.strokeStyle = "#f2f4f6";
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i++) {
    const y = pad.t + (priceH * i) / 3;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(width - pad.r, y);
    ctx.stroke();
    const value = max - ((max - min) * i) / 3;
    ctx.fillStyle = "#8b95a1";
    ctx.font = "11px Pretendard, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(fmtPrice(value, currency).replace("원", ""), width - pad.r + 6, y + 4);
  }

  if (show.bb) {
    stroke(ctx, series.bb_upper, "#c4b5fd", xOf, yOf);
    stroke(ctx, series.bb_lower, "#c4b5fd", xOf, yOf);
  }
  opts.lines.forEach((line) => {
    if (line.type === "horizontal" && line.price) {
      const plan = line.id.startsWith("plan-");
      ctx.strokeStyle = line.id.startsWith("plan-stop") ? "#3182f6" : line.id.startsWith("support") ? "#12b886" : "#f04452";
      ctx.lineWidth = plan ? 1.8 : 1;
      ctx.setLineDash(plan ? [6, 4] : [4, 4]);
      const y = yOf(line.price);
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(width - pad.r, y);
      ctx.stroke();
      ctx.setLineDash([]);
      if (plan) {
        const caption = line.id === "plan-stop" ? "손절" : line.id === "plan-target" ? "+7%" : "저항";
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = "12px Pretendard, sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(caption, pad.l + 6, y - 5);
      }
    }
    if (line.type === "segment" && line.t1 && line.t2 && line.p1 != null && line.p2 != null) {
      const i1 = bars.findIndex((bar) => bar.t === line.t1);
      const i2 = bars.findIndex((bar) => bar.t === line.t2);
      if (i1 >= 0 && i2 >= 0) {
        ctx.strokeStyle = "#12b886";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(xOf(i1), yOf(line.p1));
        ctx.lineTo(xOf(i2), yOf(line.p2));
        ctx.stroke();
      }
    }
  });
  const manual = opts.draft ? [...opts.drawings, opts.draft] : opts.drawings;
  manual.forEach((line) => {
    ctx.strokeStyle = "#191f28";
    ctx.lineWidth = 1.6;
    ctx.setLineDash([]);
    if (line.type === "h") {
      ctx.beginPath();
      ctx.moveTo(pad.l, yOf(line.price));
      ctx.lineTo(width - pad.r, yOf(line.price));
      ctx.stroke();
    } else {
      const i1 = Math.max(0, bars.findIndex((bar) => bar.t === line.t1));
      const i2 = Math.max(i1, bars.findIndex((bar) => bar.t === line.t2));
      ctx.beginPath();
      ctx.moveTo(xOf(i1), yOf(line.p1));
      ctx.lineTo(xOf(i2), yOf(line.p2));
      ctx.stroke();
    }
  });

  bars.forEach((bar, i) => {
    const up = bar.c >= bar.o;
    ctx.strokeStyle = up ? "#f04452" : "#3182f6";
    ctx.fillStyle = up ? "#f04452" : "#3182f6";
    const x = xOf(i);
    ctx.beginPath();
    ctx.moveTo(x, yOf(bar.h));
    ctx.lineTo(x, yOf(bar.l));
    ctx.stroke();
    const top = yOf(Math.max(bar.o, bar.c));
    const bot = yOf(Math.min(bar.o, bar.c));
    const body = Math.max(1, bot - top);
    ctx.fillRect(x - Math.max(1.2, slot * 0.32), top, Math.max(2.4, slot * 0.64), body);
  });

  if (show.ma) {
    stroke(ctx, series.ma5, "#f59f00", xOf, yOf);
    stroke(ctx, series.ma20, "#3182f6", xOf, yOf);
    stroke(ctx, series.ma60, "#8b95a1", xOf, yOf);
  }

  const volTop = pad.t + priceH + 8;
  bars.forEach((bar, i) => {
    const up = bar.c >= bar.o;
    ctx.globalAlpha = 0.45;
    ctx.fillStyle = up ? "#f04452" : "#3182f6";
    const h = (bar.v / volMax) * (volumeH - 10);
    ctx.fillRect(xOf(i) - Math.max(1, slot * 0.3), volTop + volumeH - h, Math.max(2, slot * 0.6), h);
    ctx.globalAlpha = 1;
  });

  let oscTop = volTop + volumeH;
  if (show.rsi && series.rsi) {
    drawOsc(ctx, series.rsi, pad.l, oscTop, inner, 70, 0, 100, xOf, "#191f28", false);
    ctx.fillStyle = "rgba(255,176,32,0.13)";
    const y43 = oscTop + ((100 - 60) / 100) * 64;
    const y60 = oscTop + ((100 - 43) / 100) * 64;
    ctx.fillRect(pad.l, Math.min(y43, y60), inner, Math.abs(y60 - y43));
    oscTop += 78;
  }
  if (show.macd && series.macd_hist) {
    const values = series.macd_hist.map((v) => v ?? 0);
    const peak = Math.max(...values.map((v) => Math.abs(v)), 0.0001);
    values.forEach((value, i) => {
      ctx.fillStyle = value >= 0 ? "#f04452" : "#3182f6";
      const mid = oscTop + 32;
      const h = (value / peak) * 26;
      ctx.fillRect(xOf(i) - 1, h > 0 ? mid - h : mid, 2.2, Math.abs(h));
    });
    stroke(ctx, series.macd, "#191f28", xOf, (v) => oscTop + 32 - (v / peak) * 26);
    stroke(ctx, series.macd_signal, "#f59f00", xOf, (v) => oscTop + 32 - (v / peak) * 26);
  }

  if (hover != null) {
    ctx.strokeStyle = "#d1d6db";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(xOf(hover), pad.t);
    ctx.lineTo(xOf(hover), pad.t + priceH);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.fillStyle = "#8b95a1";
  ctx.font = "11px Pretendard, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(bars[0].t.slice(5, 16), pad.l, opts.height - 6);
  ctx.textAlign = "right";
  ctx.fillText(bars[bars.length - 1].t.slice(5, 16), width - pad.r, opts.height - 6);
}

function stroke(
  ctx: CanvasRenderingContext2D,
  values: (number | null)[] | undefined,
  color: string,
  xOf: (i: number) => number,
  yOf: (v: number) => number,
) {
  if (!values) return;
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.3;
  let started = false;
  values.forEach((value, i) => {
    if (value == null || Number.isNaN(value)) return;
    const x = xOf(i);
    const y = yOf(value);
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function drawOsc(
  ctx: CanvasRenderingContext2D,
  values: (number | null)[],
  left: number,
  top: number,
  width: number,
  _right: number,
  min: number,
  max: number,
  xOf: (i: number) => number,
  color: string,
  _fill: boolean,
) {
  ctx.strokeStyle = "#f2f4f6";
  [30, 70].forEach((level) => {
    const y = top + ((max - level) / (max - min)) * 64;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + width, y);
    ctx.stroke();
  });
  stroke(ctx, values, color, xOf, (v) => top + ((max - v) / (max - min)) * 64);
}
