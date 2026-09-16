import { MarketAnalysisScreen } from '@/features/analysis/MarketAnalysisScreen';

type AnalysisPageProps = { searchParams: Promise<Record<string, string | string[] | undefined>> };
const allowedTimeframes = new Set(['M1', 'M5', 'M15', 'H1', 'H4', 'D1', 'W1']);

function safeQuery(value: string | string[] | undefined, pattern: RegExp, maxLength: number) {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate && candidate.length <= maxLength && pattern.test(candidate) ? candidate : null;
}

export default async function AnalysisPage({ searchParams }: AnalysisPageProps) {
  const query = await searchParams;
  const candidate = safeQuery(query.candidate, /^[A-Za-z0-9._:-]+$/, 200);
  const symbol = safeQuery(query.symbol, /^[A-Za-z0-9._-]+$/, 30);
  const requestedTimeframe = Array.isArray(query.timeframe) ? query.timeframe[0] : query.timeframe;
  const timeframe = requestedTimeframe && allowedTimeframes.has(requestedTimeframe) ? requestedTimeframe : null;
  return (
    <MarketAnalysisScreen
      initialCandidateId={candidate}
      initialSymbol={symbol}
      initialTimeframe={timeframe}
    />
  );
}
