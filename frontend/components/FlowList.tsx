"use client";

import { Move } from "@/components/Bits";
import { FadeIn } from "@/components/Motion";
import { price } from "@/lib/format";
import type { FlowGroup } from "@/lib/types";

function pctText(value: number | null) {
  if (value == null) return "데이터 없음";
  return null;
}

export default function FlowList({ groups, empty }: { groups: FlowGroup[]; empty: string }) {
  if (!groups.length) return <p className="rounded-[28px] bg-white px-5 py-8 text-[14px] text-sub">{empty}</p>;
  return (
    <div className="space-y-3">
      {groups.map((group, index) => {
        const heat = group.change_1d == null ? 0 : Math.max(-1, Math.min(1, group.change_1d / 0.03));
        const tone = heat > 0 ? `rgba(240,68,82,${0.12 + Math.abs(heat) * 0.35})` : heat < 0 ? `rgba(49,130,246,${0.12 + Math.abs(heat) * 0.35})` : "#f7f8fa";
        return (
          <FadeIn as="article" key={`${group.kind}-${group.id}`} delay={Math.min(index, 4) * 0.05} className={`rounded-[28px] bg-white p-4 shadow-card ${group.has_candidate ? "ring-2 ring-[#ffb020]" : ""}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[12px] font-semibold text-sub">{group.kind}{group.has_candidate ? " · 후보 포함" : ""}</p>
                <h3 className="text-[16px] font-bold">{group.name}</h3>
              </div>
              <div className="rounded-2xl px-3 py-2 text-right" style={{ background: tone }}>
                <p className="text-[11px] text-sub">1일</p>
                {group.change_1d == null ? <p className="text-[12px]">데이터 없음</p> : <Move value={group.change_1d} className="text-[14px]" />}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
              <p className="rounded-2xl bg-[#f7f8fa] px-3 py-2">
                1주 {pctText(group.change_1w) || <Move value={group.change_1w} className="text-[12px]" />}
              </p>
              <p className="rounded-2xl bg-[#f7f8fa] px-3 py-2">
                1달 {pctText(group.change_1m) || <Move value={group.change_1m} className="text-[12px]" />}
              </p>
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-sub">{group.return_note}</p>
            <p className="mt-2 text-[12px] leading-relaxed text-sub">
              거래대금 {group.value_today == null ? "데이터 없음" : `${Math.round(group.value_today).toLocaleString("ko-KR")}`} · {group.volume_surge.reason}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-sub">
              {group.foreign.available
                ? `${group.foreign.name} ${group.foreign.date} 외국인 ${fmtQty(group.foreign.foreign_net)}주, 기관 ${fmtQty(group.foreign.institution_net)}주. ${group.foreign.reason}`
                : `수급 데이터 없음. ${group.foreign.reason}`}
            </p>
            {group.leader && (
              <p className="mt-2 text-[13px]">
                대장주 {group.leader.name} {group.leader.price == null ? "" : price(group.leader.price, "KRW")}{" "}
                {group.leader.change_pct == null ? "등락 데이터 없음" : <Move value={group.leader.change_pct} className="text-[12px]" />}
              </p>
            )}
            {group.stocks.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {group.stocks.map((stock) => (
                  <span key={stock.code} className={`rounded-full px-2.5 py-1 text-[12px] ${stock.candidate ? "bg-[#fff4e5] font-semibold" : "bg-[#f2f4f6]"}`}>
                    {stock.name}
                    {stock.candidate ? " · 후보" : ""}
                  </span>
                ))}
              </div>
            )}
          </FadeIn>
        );
      })}
    </div>
  );
}

function fmtQty(value: number | null) {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString("ko-KR")}`;
}
