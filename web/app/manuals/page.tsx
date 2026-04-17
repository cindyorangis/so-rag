"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceCard } from "@/components/SourceCard";

type Source = { source: string; page_number: number; content: string };

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

const SUGGESTIONS = [
  "What docs do I need for vehicle registration?",
  "How do I get a replacement driver's licence?",
  "What are the fees for a personalized plate?",
];

export default function ManualsPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

      if (!res.ok) throw new Error(`API returned ${res.status}`);
      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "**Error:** I couldn't connect to the manual database. Please ensure the backend is running.",
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100dvh",
        background: "#0f1117",
        color: "#fff",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      {/* Header */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          padding: "14px 20px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          background: "#0f1117",
          zIndex: 10,
        }}
      >
        <div
          style={{ background: "#1a56db", padding: "6px", borderRadius: "8px" }}
        >
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
          <h1 style={{ fontSize: "15px", fontWeight: 600, margin: 0 }}>
            ServiceOntario
          </h1>
          <p
            style={{
              fontSize: "11px",
              color: "rgba(255,255,255,0.4)",
              margin: 0,
            }}
          >
            Policy Intelligence Unit
          </p>
        </div>
      </header>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "24px",
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              gap: "24px",
            }}
          >
            <div>
              <h2 style={{ fontSize: "20px", marginBottom: "8px" }}>
                How can I help you today?
              </h2>
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: "14px" }}>
                Search verified ServiceOntario manuals instantly.
              </p>
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "10px",
                width: "100%",
                maxWidth: "400px",
              }}
            >
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleAsk(s)}
                  style={{
                    padding: "12px 16px",
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "12px",
                    color: "rgba(255,255,255,0.8)",
                    textAlign: "left",
                    cursor: "pointer",
                    fontSize: "13px",
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "90%",
                padding: "12px 16px",
                borderRadius:
                  msg.role === "user"
                    ? "18px 18px 4px 18px"
                    : "18px 18px 18px 4px",
                background:
                  msg.role === "user" ? "#1a56db" : "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              {/* Markdown Content Renderer */}
              <div className="markdown-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              </div>

              {msg.sources && msg.sources.length > 0 && (
                <div
                  style={{
                    marginTop: "16px",
                    paddingTop: "12px",
                    borderTop: "1px solid rgba(255,255,255,0.1)",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "rgba(255,255,255,0.4)",
                      fontWeight: 700,
                      textTransform: "uppercase",
                    }}
                  >
                    Sources
                  </span>
                  <div
                    style={{
                      marginTop: "8px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "6px",
                    }}
                  >
                    {msg.sources.map((s, j) => (
                      <SourceCard key={j} source={s} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div
            style={{
              color: "rgba(255,255,255,0.4)",
              fontSize: "12px",
              marginLeft: "8px",
            }}
          >
            AI is searching manuals...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Area */}
      <div
        style={{
          padding: "20px",
          background: "#0f1117",
          borderTop: "1px solid rgba(255,255,255,0.07)",
        }}
      >
        <div
          style={{
            display: "flex",
            gap: "10px",
            maxWidth: "800px",
            margin: "0 auto",
          }}
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAsk()}
            placeholder="Type your question..."
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "12px",
              padding: "12px 16px",
              color: "#fff",
              outline: "none",
            }}
          />
          <button
            onClick={() => handleAsk()}
            disabled={loading || !input.trim()}
            style={{
              padding: "0 20px",
              background: "#1a56db",
              color: "#fff",
              border: "none",
              borderRadius: "12px",
              fontWeight: 600,
              cursor: "pointer",
              opacity: loading || !input.trim() ? 0.5 : 1,
            }}
          >
            Ask
          </button>
        </div>
      </div>

      <style jsx global>{`
        .markdown-content {
          font-size: 14px;
          line-height: 1.6;
          color: rgba(255, 255, 255, 0.9);
        }
        .markdown-content p {
          margin: 0 0 12px 0;
        }
        .markdown-content p:last-child {
          margin-bottom: 0;
        }
        .markdown-content ul,
        .markdown-content ol {
          padding-left: 20px;
          margin-bottom: 12px;
        }
        .markdown-content li {
          margin-bottom: 4px;
        }
        .markdown-content table {
          width: 100%;
          border-collapse: collapse;
          margin: 12px 0;
          font-size: 13px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
          overflow: hidden;
        }
        .markdown-content th,
        .markdown-content td {
          border: 1px solid rgba(255, 255, 255, 0.1);
          padding: 8px;
          text-align: left;
        }
        .markdown-content th {
          background: rgba(255, 255, 255, 0.05);
        }
        .markdown-content strong {
          color: #fff;
        }
      `}</style>
    </div>
  );
}
