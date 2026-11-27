"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useId, useState, type ReactNode } from "react";
import { readConsent, writeConsent } from "@/lib/consent";
import { softEase } from "@/components/Motion";

export default function ConsentGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<"unknown" | "needed" | "ok">("unknown");
  const [checked, setChecked] = useState(false);
  const reduce = useReducedMotion();
  const titleId = useId();
  const checkId = useId();

  useEffect(() => {
    setPhase(readConsent() ? "ok" : "needed");
  }, []);

  useEffect(() => {
    if (phase !== "needed") return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [phase]);

  if (phase === "unknown") {
    return <div className="min-h-screen bg-paper" aria-busy="true" />;
  }

  if (phase === "ok") return children;

  function agree() {
    if (!checked) return;
    writeConsent();
    setPhase("ok");
  }

  return (
    <div className="min-h-screen bg-paper">
      <motion.div
        className="fixed inset-0 z-[80] flex items-end justify-center bg-[#0f1216]/45 p-0 sm:items-center sm:p-6"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: reduce ? 0 : 0.35, ease: softEase }}
      >
        <motion.section
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          initial={reduce ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduce ? 0 : 0.46, ease: softEase }}
          className="w-full max-w-lg rounded-t-[28px] bg-white px-6 pb-8 pt-6 shadow-card sm:rounded-[28px]"
        >
          <p className="text-[13px] font-medium text-sub">처음 방문</p>
          <h1 id={titleId} className="mt-1 text-[24px] font-bold tracking-tight">
            투자 유의사항
          </h1>
          <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-[#333d4b]">
            <p>프리런은 과거 시세와 통계 모형으로 점수를 내는 정량·데이터 참고 도구입니다. 화면에 나오는 확률, 후보, 손절·목표 가격은 과거 빈도에서 계산한 참고 값입니다.</p>
            <p>프리런은 투자 자문이나 매수·매도 권유가 아니고, 수익을 약속하지 않습니다.</p>
            <p>모든 투자 판단과 그 결과, 원금 손실을 포함한 책임은 사용자 본인에게 있습니다.</p>
          </div>
          <form
            className="mt-5"
            onSubmit={(event) => {
              event.preventDefault();
              agree();
            }}
          >
            <label htmlFor={checkId} className="flex cursor-pointer items-start gap-3 rounded-2xl bg-[#f7f8fa] px-4 py-3 text-[14px] leading-relaxed">
              <input
                id={checkId}
                type="checkbox"
                checked={checked}
                onChange={(event) => setChecked(event.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 accent-[#191f28]"
              />
              <span>위 내용을 확인했습니다. 투자 결정과 책임은 본인에게 있습니다.</span>
            </label>
            <button
              type="submit"
              disabled={!checked}
              className="mt-4 w-full rounded-2xl bg-ink py-3.5 text-[15px] font-semibold text-white transition duration-300 ease-out hover:bg-[#2c3542] disabled:cursor-not-allowed disabled:bg-[#d1d6db] disabled:hover:bg-[#d1d6db]"
            >
              이에 동의합니다
            </button>
            <p className="mt-3 text-center text-[12px] leading-relaxed text-sub">동의는 이 브라우저에만 저장됩니다. 동의한 뒤에는 다시 묻지 않습니다.</p>
          </form>
        </motion.section>
      </motion.div>
    </div>
  );
}
