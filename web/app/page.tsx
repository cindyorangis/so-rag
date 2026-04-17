import Link from "next/link";

export default function Home() {
  const features = [
    {
      icon: "📄",
      label: "Policy manuals",
      detail: "Vehicle, driver, health & more",
    },
    {
      icon: "⚡",
      label: "Instant answers",
      detail: "Powered by Llama 3.3 70B",
    },
    {
      icon: "📍",
      label: "Page citations",
      detail: "Every answer sourced & cited",
    },
  ];

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0a0c10",
        color: "#fff",
        fontFamily: "'Georgia', 'Times New Roman', serif",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 24px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Grid background */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 0,
          backgroundImage: `
          linear-gradient(rgba(26,86,219,0.06) 1px, transparent 1px),
          linear-gradient(90deg, rgba(26,86,219,0.06) 1px, transparent 1px)
        `,
          backgroundSize: "48px 48px",
        }}
      />

      {/* Radial glow */}
      <div
        style={{
          position: "absolute",
          top: "30%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "600px",
          height: "400px",
          background:
            "radial-gradient(ellipse, rgba(26,86,219,0.12) 0%, transparent 70%)",
          zIndex: 0,
          pointerEvents: "none",
        }}
      />

      <div
        style={{
          position: "relative",
          zIndex: 1,
          textAlign: "center",
          maxWidth: "560px",
        }}
      >
        {/* Eyebrow */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            border: "1px solid rgba(26,86,219,0.4)",
            borderRadius: "100px",
            padding: "5px 14px",
            fontSize: "11px",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "#6b9eff",
            marginBottom: "32px",
            background: "rgba(26,86,219,0.08)",
          }}
        >
          <span
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "#6b9eff",
              display: "inline-block",
            }}
          />
          Policy Intelligence Unit
        </div>

        {/* Heading */}
        <h1
          style={{
            fontSize: "clamp(2rem, 5vw, 3.25rem)",
            fontWeight: 400,
            lineHeight: 1.15,
            letterSpacing: "-0.02em",
            marginBottom: "20px",
            color: "#fff",
          }}
        >
          ServiceOntario
          <br />
          <span
            style={{ color: "rgba(255,255,255,0.35)", fontStyle: "italic" }}
          >
            Manual Search
          </span>
        </h1>

        {/* Subtext */}
        <p
          style={{
            fontSize: "15px",
            color: "rgba(255,255,255,0.45)",
            lineHeight: 1.7,
            marginBottom: "40px",
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            fontWeight: 400,
          }}
        >
          Ask plain-English questions. Get answers sourced directly from
          official ServiceOntario manuals — with page citations. No
          hallucinations, no internet search.
        </p>

        {/* CTA */}
        <Link href="/manuals" className="cta-link">
          Open Manual Search
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
          >
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </Link>

        {/* Feature pills */}
        <div
          style={{
            display: "flex",
            gap: "12px",
            justifyContent: "center",
            flexWrap: "wrap",
            marginTop: "56px",
          }}
        >
          {features.map(({ icon, label, detail }) => (
            <div
              key={label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: "10px",
                padding: "10px 16px",
                fontFamily:
                  "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
              }}
            >
              <span style={{ fontSize: "16px" }}>{icon}</span>
              <div style={{ textAlign: "left" }}>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "rgba(255,255,255,0.8)",
                  }}
                >
                  {label}
                </div>
                <div
                  style={{
                    fontSize: "11px",
                    color: "rgba(255,255,255,0.35)",
                    marginTop: "1px",
                  }}
                >
                  {detail}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer note */}
        <p
          style={{
            marginTop: "48px",
            fontSize: "11px",
            color: "rgba(255,255,255,0.2)",
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            letterSpacing: "0.04em",
          }}
        >
          Answers sourced exclusively from official manuals · Not affiliated
          with the Government of Ontario
        </p>
      </div>
    </main>
  );
}
