"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

export const softEase = [0.22, 1, 0.36, 1] as const;

export function useSoft(duration = 0.42) {
  const reduce = useReducedMotion();
  return {
    reduce: Boolean(reduce),
    transition: { duration: reduce ? 0 : duration, ease: softEase },
  };
}

const fadeTags = {
  div: motion.div,
  li: motion.li,
  article: motion.article,
};

export function FadeIn({
  children,
  className,
  delay = 0,
  y = 10,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
  as?: keyof typeof fadeTags;
}) {
  const { reduce, transition } = useSoft();
  const Comp = fadeTags[as];
  return (
    <Comp
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: Math.round(y * 0.5) }}
      transition={{ ...transition, delay: reduce ? 0 : delay }}
    >
      {children}
    </Comp>
  );
}

export function SoftSwap({
  id,
  children,
  className,
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  const { reduce, transition } = useSoft(0.34);
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={id}
        className={className}
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: -6 }}
        transition={transition}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

export function TabButton({
  active,
  layoutId,
  onClick,
  children,
  idleClass = "bg-white",
}: {
  active: boolean;
  layoutId: string;
  onClick: () => void;
  children: ReactNode;
  idleClass?: string;
}) {
  const { reduce, transition } = useSoft(0.34);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`relative rounded-full px-3 py-1.5 text-[13px] font-semibold transition-colors duration-300 ${active ? "text-white" : "text-sub"}`}
    >
      <span className={`absolute inset-0 rounded-full ${idleClass}`} />
      {active && (
        <motion.span
          layoutId={layoutId}
          className="absolute inset-0 rounded-full bg-ink"
          transition={reduce ? { duration: 0 } : { type: "tween", duration: transition.duration, ease: softEase }}
        />
      )}
      <span className="relative">{children}</span>
    </button>
  );
}
