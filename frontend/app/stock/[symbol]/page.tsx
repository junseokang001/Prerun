"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Disclaimer, Move, SentimentMark } from "@/components/Bits";
import WatchButton from "@/components/WatchButton";
import { readWatch, writeWatch } from "@/lib/watchlist";
import ExplainSheet from "@/components/ExplainSheet";
import { SoftSwap } from "@/components/Motion";
import PriceChart from "@/components/PriceChart";
import { marketLabel, pct, price, qty, when } from "@/lib/format";
import type { Explain, StockDetail } from "@/lib/types";

export default function StockPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [range, setRange] = useState("3m");
  const [data, setData] = useState<StockDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [explain, setExplain] = useState<Explain | null>(null);
  const [watched, setWatched] = useState(false);
  useEffect(() => {
    setWatched(readWatch().some((item) => item.symbol === symbol));
  }, [symbol]);
  function toggleWatch() {
    const current = readWatch();
    const next = current.some((item) => item.symbol === symbol)
      ? current.filter((item) => item.symbol !== symbol)
      : [{ symbol, savedAt: new Date().toISOString() }, ...current];
    writeWatch(next);
    setWatched(next.some((item) => item.symbol === symbol));
  }

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const response = await fetch(`/backend-api/stock/${encodeURIComponent(symbol)}?range=${range}`, { cache: "no-store" });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || "종목을 받지 못했습니다.");
        }
        const body = (await response.json()) as StockDetail;
        if (!stop) {
          setData(body);
          setError(null);
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "오류");
      } finally {
        if (!stop) setLoading(false);
      }
    };
    setLoading(true);
    load();
    const timer = setInterval(load, 45000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [range, symbol]);

  const off = data?.status === "demoted";

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-4 pb-16 pt-4 sm:px-6">
      <div className="mb-3 flex items-center justify-between">
        <Link href="/" className="text-[14px] font-semibold text-sub transition-colors duration-300 hover:text-ink">
          ← 프리런
        </Link>
        <div className="flex items-center gap-2">
          <WatchButton on={watched} onToggle={toggleWatch} />
          <span className="text-[13px] font-bold">PreRun</span>
        </div>
      </div>
      <SoftSwap id={data ? `ready-${symbol}` : error ? "error" : "loading"}>
      {loading && !data && (
        <div className="space-y-3">
          <div className="skel h-28 rounded-[28px]" />
          <div className="skel h-80 rounded-[28px]" />
        </div>
      )}
      {error && !data && <p className="rounded-[28px] bg-white p-5 text-[14px]">{error}</p>}
      {data && (
        <div className={off ? "turned-off" : ""}>
          <section className={`rounded-[28px] bg-white p-5 shadow-card ${off ? "opacity-80" : ""}`}>
            <div className="flex items-center gap-2">
              <span className={off ? "dot-off" : "dot-on"} />
              <p className="text-[12px] font-semibold text-sub">
                {off ? "타이밍 지남" : data.status === "candidate" ? "급등 예상 후보" : "후보 아님"} · {marketLabel(data.market)}
              </p>
            </div>
            <h1 className="mt-2 text-[26px] font-bold tracking-tight">{data.name}</h1>
            <p className="text-[13px] text-sub">{data.code}</p>
            <p className="num mt-3 text-[32px] font-bold leading-none">{price(data.price, data.currency)}</p>
            <Move value={data.change_pct} className="mt-1 text-[15px]" />
            <p className="mt-3 text-[12px] leading-relaxed text-sub">
              현재가 {data.price_source} · {data.price_time} · 지표 기준일 {data.signal_bar_date}
              {data.dropped_today ? " (장중이라 오늘 미완성 봉은 빼 둠)" : ""}
            </p>
            {off && data.demote_reason && (
              <p className="mt-3 rounded-2xl bg-[#f2f4f6] px-3 py-3 text-[13px] leading-relaxed">
                {data.demoted_at}부터 목록에서 내림. {data.demote_reason}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => setExplain(data.explain_score)} className="rounded-2xl bg-[#fff4e5] px-3 py-2 text-left text-[#b36b00]">
                <span className="block text-[11px] font-semibold">보정 확률</span>
                <span className="num block text-[22px] font-bold leading-none">
                  {data.calibrated_probability == null ? "없음" : `${(data.calibrated_probability * 100).toFixed(1)}%`}
                </span>
                <span className="mt-1 block text-[11px] font-medium leading-snug">
                  {data.bucket?.actual_hit_rate != null
                    ? `시험 적중 ${(data.bucket.actual_hit_rate * 100).toFixed(1)}% · ${data.bucket.n.toLocaleString("ko-KR")}건`
                    : "시험 적중 없음"}
                  {data.forecast?.ml?.baseline_hit_rate != null
                    ? ` · 기준선 ${(data.forecast.ml.baseline_hit_rate * 100).toFixed(1)}%`
                    : ""}
                </span>
              </button>
              {data.plan && (
                <>
                  <button type="button" onClick={() => setExplain(data.plan!.explain_stop)} className="rounded-full bg-[#e8f3ff] px-3 py-1.5 text-[13px] font-semibold text-down">
                    손절 {price(data.plan.stop, data.currency)}
                  </button>
                  <button type="button" onClick={() => setExplain(data.plan!.explain_target)} className="rounded-full bg-[#fff1f2] px-3 py-1.5 text-[13px] font-semibold text-up">
                    목표 {price(data.plan.target, data.currency)}
                  </button>
                </>
              )}
              <button type="button" onClick={() => setExplain(data.explain_timing)} className="rounded-full bg-[#f2f4f6] px-3 py-1.5 text-[13px] font-semibold">
                {data.timing.available ? `예상 ${data.timing.label} · ${(data.timing.probability * 100).toFixed(0)}%` : "시기 표본 없음"}
              </button>
            </div>
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-4 shadow-card">
            {data.chart_error && <p className="mb-3 text-[13px] text-sub">차트: {data.chart_error}</p>}
            <PriceChart
              bars={data.bars || []}
              series={data.indicator_series || {}}
              lines={data.lines || []}
              currency={data.currency}
              range={range}
              onRange={setRange}
              explains={data.indicator_explain}
              onExplain={setExplain}
              storageKey={`prerun-draw:${symbol}:${range}`}
            />
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">호가</h2>
            {data.orderbook.available ? (
              <OrderBook book={data.orderbook} currency={data.currency} />
            ) : (
              <p className="mt-2 text-[14px] leading-relaxed text-sub">데이터 없음. {data.orderbook.reason}</p>
            )}
            <h3 className="mt-5 text-[14px] font-bold">오늘 매수·매도 체결량</h3>
            <p className="mt-1 text-[14px] leading-relaxed text-sub">데이터 없음. {data.buy_sell.reason}</p>
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">투자자</h2>
            {data.investors.available && data.investors.rows.length > 0 ? (
              <>
                <p className="mt-1 text-[12px] leading-relaxed text-sub">{data.investors.ownership_note}</p>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[460px] text-left text-[13px]">
                    <thead className="text-sub">
                      <tr>
                        <th className="py-2 font-medium">날짜</th>
                        <th className="py-2 font-medium">외국인</th>
                        <th className="py-2 font-medium">기관</th>
                        <th className="py-2 font-medium">개인</th>
                        <th className="py-2 font-medium">외인소진율</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.investors.rows.map((row) => (
                        <tr key={row.date} className="border-t border-[#f2f4f6]">
                          <td className="py-2">{row.date.slice(5)}</td>
                          <td className={`num py-2 ${tone(row.foreign_net)}`}>{qty(row.foreign_net)}</td>
                          <td className={`num py-2 ${tone(row.institution_net)}`}>{qty(row.institution_net)}</td>
                          <td className={`num py-2 ${tone(row.individual_net)}`}>{qty(row.individual_net)}</td>
                          <td className="num py-2">{row.foreign_ratio == null ? "—" : `${row.foreign_ratio.toFixed(2)}%`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[12px] text-sub">기관·개인 지분율은 이 무료 API에 없습니다. 순매수 수량만 표시합니다.</p>
                {data.investors.source_url && (
                  <a href={data.investors.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[13px] font-semibold text-down">
                    네이버 원문
                  </a>
                )}
              </>
            ) : (
              <p className="mt-2 text-[14px] leading-relaxed text-sub">데이터 없음. {data.investors.reason}</p>
            )}
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">오늘 가격이 {data.why.direction}인 단서</h2>
            <p className="mt-2 text-[14px] leading-relaxed">{data.why.lead}</p>
            <ul className="mt-3 space-y-3">
              {data.why.factors.map((factor) => (
                <li key={factor.title} className="rounded-2xl bg-[#f7f8fa] px-3 py-3">
                  <p className="text-[14px] font-semibold">{factor.title}</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-[#333d4b]">{factor.detail}</p>
                  {factor.url && (
                    <a href={factor.url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[12px] font-semibold text-down">
                      {factor.source || "원문"}
                    </a>
                  )}
                </li>
              ))}
            </ul>
            {data.why.articles.length > 0 && (
              <ul className="mt-4 divide-y divide-[#f2f4f6]">
                {data.why.articles.map((article) => (
                  <li key={article.url} className="flex gap-3 py-3">
                    <SentimentMark sentiment={article.sentiment} onClick={() => setExplain(article.explain)} />
                    <div>
                      <a href={article.url} target="_blank" rel="noreferrer" className="text-[14px] font-semibold leading-snug hover:underline">
                        {article.title}
                      </a>
                      <p className="mt-1 text-[12px] text-sub">
                        {article.source} · {when(article.published_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">향후 전망</h2>
            <p className="mt-2 text-[14px] leading-relaxed">{data.forecast.headline}</p>
            <button type="button" onClick={() => setExplain(data.forecast.explain)} className="mt-3 text-left">
              <p className="text-[22px] font-bold">{data.forecast.timing.available ? data.forecast.timing.label : "날짜를 적지 않음"}</p>
              <p className="text-[13px] text-sub">
                {data.forecast.timing.detail} · 확률 {pct(data.forecast.timing.probability, 1)} · 표본 {data.forecast.timing.sample_n}건
              </p>
            </button>
            <ul className="mt-4 space-y-2">
              {data.forecast.timing.windows?.map((row) => (
                <li key={row.label}>
                  <div className="mb-1 flex justify-between text-[12px]">
                    <span>
                      {row.label}
                      {row.range_label ? ` · ${row.range_label}` : ""}
                    </span>
                    <span className="num">
                      {row.count}건 · {(row.probability * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#f2f4f6]">
                    <div className="h-full rounded-full bg-[#ffb020]" style={{ width: `${Math.min(100, row.probability * 100)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] leading-relaxed text-sub">{data.forecast.timing.bucket_note}</p>
            {data.forecast.ml.available && data.forecast.ml.probability != null && (
              <p className="mt-3 text-[13px] leading-relaxed">
                보정 확률 {((data.calibrated_probability ?? data.forecast.ml.probability ?? 0) * 100).toFixed(1)}%.
                {data.bucket?.actual_hit_rate != null
                  ? ` 검증에서 확률 ${data.bucket.label} ${data.bucket.n}건의 실제 적중률은 ${(data.bucket.actual_hit_rate * 100).toFixed(1)}%이고, 같은 구간 전체는 ${((data.forecast.ml.baseline_hit_rate || 0) * 100).toFixed(1)}%입니다.`
                  : ` 검증 전체 적중률은 ${((data.forecast.ml.baseline_hit_rate || 0) * 100).toFixed(1)}%입니다.`}
              </p>
            )}
          </section>

          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">확률을 움직인 숫자</h2>
            <p className="mt-1 text-[12px] leading-relaxed text-sub">값 하나만 학습 중앙값으로 바꿨을 때 확률이 얼마나 변하는지입니다.</p>
            <ul className="mt-2 divide-y divide-[#f2f4f6]">
              {(data.contributions || []).slice(0, 6).map((item) => (
                <li key={item.feature}>
                  <button type="button" onClick={() => setExplain(item.explain)} className="flex w-full items-center justify-between gap-3 py-3 text-left">
                    <span>
                      <span className="block text-[14px] font-semibold">{item.label}</span>
                      <span className="text-[12px] text-sub">{item.text}</span>
                    </span>
                    <span className={`num text-[14px] font-bold ${item.delta >= 0 ? "text-up" : "text-down"}`}>
                      {item.delta >= 0 ? "▲" : "▼"} {Math.abs(item.delta * 100).toFixed(1)}%p
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section className="mt-3 rounded-[28px] bg-white p-5 shadow-card">
            <h2 className="text-[16px] font-bold">기술 신호 (참고)</h2>
            <ul className="mt-2 divide-y divide-[#f2f4f6]">
              {data.signals.map((signal) => (
                <li key={signal.id}>
                  <button type="button" onClick={() => setExplain(signal.explain)} className="flex w-full items-center justify-between py-3 text-left">
                    <span>
                      <span className="block text-[14px] font-semibold">{signal.name}</span>
                      <span className="text-[12px] text-sub">{signal.fired ? "켜짐" : "꺼짐"}</span>
                    </span>
                    <span className="num text-[14px] font-bold">{signal.contribution.toFixed(1)}점</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <footer className="mt-6">
            <Disclaimer />
          </footer>
        </div>
      )}
      </SoftSwap>
      <ExplainSheet item={explain} onClose={() => setExplain(null)} />
    </main>
  );
}

function tone(value: number | null) {
  if (value == null || value === 0) return "text-sub";
  return value > 0 ? "text-up" : "text-down";
}

function OrderBook({
  book,
  currency,
}: {
  book: StockDetail["orderbook"];
  currency: string;
}) {
  const max = Math.max(1, ...book.sells.map((row) => row.qty), ...book.buys.map((row) => row.qty));
  return (
    <div className="mt-3">
      <div className="mb-2 flex justify-between text-[12px] text-sub">
        <span>매도대기 {book.total_sell == null ? "" : book.total_sell.toLocaleString("ko-KR")}</span>
        <span>매수대기 {book.total_buy == null ? "" : book.total_buy.toLocaleString("ko-KR")}</span>
      </div>
      <ul>
        {[...book.sells].reverse().map((row) => (
          <QuoteRow key={`s-${row.price}`} price={row.price} qty={row.qty} max={max} side="sell" currency={currency} />
        ))}
      </ul>
      <ul className="mt-1 border-t border-[#f2f4f6] pt-1">
        {book.buys.map((row) => (
          <QuoteRow key={`b-${row.price}`} price={row.price} qty={row.qty} max={max} side="buy" currency={currency} />
        ))}
      </ul>
      {book.source_url && (
        <a href={book.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-[13px] font-semibold text-down">
          네이버 원문
        </a>
      )}
    </div>
  );
}

function QuoteRow({
  price: level,
  qty: size,
  max,
  side,
  currency,
}: {
  price: number;
  qty: number;
  max: number;
  side: "buy" | "sell";
  currency: string;
}) {
  return (
    <li className="relative flex items-center justify-between py-1 text-[13px]">
      <span className="absolute inset-y-0.5 right-0 rounded-md bg-[#f2f4f6]" style={{ width: `${(size / max) * 46}%` }} />
      <span className={`num relative font-semibold ${side === "sell" ? "text-down" : "text-up"}`}>{price(level, currency)}</span>
      <span className="num relative text-sub">{Math.round(size).toLocaleString("ko-KR")}</span>
    </li>
  );
}
