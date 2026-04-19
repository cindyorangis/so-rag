"use client";

import { useEffect, useRef, useState } from "react";

type ModelStatus = {
  id: string;
  label: string;
  description: string;
  tier: string;
  available: boolean;
  reset_in: string | null;
  remaining_requests: string | null;
};

type Props = {
  selectedModel: string;
  onChange: (modelId: string) => void;
};

export function ModelPicker({ selectedModel, onChange }: Props) {
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function fetchModels() {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/models`);
        const data = await res.json();
        setModels(data.models);
        // Auto-select first available if current selection unavailable
        const current = data.models.find(
          (m: ModelStatus) => m.id === selectedModel,
        );
        if (!current?.available) {
          const firstAvailable = data.models.find(
            (m: ModelStatus) => m.available,
          );
          if (firstAvailable) onChange(firstAvailable.id);
        }
      } catch {
        // silently fail — model picker just won't show
      } finally {
        setLoading(false);
      }
    }
    fetchModels();
    const interval = setInterval(fetchModels, 30000);
    return () => clearInterval(interval);
  }, []);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (loading || models.length === 0) return null;

  const selected = models.find((m) => m.id === selectedModel) ?? models[0];

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.04] hover:bg-white/[0.07] hover:border-white/20 transition-all text-[11px] text-white/60 hover:text-white/80"
      >
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            selected?.available ? "bg-green-400" : "bg-red-400/60"
          }`}
        />
        <span>{selected?.label ?? "Select model"}</span>
        {/* Chevron */}
        <svg
          className={`w-3 h-3 text-white/30 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          viewBox="0 0 12 12"
          fill="none"
        >
          <path
            d="M2.5 4.5L6 8l3.5-3.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute bottom-full mb-2 left-0 z-50 w-64 rounded-xl border border-white/10 bg-[#1a1a1a] shadow-2xl overflow-hidden">
          {models.map((m, i) => {
            const isSelected = m.id === selectedModel;
            return (
              <button
                key={m.id}
                onClick={() => {
                  if (m.available) {
                    onChange(m.id);
                    setOpen(false);
                  }
                }}
                disabled={!m.available}
                className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors ${
                  i > 0 ? "border-t border-white/[0.06]" : ""
                } ${
                  isSelected
                    ? "bg-blue-500/10"
                    : m.available
                      ? "hover:bg-white/[0.05] cursor-pointer"
                      : "cursor-not-allowed opacity-50"
                }`}
              >
                {/* Status dot */}
                <span className="mt-[3px] flex-shrink-0">
                  <span
                    className={`block w-1.5 h-1.5 rounded-full ${
                      m.available ? "bg-green-400" : "bg-red-400/60"
                    }`}
                  />
                </span>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`text-[12px] font-medium ${
                        isSelected ? "text-blue-300" : "text-white/80"
                      }`}
                    >
                      {m.label}
                    </span>
                    {isSelected && (
                      <svg
                        className="w-3 h-3 text-blue-400 flex-shrink-0"
                        viewBox="0 0 12 12"
                        fill="none"
                      >
                        <path
                          d="M2 6l3 3 5-5"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </div>
                  <p className="text-[10px] text-white/35 mt-0.5 leading-snug">
                    {!m.available && m.reset_in
                      ? `Rate limited — resets in ${m.reset_in}`
                      : m.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
