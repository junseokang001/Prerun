"use client";

export default function WatchButton({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-label={on ? "관심 해제" : "관심 추가"}
      aria-pressed={on}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-full transition ${on ? "bg-[#fff4e5] text-[#b36b00]" : "bg-[#f2f4f6] text-sub hover:bg-[#e9edf1]"}`}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
        <path d="M12 3.6l2.3 4.7 5.2.8-3.8 3.6.9 5.2L12 15.8 7.4 18l.9-5.2L4.5 9.1l5.2-.8L12 3.6z" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
