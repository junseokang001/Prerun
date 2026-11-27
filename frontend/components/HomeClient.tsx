"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Disclaimer, Move, SentimentMark, Spark } from "@/components/Bits";
import ExplainSheet from "@/components/ExplainSheet";
import { FadeIn, SoftSwap, TabButton } from "@/components/Motion";
import FlowList from "@/components/FlowList";
import PageDeck, { type DeckPage } from "@/components/PageDeck";
import WatchButton from "@/components/WatchButton";
import { kstClock, marketLabel, pct, price, when } from "@/lib/format";
import type { Card, Explain, IndexItem, LedgerWindow, NewsItem, Screener, SectorPayload, Tracked } from "@/lib/types";
import { readWatch, writeWatch, type WatchItem } from "@/lib/watchlist";

const MARKETS = [
  { id: "KR", label: "국내" },
  { id: "KOSPI", label: "코스피" },
  { id: "KOSDAQ", label: "코스닥" },
  { id: "US", label: "미국" },
];

export default function HomeClient() {
  const router = useRouter();
  const [screen, setScreen] = useState<Screener | null>(null);
  const [indices, setIndices] = useState<IndexItem[]>([]);
  const [indexAt, setIndexAt] = useState<string | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [newsMode, setNewsMode] = useState("규칙");
  const [market, setMarket] = useState("KR");
  const [minPrice, setMinPrice] = useState("");
  const [minValue, setMinValue] = useState("");
  const [explain, setExplain] = useState<Explain | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [watch, setWatch] = useState<WatchItem[]>([]);
  const [sectors, setSectors] = useState<SectorPayload | null>(null);
  const [wide, setWide] = useState(false);

  async function loadScreen() {
    const response = await fetch("/backend-api/screener", { cache: "no-store" });
    if (!response.ok) throw new Error("스크리너를 받지 못했습니다.");
    setScreen((await response.json()) as Screener);
  }
  async function loadIndices() {
    const response = await fetch("/backend-api/indices", { cache: "no-store" });
    if (!response.ok) throw new Error("지수를 받지 못했습니다.");
    const body = await response.json();
    setIndices(body.items || []);
    setIndexAt(body.updated_at);
  }
  async function loadNews() {
    const response = await fetch("/backend-api/news", { cache: "no-store" });
    if (!response.ok) throw new Error("뉴스를 받지 못했습니다.");
    const body = await response.json();
    setNews(body.items || []);
    setNewsMode(body.mode || "규칙");
    setNewsError(body.items?.length ? null : (body.errors || []).join(" / ") || "뉴스가 없습니다.");
  }

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        await loadScreen();
        if (!stop) setFailed(null);
      } catch (error) {
        if (!stop) setFailed(error instanceof Error ? error.message : "연결 실패");
      }
    };
    tick();
    const slow = setInterval(tick, 60000);
    const fast = setInterval(() => {
      loadIndices().catch(() => setIndices([]));
    }, 45000);
    const newsTimer = setInterval(() => {
      loadNews().catch((error) => setNewsError(error instanceof Error ? error.message : "뉴스 실패"));
    }, 180000);
    loadIndices().catch(() => undefined);
    loadNews().catch((error) => setNewsError(error instanceof Error ? error.message : "뉴스 실패"));
    setWatch(readWatch());
    const media = window.matchMedia("(min-width: 768px)");
    const apply = () => setWide(media.matches);
    apply();
    media.addEventListener("change", apply);
    const sectorTimer = setInterval(() => {
      fetch("/backend-api/sectors", { cache: "no-store" })
        .then((response) => response.json())
        .then((body) => setSectors(body as SectorPayload))
        .catch(() => setSectors({ status: "error", error: "업종 화면을 받지 못했습니다.", industries: [], themes: [] }));
    }, 180000);
    fetch("/backend-api/sectors", { cache: "no-store" })
      .then((response) => response.json())
      .then((body) => setSectors(body as SectorPayload))
      .catch(() => setSectors({ status: "error", error: "업종 화면을 받지 못했습니다.", industries: [], themes: [] }));
    return () => {
      stop = true;
      clearInterval(slow);
      clearInterval(fast);
      clearInterval(newsTimer);
      clearInterval(sectorTimer);
      media.removeEventListener("change", apply);
    };
  }, []);

  function toggleWatch(symbol: string) {
    setWatch((prev) => {
      const next = prev.some((item) => item.symbol === symbol)
        ? prev.filter((item) => item.symbol !== symbol)
        : [{ symbol, savedAt: new Date().toISOString() }, ...prev];
      writeWatch(next);
      return next;
    });
  }

  const unitValue = market === "US" ? 1_000_000 : 100_000_000;
  const filtered = useMemo(() => {
    const match = (card: Card) => {
      if (market === "KR" && card.market === "US") return false;
      if (market !== "KR" && card.market !== market) return false;
      const floor = Number(minPrice);
      if (minPrice && !Number.isNaN(floor) && card.price < floor) return false;
      const valueFloor = Number(minValue);
      if (minValue && !Number.isNaN(valueFloor) && card.value20 != null && card.value20 < valueFloor * unitValue) return false;
      return true;
    };
    return {
      candidates: (screen?.candidates || []).filter(match),
      demoted: (screen?.demoted || []).filter(match),
    };
  }, [market, minPrice, minValue, screen, unitValue]);

  const heroes = filtered.candidates.slice(0, 8);
  const warming = !screen || screen.status === "warming";

  const tracked = screen?.tracked || [];
  const watchRows = watch
    .map((item) => ({ saved: item, row: tracked.find((stock) => stock.symbol === item.symbol) }))
    .filter((item) => item.row);
  const pageSize = wide ? 4 : 2;
  const heroPages = chunk(heroes, pageSize);
  const pastPages = chunk(filtered.demoted, wide ? 6 : 4);
  const watchPages = chunk(watchRows, pageSize);
  const industryPages = chunk(sectors?.industries || [], wide ? 3 : 2);
  const themePages = chunk(sectors?.themes || [], wide ? 3 : 2);

  const pages: DeckPage[] = [];
  (heroPages.length ? heroPages : [[]]).forEach((group, index, all) => {
    pages.push({
      id: `candidates-${index}`,
      title: `급등 예상 후보 ${index + 1}/${all.length}`,
      node: (
        <div>
          <p className="mb-3 text-[13px] leading-relaxed text-sub">
            이미 오른 종목은 빼 둡니다. 검증 기준을 넘긴 보정 확률만, 높은 순으로 보여 줍니다.
            {screen?.status === "ready" ? ` 통과 ${filtered.candidates.length}개.` : ""}
            {screen?.risk?.count ? ` 위험 종목 ${screen.risk.count}개 제외.` : ""}
            {screen?.regime?.weak ? " 약세장에서는 기준을 올리고 최대 3개만 보여 줍니다." : ""}
            {heroes.length < 4 ? " 4개가 안 되면 있는 것만 보여 줍니다." : ""}
          </p>
          <div className="mb-3 flex flex-wrap gap-2">
            {MARKETS.map((item) => (
              <TabButton key={item.id} active={market === item.id} layoutId={`market-tab-${index}`} onClick={() => setMarket(item.id)}>
                {item.label}
              </TabButton>
            ))}
          </div>
          <SoftSwap id={`${warming ? "warming" : group.length === 0 ? "empty" : "list"}-${market}`}>
          {warming ? (
            <div className="grid gap-3 sm:grid-cols-2">{[0, 1].map((i) => <div key={i} className="skel h-40 rounded-[28px]" />)}</div>
          ) : group.length === 0 ? (
            <div className="rounded-[28px] bg-white px-5 py-10 text-center shadow-card">
              <p className="font-semibold">지금은 조건을 통과한 후보가 없습니다.</p>
              <p className="mt-2 text-[13px] text-sub">기준을 낮춰 채우지 않습니다.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {group.map((card, cardIndex) => (
                <FadeIn key={card.symbol} delay={Math.min(cardIndex, 4) * 0.045}>
                  <CandidateCard
                    card={card}
                    watched={watch.some((item) => item.symbol === card.symbol)}
                    onWatch={() => toggleWatch(card.symbol)}
                    onOpen={() => router.push(`/stock/${encodeURIComponent(card.symbol)}`)}
                    onExplain={setExplain}
                  />
                </FadeIn>
              ))}
            </div>
          )}
          </SoftSwap>
        </div>
      ),
    });
  });
  (watchPages.length ? watchPages : [[]]).forEach((group, index, all) => {
    pages.push({
      id: `watch-${index}`,
      title: `관심 ${index + 1}/${all.length}`,
      node: (
        <div className="space-y-3">
          <p className="text-[13px] text-sub">이 브라우저에만 저장됩니다. 로그인 없습니다.</p>
          {group.length === 0 ? (
            <p className="rounded-[28px] bg-white px-5 py-8 text-[14px] text-sub">별표를 누르면 여기에 쌓입니다.</p>
          ) : (
            group.map(({ saved, row }, rowIndex) =>
              row ? (
                <FadeIn as="article" key={row.symbol} delay={Math.min(rowIndex, 4) * 0.04} className={`rounded-[28px] bg-white p-4 shadow-card ${row.status === "demoted" ? "turned-off" : ""}`}>
                  <div className="flex items-start justify-between gap-3">
                    <button type="button" onClick={() => router.push(`/stock/${encodeURIComponent(row.symbol)}`)} className="min-w-0 flex-1 text-left">
                      <div className="flex items-center gap-2">
                        <span className={row.status === "candidate" ? "dot-on" : "dot-off"} />
                        <p className="font-bold">{row.name}</p>
                      </div>
                      <p className="mt-1 text-[12px] text-sub">
                        {row.code} · {row.status === "candidate" ? "후보" : row.status === "demoted" ? "타이밍 지남" : "후보 아님"} · 저장 {when(saved.savedAt)}
                      </p>
                      <p className="num mt-2 text-[18px] font-bold">{price(row.price, row.currency)}</p>
                      <Move value={row.change_pct} className="text-[13px]" />
                      <p className="mt-1 text-[12px] text-sub">보정 확률 {row.probability == null ? "—" : `${(row.probability * 100).toFixed(1)}%`}</p>
                    </button>
                    <WatchButton on onToggle={() => toggleWatch(row.symbol)} />
                  </div>
                </FadeIn>
              ) : null,
            )
          )}
        </div>
      ),
    });
  });
  (industryPages.length ? industryPages : [[]]).forEach((group, index, all) => {
    pages.push({
      id: `industry-${index}`,
      title: `업종 흐름 ${index + 1}/${all.length}`,
      node: (
        <SoftSwap id={sectors?.status === "error" ? "error" : !sectors || sectors.status === "warming" ? "warming" : "ready"}>
          {sectors?.status === "error" ? (
            <p className="rounded-[28px] bg-white px-5 py-8 text-[14px]">데이터 없음. {sectors.error}</p>
          ) : !sectors || sectors.status === "warming" ? (
            <div className="skel h-40 rounded-[28px]" />
          ) : (
            <FlowList groups={group} empty="업종 목록이 비어 있습니다." />
          )}
        </SoftSwap>
      ),
    });
  });
  (themePages.length ? themePages : [[]]).forEach((group, index, all) => {
    pages.push({
      id: `theme-${index}`,
      title: `테마 흐름 ${index + 1}/${all.length}`,
      node: <FlowList groups={group} empty={sectors?.status === "ready" ? "테마가 없습니다." : "테마를 받는 중입니다."} />,
    });
  });
  (pastPages.length ? pastPages : [[]]).forEach((group, index, all) => {
    pages.push({
      id: `past-${index}`,
      title: `타이밍 지남 ${index + 1}/${all.length}`,
      node: (
        <div className="turned-off overflow-hidden rounded-[28px] bg-white shadow-card">
          <p className="px-5 pt-4 text-[13px] text-sub">불이 꺼진 종목입니다. 급등이 끝났거나 예상 구간이 지났거나 확률이 기준 아래로 내려갔습니다.</p>
          {group.length === 0 ? (
            <p className="px-5 py-8 text-[14px]">최근 40일 안에 후보였다가 빠진 종목이 없습니다.</p>
          ) : (
            group.map((card) => (
              <ListRow
                key={card.symbol}
                card={card}
                off
                watched={watch.some((item) => item.symbol === card.symbol)}
                onWatch={() => toggleWatch(card.symbol)}
                onOpen={() => router.push(`/stock/${encodeURIComponent(card.symbol)}`)}
                onExplain={setExplain}
              />
            ))
          )}
        </div>
      ),
    });
  });
  if (screen?.backtest) {
    pages.push({
      id: "validation",
      title: "검증",
      node: (
        <section className="max-h-[70vh] overflow-y-auto rounded-[28px] bg-white p-5 shadow-card">
          <h2 className="text-[16px] font-bold">모델 검증</h2>
          <p className="mt-1 text-[13px] leading-relaxed text-sub">
            학습과 시험 경계에서 앞뒤 {screen.backtest.ml.embargo_days ?? 10}거래일을 비웁니다. 시험 {screen.backtest.ml.test_start ?? "—"} ~ {screen.backtest.ml.test_end ?? "—"}.
            보정은 구간 밖 점수 {screen.backtest.ml.calibrate_start ?? "—"} ~ {screen.backtest.ml.calibrate_end ?? "—"}만 사용합니다.
            라벨은 손절보다 목표가 먼저인지이고, 종가 +7%는 옆에 같이 적습니다.
          </p>
          {screen.backtest.ml.available && screen.backtest.ml.threshold != null ? (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <Stat label="삼중 장벽 · 시험 전체" n={screen.backtest.ml.test_n || 0} rate={screen.backtest.ml.baseline_hit_rate || 0} note="손절보다 목표가 먼저" />
                <Stat label={`삼중 장벽 · ${Math.round(screen.backtest.ml.threshold * 100)}% 이상`} n={screen.backtest.ml.alerts || 0} rate={screen.backtest.ml.precision_at_threshold || 0} note="손절보다 목표가 먼저" />
                <Stat label="종가 +7% · 시험 전체" n={screen.backtest.ml.test_n || 0} rate={screen.backtest.ml.legacy_baseline_hit_rate || 0} note="종가 +7%" />
                <Stat label="종가 +7% · 같은 기준" n={screen.backtest.ml.alerts || 0} rate={screen.backtest.ml.legacy_precision_at_threshold || 0} note="종가 +7%" />
              </div>
              <p className="mt-4 text-[13px] leading-relaxed">{screen.backtest.ml.threshold_reason}</p>
              <LedgerBlock ledger={screen.ledger} />
              <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[13px]">
                <thead className="text-sub">
                  <tr>
                    <th className="py-2 font-medium">점수 구간</th>
                    <th className="py-2 font-medium">건수</th>
                    <th className="py-2 font-medium">보정 전</th>
                    <th className="py-2 font-medium">보정 후</th>
                    <th className="py-2 font-medium">삼중 장벽</th>
                    <th className="py-2 font-medium">종가 +7%</th>
                  </tr>
                </thead>
                <tbody>
                  {(screen.backtest.ml.calibration || []).map((row) => (
                    <tr key={row.label} className="border-t border-[#f2f4f6]">
                      <td className="py-2">{row.label}</td>
                      <td className="num py-2">{row.n.toLocaleString("ko-KR")}</td>
                      <td className="num py-2">{row.raw_mean == null ? "—" : `${(row.raw_mean * 100).toFixed(1)}%`}</td>
                      <td className="num py-2">{row.predicted_mean == null ? "—" : `${(row.predicted_mean * 100).toFixed(1)}%`}</td>
                      <td className="num py-2">{row.actual_hit_rate == null ? "—" : `${(row.actual_hit_rate * 100).toFixed(1)}%`}</td>
                      <td className="num py-2">{row.legacy_hit_rate == null ? "—" : `${(row.legacy_hit_rate * 100).toFixed(1)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </>
          ) : (
            <p className="mt-3 text-[13px]">모델: {screen.backtest.ml.reason || "아직 없습니다."}</p>
          )}
          <p className="mt-3 text-[12px] text-sub">{screen.backtest.note}</p>
        </section>
      ),
    });
  }

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-4 pb-16 pt-4 sm:px-8">
      <div className="sticky top-0 z-20 -mx-4 bg-[#f2f4f6]/95 px-4 pb-3 backdrop-blur sm:-mx-8 sm:px-8">
      <header className="flex items-start justify-between gap-4 pt-2">
        <div className="flex items-baseline gap-2">
          <h1 className="text-[22px] font-bold tracking-tight">PreRun</h1>
          <span className="text-[15px] font-semibold text-sub">프리런</span>
        </div>
        <p className="num pt-1 text-right text-[12px] text-sub">KST {kstClock(indexAt)}</p>
      </header>
      <div className="mt-3">
        <Disclaimer compact />
      </div>
      {screen?.freshness?.warnings?.length ? (
        <div className="mt-3 rounded-2xl bg-[#fff4e5] px-4 py-3 text-[13px] leading-relaxed text-[#8a5a00]">
          {screen.freshness.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}
      {screen?.regime?.badge && (
        <p className={`mt-3 inline-flex rounded-full px-3 py-1 text-[12px] font-bold ${screen.regime.weak ? "bg-[#fff1f2] text-up" : "bg-white text-sub"}`}>
          {screen.regime.badge}
          {screen.regime.kospi_distance != null ? ` · 코스피 60일선 ${(screen.regime.kospi_distance * 100).toFixed(1)}%` : ""}
          {screen.regime.kosdaq_distance != null ? ` · 코스닥 ${(screen.regime.kosdaq_distance * 100).toFixed(1)}%` : ""}
        </p>
      )}

      <section className="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
        {(indices.length ? indices : [0, 1, 2]).map((item, index) =>
          typeof item === "number" ? (
            <div key={index} className="skel h-[84px] rounded-3xl" />
          ) : (
            <FadeIn key={item.id} delay={index * 0.04} y={8}>
              <IndexCard item={item} />
            </FadeIn>
          ),
        )}
      </section>

      <section className="mt-4 rounded-[28px] bg-white p-4 shadow-card">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[15px] font-bold">시장 뉴스</h2>
          <span className="text-[12px] text-sub">요약 {newsMode === "LLM" ? "LLM" : "규칙"}</span>
        </div>
        <SoftSwap id={newsError && !news.length ? "news-error" : news.length === 0 ? "news-wait" : "news"}>
        {newsError && !news.length ? (
          <p className="text-[14px] text-sub">뉴스를 가져오지 못했습니다. {newsError}</p>
        ) : news.length === 0 ? (
          <div className="space-y-2">
            <div className="skel h-12 rounded-2xl" />
            <div className="skel h-12 rounded-2xl" />
          </div>
        ) : (
          <ul className="divide-y divide-[#f2f4f6]">
            {news.slice(0, 2).map((item, newsIndex) => (
              <FadeIn as="li" key={item.url + item.title} y={6} delay={newsIndex * 0.04} className="flex gap-3 py-3">
                <SentimentMark sentiment={item.sentiment} onClick={() => setExplain(item.explain)} />
                <div className="min-w-0 flex-1">
                  <a href={item.url} target="_blank" rel="noreferrer" className="block text-[14px] font-semibold leading-snug hover:underline">
                    {item.title}
                  </a>
                  <p className="mt-1 text-[12px] leading-relaxed text-sub">{item.summary}</p>
                  <p className="mt-1 text-[12px] text-sub">
                    {item.source} · {when(item.published_at)}
                  </p>
                  {item.related?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.related.map((rel) => (
                        <button
                          key={rel.symbol}
                          type="button"
                          onClick={() => router.push(`/stock/${encodeURIComponent(rel.symbol)}`)}
                          className="rounded-full bg-[#f2f4f6] px-2.5 py-1 text-[12px] font-semibold"
                        >
                          {rel.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </FadeIn>
            ))}
          </ul>
        )}
        </SoftSwap>
      </section>
      </div>

      <PageDeck pages={pages} />

      <footer className="mt-8">
        <Disclaimer />
        <p className="mt-2 text-[12px] text-sub">국내 일봉은 네이버 금융, 미국과 나스닥은 야후 파이낸스입니다. 장중에는 오늘 미완성 봉을 빼고 현재가로 급등 여부를 다시 봅니다.</p>
      </footer>
      <ExplainSheet item={explain} onClose={() => setExplain(null)} />
    </main>
  );
}

function IndexCard({ item }: { item: IndexItem }) {
  if (item.error || item.price == null) {
    return (
      <div className="rounded-3xl bg-white px-3 py-3 shadow-card">
        <p className="text-[12px] font-semibold text-sub">{item.name}</p>
        <p className="mt-2 text-[12px] leading-snug text-sub">데이터 없음</p>
      </div>
    );
  }
  return (
    <div className="rounded-3xl bg-white px-3 py-3 shadow-card sm:px-4">
      <p className="text-[12px] font-semibold text-sub">{item.name}</p>
      <p className="num mt-1 text-[16px] font-bold sm:text-[18px]">{item.price.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}</p>
      <Move value={item.change_pct} className="text-[12px]" />
    </div>
  );
}

function chunk<T>(items: T[], size: number): T[][] {
  if (!items.length) return [];
  const out: T[][] = [];
  for (let index = 0; index < items.length; index += size) out.push(items.slice(index, index + size));
  return out;
}

function CandidateCard({
  card,
  watched,
  onWatch,
  onOpen,
  onExplain,
}: {
  card: Card;
  watched: boolean;
  onWatch: () => void;
  onOpen: () => void;
  onExplain: (item: Explain) => void;
}) {
  return (
    <article className="card-hover relative rounded-[28px] bg-white p-4 shadow-card">
      <button type="button" onClick={onOpen} className="block w-full text-left">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="dot-on" />
              <h3 className="text-[17px] font-bold">{card.name}</h3>
              <WatchButton on={watched} onToggle={onWatch} />
            </div>
            <p className="mt-1 text-[12px] text-sub">
              {card.code} · {marketLabel(card.market)}
            </p>
          </div>
          <Spark values={card.spark} up={card.spark.at(-1)! >= card.spark[0]} />
        </div>
        <p className="num mt-3 text-[20px] font-bold">{price(card.price, card.currency)}</p>
        <Move value={card.change_pct} className="text-[13px]" />
      </button>
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={() => onExplain(card.explain_score)} className="rounded-2xl bg-[#fff4e5] px-3 py-2 text-left text-[#b36b00]">
          <span className="block text-[11px] font-semibold">보정 확률</span>
          <span className="num block text-[22px] font-bold leading-none">
            {card.calibrated_probability == null ? "없음" : `${(card.calibrated_probability * 100).toFixed(1)}%`}
          </span>
          <span className="mt-1 block text-[11px] font-medium leading-snug">
            {card.bucket?.actual_hit_rate != null
              ? `시험 적중 ${(card.bucket.actual_hit_rate * 100).toFixed(1)}% · ${card.bucket.n.toLocaleString("ko-KR")}건`
              : "시험 적중 없음"}
            {card.baseline_hit_rate != null ? ` · 기준선 ${(card.baseline_hit_rate * 100).toFixed(1)}%` : ""}
          </span>
        </button>
        <button type="button" onClick={() => onExplain(card.explain_timing)} className="rounded-full bg-[#f2f4f6] px-2.5 py-1 text-[12px] font-semibold">
          {card.timing.available ? `${card.timing.label} · ${(card.timing.probability * 100).toFixed(0)}%` : "시기 표본 없음"}
        </button>
        {card.tags.map((tag) => (
          <button key={tag.id} type="button" onClick={() => onExplain(tag.explain)} className="rounded-full bg-[#f2f4f6] px-2.5 py-1 text-[12px] font-medium text-[#333d4b]">
            {tag.text}
          </button>
        ))}
      </div>
      {card.plan && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button type="button" onClick={() => onExplain(card.plan!.explain_stop)} className="rounded-full bg-[#e8f3ff] px-2.5 py-1 text-[12px] font-semibold text-down">
            손절 {price(card.plan.stop, card.currency)}
          </button>
          <button type="button" onClick={() => onExplain(card.plan!.explain_target)} className="rounded-full bg-[#fff1f2] px-2.5 py-1 text-[12px] font-semibold text-up">
            목표 {price(card.plan.target, card.currency)}
          </button>
        </div>
      )}
    </article>
  );
}

function ListRow({
  card,
  off,
  watched,
  onWatch,
  onOpen,
  onExplain,
}: {
  card: Card;
  off: boolean;
  watched: boolean;
  onWatch: () => void;
  onOpen: () => void;
  onExplain: (item: Explain) => void;
}) {
  return (
    <div className="flex items-start gap-3 border-t border-[#f2f4f6] px-4 py-3 first:border-t-0">
      <span className={off ? "dot-off mt-1.5" : "dot-on mt-1.5"} />
      <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-[15px] font-bold">{card.name}</p>
          <p className="num text-[14px] font-semibold">{price(card.price, card.currency)}</p>
        </div>
        <div className="mt-0.5 flex items-center justify-between text-[12px] text-sub">
          <span>
            {card.code} · 거래량비 {card.vol_ratio == null ? "—" : `${card.vol_ratio.toFixed(2)}배`}
          </span>
          <Move value={card.change_pct} className="text-[12px]" />
        </div>
        {off && card.demote_reason && (
          <p className="mt-1 text-[12px] leading-relaxed">
            {card.demoted_at} · {card.demote_reason}
          </p>
        )}
      </button>
      <WatchButton on={watched} onToggle={onWatch} />
      <div className="flex shrink-0 flex-col items-end gap-1">
        <button type="button" onClick={() => onExplain(card.explain_score)} className="text-right text-[12px] font-bold leading-tight">
          {card.calibrated_probability == null ? "—" : `보정 ${(card.calibrated_probability * 100).toFixed(0)}%`}
          {card.bucket?.actual_hit_rate != null && (
            <span className="mt-0.5 block text-[10px] font-medium text-sub">
              시험 {(card.bucket.actual_hit_rate * 100).toFixed(0)}% · {card.bucket.n.toLocaleString("ko-KR")}건
            </span>
          )}
        </button>
        <button type="button" onClick={() => onExplain(card.explain_timing)} className="text-[11px] font-semibold text-sub">
          {card.timing.label || "시기"}
        </button>
      </div>
    </div>
  );
}

function LedgerBlock({ ledger }: { ledger?: Screener["ledger"] }) {
  if (!ledger) return null;
  return (
    <div className="mt-5 rounded-2xl bg-[#f7f8fa] px-4 py-3">
      <p className="text-[14px] font-bold">{ledger.headline}</p>
      <p className="mt-1 text-[12px] leading-relaxed text-sub">
        화면에 올린 후보를 이후 일봉으로 채점합니다. 목표가 먼저면 적중, 손절이 먼저거나 같은 봉에서 둘 다면 손절, 10거래일이 지나도 없으면 만료입니다.
        {ledger.headline === "기록 시작됨" ? ` 채점이 끝난 기록 ${ledger.closed}건이라 비율을 성적처럼 말하지 않습니다.` : ""}
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <LedgerStat title="최근 20거래일" window={ledger.d20} />
        <LedgerStat title="최근 60거래일" window={ledger.d60} />
      </div>
    </div>
  );
}

function LedgerStat({ title, window }: { title: string; window?: LedgerWindow }) {
  if (!window || window.n < 1 || window.hit_rate == null) {
    return (
      <div>
        <p className="text-[12px] text-sub">{title}</p>
        <p className="mt-1 text-[14px] font-semibold">기록 시작됨</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-[12px] text-sub">{title}</p>
      <p className="num mt-1 text-[18px] font-bold">{(window.hit_rate * 100).toFixed(1)}%</p>
      <p className="text-[12px] text-sub">
        {window.n}건 · 평균 {window.avg_return == null ? "—" : `${(window.avg_return * 100).toFixed(1)}%`} · 손절 먼저{" "}
        {window.stop_first_rate == null ? "—" : `${(window.stop_first_rate * 100).toFixed(0)}%`}
      </p>
    </div>
  );
}

function Stat({ label, n, rate, note }: { label: string; n: number; rate: number; note: string }) {
  return (
    <div className="rounded-2xl bg-[#f7f8fa] px-4 py-3">
      <p className="text-[12px] text-sub">{label}</p>
      <p className="num mt-1 text-[22px] font-bold">{(rate * 100).toFixed(1)}%</p>
      <p className="text-[12px] text-sub">
        {n.toLocaleString("ko-KR")}건 · {note}
      </p>
    </div>
  );
}
