"use client";

import { useState } from "react";

export function SourceCard({
  source,
}: {
  source: { source: string; page_number: number; content: string };
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const shortName = source.source
    .replace(/\.pdf$/i, "")
    .replace(/[-_]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());

  async function handleCopy(e: React.MouseEvent) {
    e.stopPropagation();
    await navigator.clipboard.writeText(source.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="border border-white/[0.08] rounded-xl overflow-hidden text-xs bg-white/[0.04]">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-transparent border-none cursor-pointer text-left gap-2 text-white/50 hover:text-white/70 transition-colors"
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <svg
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="shrink-0 opacity-50"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>

          <span className="truncate max-w-[220px] text-white/70">
            {shortName}
          </span>

          <span className="shrink-0 bg-blue-500/20 text-blue-400 rounded px-1.5 py-px text-[10px] font-semibold tracking-wide">
            p.{source.page_number}
          </span>
        </div>

        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          className={`shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : "rotate-0"}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Expandable content */}
      <div
        className={`grid transition-all duration-200 ease-in-out ${expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-3 pt-2.5 border-t border-white/[0.06]">
            <p className="text-white/60 leading-relaxed whitespace-pre-wrap text-[11.5px] mb-2.5">
              {source.content}
            </p>

            <button
              onClick={handleCopy}
              className={`flex items-center gap-1 bg-white/5 border border-white/[0.08] rounded-md text-[11px] px-2.5 py-1 cursor-pointer transition-colors ${
                copied ? "text-blue-400" : "text-white/40 hover:text-white/60"
              }`}
            >
              {copied ? (
                <>
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Copied
                </>
              ) : (
                <>
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                  </svg>
                  Copy excerpt
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
