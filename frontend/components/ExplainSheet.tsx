"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";
import type { Explain } from "@/lib/types";

export default function ExplainSheet({
  item,
  onClose,
}: {
  item: Explain | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!item) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  return (
    <AnimatePresence>
      {item && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
          initial={{ backgroundColor: "rgba(15,18,22,0)" }}
          animate={{ backgroundColor: "rgba(15,18,22,0.42)" }}
          exit={{ backgroundColor: "rgba(15,18,22,0)" }}
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="explain-title"
            initial={{ y: 36, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
            className="max-h-[86vh] w-full max-w-lg overflow-y-auto rounded-t-[28px] bg-white px-5 pb-8 pt-4 shadow-card sm:rounded-[28px]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-[#e5e8eb]" />
            <p className="text-[13px] font-medium text-sub">쉽게 보기</p>
            <h2 id="explain-title" className="mt-1 text-[22px] font-bold leading-snug tracking-tight">
              {item.title}
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-[#333d4b]">{item.plain}</p>
            <section className="mt-5">
              <h3 className="text-[13px] font-semibold text-sub">이 종목 숫자</h3>
              <ul className="mt-2 divide-y divide-[#f2f4f6] rounded-2xl bg-[#f7f8fa] px-4">
                {item.values.map((row) => (
                  <li key={row.label} className="py-3">
                    <div className="flex items-start justify-between gap-4">
                      <span className="text-[13px] text-sub">{row.label}</span>
                      <span className="num text-right text-[14px] font-semibold">{row.value}</span>
                    </div>
                    {row.note && <p className="mt-1 text-[12px] leading-relaxed text-sub">{row.note}</p>}
                  </li>
                ))}
              </ul>
            </section>
            <section className="mt-5">
              <h3 className="text-[13px] font-semibold text-sub">왜 보나</h3>
              <p className="mt-2 text-[15px] leading-relaxed">{item.why}</p>
            </section>
            <section className="mt-5">
              <h3 className="text-[13px] font-semibold text-sub">과거 근거</h3>
              <p className="mt-2 text-[15px] leading-relaxed">{item.evidence}</p>
            </section>
            {item.source && <p className="mt-5 text-[12px] text-sub">출처 · {item.source}</p>}
            <button
              type="button"
              onClick={onClose}
              className="mt-5 w-full rounded-2xl bg-ink py-3.5 text-[15px] font-semibold text-white transition hover:bg-[#2c3542]"
            >
              닫기
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
