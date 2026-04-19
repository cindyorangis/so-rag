"use client";

import { useEffect, useState } from "react";

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
    // Refresh every 30s so reset_in stays current
    const interval = setInterval(fetchModels, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading || models.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[10px] text-white/30 uppercase tracking-widest font-semibold">
        Model
      </span>
      {models.map((m) => (
        <button
          key={m.id}
          onClick={() => m.available && onChange(m.id)}
          disabled={!m.available}
          title={m.description}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] transition-all ${
            selectedModel === m.id
              ? "border-blue-500/60 bg-blue-500/10 text-blue-300"
              : m.available
                ? "border-white/10 text-white/40 hover:text-white/70 hover:border-white/20"
                : "border-white/[0.05] text-white/20 cursor-not-allowed"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              m.available ? "bg-green-400" : "bg-red-400/60"
            }`}
          />
          {m.label}
          {!m.available && m.reset_in && (
            <span className="text-white/25 text-[10px]">({m.reset_in})</span>
          )}
        </button>
      ))}
    </div>
  );
}
