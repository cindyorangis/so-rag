"use client";

import { useState } from "react";

export function SourceCard({
  source,
}: {
  source: { source: string; page_number: number; content: string };
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden text-xs">
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="text-gray-500 font-mono">
          📄 {source.source} — p.{source.page_number}
        </span>
        <span className="text-gray-400 ml-2">{expanded ? "▲" : "▼"}</span>
      </button>

      {/* Expandable content */}
      {expanded && (
        <div className="px-3 py-2 bg-white border-t border-gray-100">
          <p className="text-gray-600 leading-relaxed whitespace-pre-wrap">
            {source.content}
          </p>
        </div>
      )}
    </div>
  );
}
