"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceCard } from "@/components/SourceCard";
import type { Message, Source } from "@/types/manuals";

type Props = {
  msg: Message;
  index: number;
  onFeedback: (index: number, rating: "up" | "down") => void;
};

export function ChatMessage({ msg, index, onFeedback }: Props) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-4 py-3 rounded-[18px_18px_4px_18px] bg-blue-600 border border-white/[0.08] text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex flex-col gap-3 items-start">
      {/* Answer bubble */}
      <div
        className={`w-full px-4 py-3.5 rounded-[4px_18px_18px_18px] border text-sm leading-relaxed ${
          msg.error
            ? "bg-red-500/10 border-red-500/30"
            : "bg-white/[0.04] border-white/[0.08]"
        }`}
      >
        <div className="markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {msg.content}
          </ReactMarkdown>
        </div>

        {/* Feedback row — inside bubble, below answer */}
        {!msg.error && (
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/[0.07]">
            <span className="text-[10px] text-white/30 mr-0.5">Helpful?</span>
            <FeedbackButton
              rating="up"
              active={msg.feedback === "up"}
              locked={!!msg.feedback}
              onClick={() => onFeedback(index, "up")}
            />
            <FeedbackButton
              rating="down"
              active={msg.feedback === "down"}
              locked={!!msg.feedback}
              onClick={() => onFeedback(index, "down")}
            />
            {msg.feedback && (
              <span className="text-[10px] text-white/30 ml-1 animate-fade-in">
                Thanks for the feedback
              </span>
            )}
          </div>
        )}
      </div>

      {/* Sources — separate block, visually outside the bubble */}
      {msg.sources && msg.sources.length > 0 && (
        <SourcesBlock sources={msg.sources} />
      )}
    </div>
  );
}

function SourcesBlock({ sources }: { sources: Source[] }) {
  return (
    <div className="w-full pl-3 border-l-2 border-white/[0.08]">
      <div className="flex items-center gap-1.5 mb-2">
        <svg
          width="11"
          height="11"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="text-white/25"
        >
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <span className="text-[10px] text-white/30 font-semibold uppercase tracking-widest">
          {sources.length} {sources.length === 1 ? "reference" : "references"}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {sources.map((s, j) => (
          <SourceCard key={j} source={s} />
        ))}
      </div>
    </div>
  );
}

type FeedbackButtonProps = {
  rating: "up" | "down";
  active: boolean;
  locked: boolean;
  onClick: () => void;
};

function FeedbackButton({
  rating,
  active,
  locked,
  onClick,
}: FeedbackButtonProps) {
  const isUp = rating === "up";

  const activeClass = isUp
    ? "border-green-500/50 text-green-400 bg-green-500/10"
    : "border-red-500/40 text-red-400 bg-red-500/10";

  const idleClass =
    "border-white/10 text-white/30 hover:text-white/60 hover:border-white/20";

  return (
    <button
      onClick={onClick}
      disabled={locked}
      className={`flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] transition-all duration-200 disabled:cursor-default ${
        active ? activeClass : idleClass
      }`}
    >
      <svg
        width="11"
        height="11"
        viewBox="0 0 24 24"
        fill={active ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="2"
      >
        {isUp ? (
          <>
            <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" />
            <path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3" />
          </>
        ) : (
          <>
            <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z" />
            <path d="M17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17" />
          </>
        )}
      </svg>
      {active ? (isUp ? "Yes" : "No") : isUp ? "Yes" : "No"}
    </button>
  );
}
