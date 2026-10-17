import { ImageResponse } from "next/og";
import perf from "@/data/report-performance.json";

// ─── Static OG image — editorial paper/ink design ─────────────────────────────
// 판결 아카이브 masthead, mosaic-strip motif (verdict wall), stamp-red accent.
// Built statically at build time; font fetched from Google Fonts (glyph subset).
// If the font fetch fails, falls back to a Latin-only design (no tofu).

export const alt = "판결 아카이브 — 시간이 매긴 성적표";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Editorial palette (matches globals.css light theme)
const PAPER = "#f5f1e8";
const INK = "#241d17";
const MUTED = "#6f655a";
const STAMP = "#b62236"; // hsl(354 70% 42%) — stamp red (KR up)
const DOWN = "#2c5cb0";  // hsl(219 62% 45%) — KR down blue
const NEUTRAL = "#d8d0c2";

type PerfRecord = {
  report_date?: string | null;
  return_latest_pct?: number | null;
};

/** Fetch a glyph-subset TTF/OTF of Noto Serif KR from Google Fonts. */
async function loadKoreanFont(text: string): Promise<ArrayBuffer | null> {
  try {
    const cssUrl = `https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@900&text=${encodeURIComponent(text)}`;
    const cssRes = await fetch(cssUrl, {
      signal: AbortSignal.timeout(5_000),
      headers: {
        // TTF-serving UA — satori cannot parse woff2
        "User-Agent":
          "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; de-at) AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1",
      },
    });
    if (!cssRes.ok) return null;
    const css = await cssRes.text();
    const match = css.match(/src:\s*url\((.+?)\)\s*format\(['"]?(?:opentype|truetype)['"]?\)/);
    if (!match) return null;
    const fontRes = await fetch(match[1], { signal: AbortSignal.timeout(5_000) });
    if (!fontRes.ok) return null;
    return await fontRes.arrayBuffer();
  } catch {
    return null;
  }
}

/** Mosaic strip: most recent reports, red = up / blue = down (KR convention). */
function buildMosaic(): { color: string }[] {
  const records = (perf as { records?: PerfRecord[] }).records ?? [];
  const recent = [...records]
    .filter((r) => r.report_date)
    .sort((a, b) => String(b.report_date).localeCompare(String(a.report_date)))
    .slice(0, 96);
  return recent.map((r) => {
    const v = r.return_latest_pct;
    if (v == null || !isFinite(v)) return { color: NEUTRAL };
    return { color: v >= 0 ? STAMP : DOWN };
  });
}

export default async function OgImage() {
  const records = (perf as { records?: PerfRecord[] }).records ?? [];
  const reportCount = records.length;
  const countStr = reportCount.toLocaleString("ko-KR");

  const headline = "판결 아카이브";
  const subline = `여섯 학회 · ${countStr}건의 리포트 · 시장의 판결`;
  const tagline = "시간이 매긴 성적표";
  const fontText = headline + subline + tagline + "0123456789·,";

  const fontData = await loadKoreanFont(fontText);
  const mosaic = buildMosaic();

  const useKorean = fontData != null;
  const fonts = useKorean
    ? [{ name: "NotoSerifKR", data: fontData!, weight: 900 as const, style: "normal" as const }]
    : undefined;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          backgroundColor: PAPER,
          fontFamily: useKorean ? "NotoSerifKR, serif" : "serif",
          padding: "56px 72px 0 72px",
          position: "relative",
        }}
      >
        {/* Top rule — newspaper double border */}
        <div style={{ display: "flex", flexDirection: "column", width: "100%" }}>
          <div style={{ height: 6, backgroundColor: INK, width: "100%" }} />
          <div style={{ height: 1.5, backgroundColor: INK, width: "100%", marginTop: 4 }} />
        </div>

        {/* Eyebrow */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: 28,
            fontSize: 22,
            letterSpacing: 8,
            color: MUTED,
          }}
        >
          <span>VERDICT ARCHIVE</span>
          <span
            style={{
              border: `3px solid ${STAMP}`,
              color: STAMP,
              padding: "6px 18px",
              fontSize: 20,
              letterSpacing: 4,
              transform: "rotate(-3deg)",
            }}
          >
            {useKorean ? "판결" : "VERDICT"}
          </span>
        </div>

        {/* Masthead */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginTop: 18,
          }}
        >
          <div
            style={{
              fontSize: 132,
              fontWeight: 900,
              color: INK,
              lineHeight: 1.05,
              letterSpacing: -2,
            }}
          >
            {useKorean ? headline : "Verdict Archive"}
          </div>
          <div
            style={{
              marginTop: 14,
              fontSize: 34,
              color: MUTED,
            }}
          >
            {useKorean ? subline : `6 clubs · ${countStr} reports · judged by the market`}
          </div>
        </div>

        {/* Tagline with stamp accent */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginTop: 26,
            gap: 16,
          }}
        >
          <div style={{ width: 52, height: 5, backgroundColor: STAMP, display: "flex" }} />
          <div style={{ fontSize: 30, color: INK }}>
            {useKorean ? tagline : "the report card written by time"}
          </div>
        </div>

        {/* Mosaic strip — verdict wall motif */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            display: "flex",
            flexDirection: "column",
            padding: "0 72px 48px 72px",
          }}
        >
          <div style={{ height: 1.5, backgroundColor: INK, width: "100%", marginBottom: 18 }} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {mosaic.map((cell, i) => (
              <div
                key={i}
                style={{
                  width: 17,
                  height: 17,
                  backgroundColor: cell.color,
                  opacity: 0.92,
                }}
              />
            ))}
          </div>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}
