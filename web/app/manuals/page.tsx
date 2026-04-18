"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceCard } from "@/components/SourceCard";
import "./manuals.css";

type Source = {
  source: string;
  page_number: number;
  content: string;
  section_title?: string;
  pdf_url?: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  mode?: "answer" | "procedure";
  error?: boolean;
  question?: string;
  feedback?: "up" | "down" | null;
};

const FALLBACK_SUGGESTIONS = [
  "What docs do I need for vehicle registration?",
  "How do I get a replacement driver's licence?",
  "What are the fees for a personalized plate?",
];

function normalizeBullets(text: string): string {
  return text
    .replace(/•\s*/g, "- ")
    .replace(/·\s*/g, "- ")
    .replace(/^\*\s+/gm, "- ");
}

export default function ManualsPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(FALLBACK_SUGGESTIONS);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
  async function fetchSuggestions() {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/suggestions`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.suggestions?.length >= 3) {
        setSuggestions(data.suggestions);
      }
    } catch {
      // silently fall back to hardcoded suggestions
    }
  }
  fetchSuggestions();
}, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleAsk(question?: string) {
    const q = (question ?? input).trim();
    if (!q || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        if (res.status === 429) {
          throw new Error(
            "Rate limit reached — please wait a moment and try again.",
          );
        }
        throw new Error(detail?.detail ?? `API error ${res.status}`);
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: normalizeBullets(data.answer),
          sources: data.sources,
          mode: data.mode,
          question: q,
          feedback: null,
        },
      ]);
    } catch (err: any) {
      console.error("Ask error:", err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Could not get a response.**\n\n${err?.message ?? "Please check that the backend is running."}`,
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleClear() {
    setMessages([]);
    setInput("");
  }

  async function handleFeedback(msgIndex: number, rating: "up" | "down") {
    const msg = messages[msgIndex];
    if (!msg || msg.feedback) return; // already rated

    // Optimistically update UI
    setMessages((prev) =>
      prev.map((m, i) => (i === msgIndex ? { ...m, feedback: rating } : m)),
    );

    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: msg.question ?? "",
          answer: msg.content,
          rating,
          sources: msg.sources ?? [],
        }),
      });
    } catch (err) {
      console.error("Feedback error:", err);
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-dvh bg-[#0f1117] text-white font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.07] bg-[#0f1117] z-10">
        <div className="flex items-center gap-3">
          <div className="bg-blue-600 p-1.5 rounded-lg">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#fff"
              strokeWidth="2"
            >
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <div>
            <h1 className="text-[15px] font-semibold m-0">ServiceOntario</h1>
            <p className="text-[11px] text-white/40 m-0">
              Policy Intelligence Unit
            </p>
          </div>
        </div>

        {!isEmpty && (
          <button
            onClick={handleClear}
            className="bg-white/5 border border-white/10 rounded-lg text-white/50 text-xs px-3 py-1.5 cursor-pointer hover:text-white/70 transition-colors"
          >
            Clear
          </button>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-6">
        <div className="w-full max-w-[760px] mx-auto flex flex-col gap-6 flex-1">
          {/* Empty state */}
          {isEmpty && (
            <div className="flex-1 flex flex-col items-center justify-center text-center gap-6">
              <div>
                <h2 className="text-xl mb-2">How can I help you today?</h2>
                <p className="text-white/50 text-sm">
                  Search verified ServiceOntario manuals instantly.
                </p>
              </div>
              <div className="flex flex-col gap-2.5 w-full max-w-[400px]">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleAsk(s)}
                    className="px-4 py-3 bg-white/[0.03] border border-white/10 rounded-xl text-white/80 text-left cursor-pointer text-[13px] hover:bg-white/[0.06] transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message thread */}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[90%] px-4 py-3 border ${
                  msg.role === "user"
                    ? "rounded-[18px_18px_4px_18px] bg-blue-600 border-white/[0.08]"
                    : msg.error
                      ? "rounded-[18px_18px_18px_4px] bg-red-500/10 border-red-500/30"
                      : "rounded-[18px_18px_18px_4px] bg-white/5 border-white/[0.08]"
                }`}
              >
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>

                {msg.role === "assistant" && !msg.error && (
                  <div className="flex items-center gap-2 mt-3">
                    <span className="text-[10px] text-white/30">Helpful?</span>
                    <button
                      onClick={() => handleFeedback(i, "up")}
                      disabled={!!msg.feedback}
                      className={`flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] transition-colors ${
                        msg.feedback === "up"
                          ? "border-green-500/50 text-green-400 bg-green-500/10"
                          : "border-white/10 text-white/30 hover:text-white/60 hover:border-white/20"
                      } disabled:cursor-default`}
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 24 24"
                        fill={msg.feedback === "up" ? "currentColor" : "none"}
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" />
                        <path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3" />
                      </svg>
                      Yes
                    </button>
                    <button
                      onClick={() => handleFeedback(i, "down")}
                      disabled={!!msg.feedback}
                      className={`flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] transition-colors ${
                        msg.feedback === "down"
                          ? "border-red-500/50 text-red-400 bg-red-500/10"
                          : "border-white/10 text-white/30 hover:text-white/60 hover:border-white/20"
                      } disabled:cursor-default`}
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 24 24"
                        fill={msg.feedback === "down" ? "currentColor" : "none"}
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z" />
                        <path d="M17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17" />
                      </svg>
                      No
                    </button>
                  </div>
                )}

                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-white/10">
                    <span className="text-[10px] text-white/40 font-bold uppercase tracking-wider">
                      Sources
                    </span>
                    <div className="mt-2 flex flex-col gap-1.5">
                      {msg.sources.map((s, j) => (
                        <SourceCard key={j} source={s} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="flex items-center gap-2 ml-1">
              <div className="flex gap-1">
                {[0, 1, 2].map((n) => (
                  <div
                    key={n}
                    className="w-1.5 h-1.5 rounded-full bg-white/30"
                    style={{
                      animation: "pulse 1.2s ease-in-out infinite",
                      animationDelay: `${n * 0.2}s`,
                    }}
                  />
                ))}
              </div>
              <span className="text-white/40 text-xs">
                Searching manuals...
              </span>
            </div>
          )}

          {/* Suggestion chips */}
          {!isEmpty && !loading && (
            <div className="flex gap-2 flex-wrap">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => handleAsk(s)}
                  className="px-3 py-1.5 bg-white/[0.03] border border-white/10 rounded-full text-white/50 cursor-pointer text-xs whitespace-nowrap hover:text-white/70 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="px-5 py-5 bg-[#0f1117] border-t border-white/[0.07]">
        <div className="flex gap-2.5 max-w-[800px] mx-auto">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAsk()}
            placeholder="Ask about ServiceOntario policies..."
            disabled={loading}
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white outline-none text-sm placeholder:text-white/30 disabled:opacity-60 focus:border-white/20 transition-colors"
          />
          <button
            onClick={() => handleAsk()}
            disabled={loading || !input.trim()}
            className="px-5 bg-blue-600 text-white border-none rounded-xl font-semibold cursor-pointer min-w-16 disabled:opacity-50 hover:bg-blue-500 transition-colors text-sm"
          >
            {loading ? "..." : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}
