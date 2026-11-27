"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { softEase } from "@/components/Motion";

export type DeckPage = { id: string; title: string; node: React.ReactNode };

export default function PageDeck({ pages }: { pages: DeckPage[] }) {
  const scroller = useRef<HTMLDivElement>(null);
  const reduceRef = useRef(false);
  const [index, setIndex] = useState(0);
  const [wide, setWide] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    const media = window.matchMedia("(min-width: 768px)");
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      setWide(media.matches);
      reduceRef.current = motion.matches;
    };
    apply();
    media.addEventListener("change", apply);
    motion.addEventListener("change", apply);
    return () => {
      media.removeEventListener("change", apply);
      motion.removeEventListener("change", apply);
    };
  }, []);

  const go = useCallback(
    (next: number) => {
      const node = scroller.current;
      if (!node || pages.length === 0) return;
      const clamped = Math.max(0, Math.min(pages.length - 1, next));
      node.scrollTo({ left: clamped * node.clientWidth, behavior: reduceRef.current ? "auto" : "smooth" });
      setIndex(clamped);
    },
    [pages.length],
  );

  useEffect(() => {
    const node = scroller.current;
    if (!node) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const width = node.clientWidth || 1;
        setIndex(Math.max(0, Math.min(pages.length - 1, Math.round(node.scrollLeft / width))));
      });
    };
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      node.removeEventListener("scroll", onScroll);
    };
  }, [pages.length]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (event.key === "ArrowRight") go(index + 1);
      if (event.key === "ArrowLeft") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  if (!pages.length) return null;

  return (
    <div className="relative mt-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="relative h-5 min-w-0 flex-1">
          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={pages[index]?.id}
              className="absolute inset-x-0 top-0 truncate text-[14px] font-bold"
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: -4 }}
              transition={{ duration: reduce ? 0 : 0.28, ease: softEase }}
            >
              {pages[index]?.title}
            </motion.p>
          </AnimatePresence>
        </div>
        <div className="flex max-w-[46%] flex-wrap justify-end gap-1.5">
          {pages.map((page, pageIndex) => (
            <button
              key={page.id}
              type="button"
              onClick={() => go(pageIndex)}
              className={`h-1.5 rounded-full transition-all duration-300 ease-out ${pageIndex === index ? "w-5 bg-ink" : "w-1.5 bg-[#d1d6db]"}`}
              aria-label={page.title}
            />
          ))}
        </div>
      </div>
      <div
        ref={scroller}
        className="flex snap-x snap-mandatory overflow-x-auto scroll-smooth motion-reduce:scroll-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {pages.map((page) => (
          <section key={page.id} className="w-full shrink-0 snap-start snap-always">
            {page.node}
          </section>
        ))}
      </div>
      {wide && (
        <>
          <button
            type="button"
            aria-label="이전 페이지"
            disabled={index === 0}
            onClick={() => go(index - 1)}
            className="absolute left-0 top-1/2 z-10 grid h-12 w-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#d1d6db] text-[20px] font-bold text-[#4e5968] shadow-card transition hover:bg-[#b0b8c1] disabled:pointer-events-none disabled:opacity-0"
          >
            {"<"}
          </button>
          <button
            type="button"
            aria-label="다음 페이지"
            disabled={index >= pages.length - 1}
            onClick={() => go(index + 1)}
            className="absolute right-0 top-1/2 z-10 grid h-12 w-12 translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#d1d6db] text-[20px] font-bold text-[#4e5968] shadow-card transition hover:bg-[#b0b8c1] disabled:pointer-events-none disabled:opacity-0"
          >
            {">"}
          </button>
        </>
      )}
    </div>
  );
}
