"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { softEase } from "@/components/Motion";

export default function Template({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0 : 0.45, ease: softEase }}
    >
      {children}
    </motion.div>
  );
}
