import type { Metadata } from "next";
import Link from "next/link";
import { promises as fs } from "node:fs";
import path from "node:path";
import { SiteHeader } from "@/components/site-header";
import { UsIndexMtfChart } from "@/components/strategy/us-index-mtf-chart";
import { formatPct } from "@/lib/utils";
import research from "@/data/us-index-mtf-decay.json";

export const metadata: Metadata = {
  title: "미국 지수 MTF 감쇠 전략 — 판결 아카이브",
  description: "QQQ·SOXX 다중 타임프레임 감쇠 분할매도 및 일괄 재매수 전략, 백테스트와 Pine Script.",
};

type Metrics = {
  start: string;
  end: string;
  total_return_pct: number;
  cagr_pct: number | null;
  sharpe: number | null;
  mdd_pct: number;
  events?: number;
  exit_events?: number;
  win_rate_pct?: number | null;
};

type EquityPoint = { date: string; nav: number };
type EventRow = {
  signal_date: string;
  fill_date: string;
  action: string;
  stage_after: number;
  fill_price: number;
  quantity: number;
  position_after_pct: number;
};

type Instrument = {
  symbol: string;
  label: string;
  data_start: string;
  data_end: string;
  strategy: { metrics: Metrics; equity: EquityPoint[]; events: EventRow[]; final_stage: number; final_exposure_pct: number };
  benchmark: { metrics: Metrics; equity: EquityPoint[] };
};

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-display text-2xl font-black tracking-tight">{value}</p>
      {note && <p className="mt-1 text-[11px] text-muted-foreground">{note}</p>}
    </div>
  );
}

export default async function UsIndexMtfDecayPage() {
  const pine = await fs.readFile(path.join(process.cwd(), "public", "pine", "us-index-mtf-decay.pine"), "utf8");
  const instruments = research.instruments as Instrument[];

  return (
    <main className="mx-auto max-w-[1500px] space-y-8 px-4 py-6 sm:px-8">
      <SiteHeader eyebrow="US Index MTF Research" />

      <section className="rounded-lg border-2 border-stamp bg-stamp/5 p-5 sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-4xl">
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-stamp">Research strategy · USD baseline</p>
            <h1 className="mt-2 font-display text-3xl font-black tracking-tight sm:text-5xl">미국 지수 MTF 감쇠 분할매도</h1>
            <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
              일봉·2일봉·주봉의 추세 훼손을 여섯 단계로 확인하면서 <strong className="text-foreground">매번 남은 수량</strong>의
              20%·20%·20%·20%·50%·50%를 줄이고, 조정 깊이에 맞는 회복 신호에서 가용 현금을 다시 투입합니다.
              나스닥100은 QQQ, 필라델피아 반도체 지수는 SOXX를 거래 가능한 대용물로 사용했습니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href="/pine/us-index-mtf-decay.pine" download className="rounded-md bg-stamp px-4 py-2 font-mono text-xs font-black text-background">
              Pine Script 다운로드
            </a>
            <a href={research.full_data_url} download className="rounded-md border border-stamp/50 bg-card px-4 py-2 font-mono text-xs font-bold text-stamp">
              전체 백테스트 JSON
            </a>
            <Link href="/strategy" className="rounded-md border border-border bg-card px-4 py-2 font-mono text-xs font-bold">
              전략 연구실로
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-3 lg:grid-cols-6" aria-label="6단계 규칙">
        {[
          ["1D", "종가 < 20SMA", "잔여 20%"],
          ["1D", "5SMA ↓ 20SMA", "잔여 20%"],
          ["2D", "종가 < 20SMA", "잔여 20%"],
          ["2D", "5SMA ↓ 20SMA", "잔여 20%"],
          ["1W", "종가 < 20SMA", "잔여 50%"],
          ["1W", "5SMA ↓ 20SMA", "잔여 50%"],
        ].map(([tf, trigger, action], index) => (
          <article key={`${tf}-${trigger}`} className="rounded-lg border border-border bg-card p-3">
            <p className="font-mono text-[10px] font-black text-stamp">STAGE {index + 1} · {tf}</p>
            <p className="mt-2 text-sm font-bold">{trigger}</p>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">{action}</p>
          </article>
        ))}
      </section>

      <section className="rounded-lg border border-border bg-card p-5">
        <h2 className="font-display text-2xl font-black tracking-tight">재진입 상태 머신</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div><p className="font-mono text-xs font-black text-stamp">1–2단계 후</p><p className="mt-1 text-sm leading-6 text-muted-foreground">완료된 주봉 종가가 주봉 20SMA 이상이고, 일봉 5SMA가 20SMA를 상향 돌파할 때.</p></div>
          <div><p className="font-mono text-xs font-black text-stamp">3–4단계 후</p><p className="mt-1 text-sm leading-6 text-muted-foreground">완료된 2일봉 종가가 2일봉 20SMA를 상향 돌파할 때.</p></div>
          <div><p className="font-mono text-xs font-black text-stamp">5–6단계 후</p><p className="mt-1 text-sm leading-6 text-muted-foreground">완료된 주봉 종가가 주봉 20SMA를 상향 돌파할 때.</p></div>
        </div>
      </section>

      {instruments.map((instrument) => {
        const sm = instrument.strategy.metrics;
        const bm = instrument.benchmark.metrics;
        const recent = instrument.strategy.events.slice(-12).reverse();
        return (
          <section key={instrument.symbol} className="space-y-4 rounded-lg border-2 border-foreground/60 bg-card p-5 shadow-[4px_4px_0_0_hsl(var(--foreground)/0.45)]">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <p className="font-mono text-[11px] font-black uppercase tracking-[0.18em] text-stamp">{instrument.symbol} · USD</p>
                <h2 className="font-display text-3xl font-black tracking-tight">{instrument.label}</h2>
              </div>
              <p className="font-mono text-[11px] text-muted-foreground">{sm.start} → {sm.end}</p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <Stat label="전략 CAGR" value={formatPct(sm.cagr_pct, 2)} note={`보유 ${formatPct(bm.cagr_pct, 2)}`} />
              <Stat label="전략 총수익" value={formatPct(sm.total_return_pct, 1)} note={`보유 ${formatPct(bm.total_return_pct, 1)}`} />
              <Stat label="전략 MDD" value={formatPct(sm.mdd_pct, 1)} note={`보유 ${formatPct(bm.mdd_pct, 1)}`} />
              <Stat label="전략 Sharpe" value={sm.sharpe?.toFixed(2) ?? "—"} note={`보유 ${bm.sharpe?.toFixed(2) ?? "—"}`} />
              <Stat label="분할매도" value={`${sm.exit_events ?? 0}회`} note={`수익 매도 ${formatPct(sm.win_rate_pct, 1)}`} />
              <Stat label="현재 상태" value={`Stage ${instrument.strategy.final_stage}`} note={`노출 ${instrument.strategy.final_exposure_pct.toFixed(1)}%`} />
            </div>

            <div className="rounded-lg border border-border bg-background/40 p-3">
              <UsIndexMtfChart symbol={instrument.symbol} strategy={instrument.strategy.equity} benchmark={instrument.benchmark.equity} />
            </div>

            <details className="rounded-lg border border-border bg-background/30 p-4">
              <summary className="cursor-pointer font-display text-lg font-black">최근 체결 이벤트 12건</summary>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-xs">
                  <thead className="border-b border-border font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="py-2">신호일</th><th>체결일</th><th>행동</th><th>가격</th><th>수량</th><th>잔여 비중</th></tr></thead>
                  <tbody>{recent.map((event, index) => <tr key={`${event.fill_date}-${event.action}-${index}`} className="border-b border-border/50"><td className="py-2 font-mono">{event.signal_date}</td><td className="font-mono">{event.fill_date}</td><td className="font-bold">{event.action}</td><td>${event.fill_price.toFixed(2)}</td><td>{event.quantity.toFixed(3)}</td><td>{event.position_after_pct.toFixed(2)}%</td></tr>)}</tbody>
                </table>
              </div>
            </details>
          </section>
        );
      })}

      <section className="rounded-lg border border-border bg-card p-5">
        <h2 className="font-display text-2xl font-black tracking-tight">체결·데이터 가정</h2>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
          <li>· 일봉 신호는 완료된 일봉에서, 2D·주봉 신호는 확정된 이전 상위 봉이 다음 일봉에 공개된 뒤 의사결정하며 그 다음 시가에 체결합니다. 미래 데이터와 진행 중 상위 봉은 사용하지 않습니다.</li>
          <li>· 수수료는 체결당 0.01%, 슬리피지는 주당 $0.02를 적용했습니다.</li>
          <li>· 배당·분할 조정 OHLC를 사용하며, 세금·환전비용·시장충격은 제외했습니다.</li>
          <li>· Python의 2일봉은 고정 2일 달력 버킷 대용치입니다. TradingView 네이티브 2D는 휴일 주변에서 경계가 달라질 수 있습니다.</li>
          <li>· 환율 필터는 계좌·상품·환전 방식에 따라 결과가 달라 USD 기준 성과에는 포함하지 않았습니다. Pine 차트에는 USD/KRW 주봉 20SMA 이탈 경고만 표시합니다.</li>
          <li>· 결과상 이 전략은 두 ETF 모두 매수 후 보유보다 수익률이 낮고 낙폭은 작았습니다. 수익 극대화보다 하락 위험 완화 성격이 강합니다.</li>
        </ul>
      </section>

      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-2xl font-black tracking-tight">Pine Script v6</h2>
          <a href="/pine/us-index-mtf-decay.pine" download className="font-mono text-xs font-black text-stamp underline underline-offset-4">원본 파일 다운로드</a>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">TradingView의 QQQ 또는 SOXX 표준 일봉 차트에 붙여 넣으세요. 비표준 캔들에서는 사용하지 마세요.</p>
        <pre className="mt-4 max-h-[720px] overflow-auto rounded-lg border border-border bg-background p-4 text-[11px] leading-5"><code>{pine}</code></pre>
      </section>

      <p className="border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
        생성 시각 {research.generated_at}. 과거 데이터 기반 연구이며 미래 수익을 보장하지 않습니다. “장기 우상향”과 “평균 회귀”는 보장이 아니라 검증 대상인 가정입니다.
      </p>
    </main>
  );
}
