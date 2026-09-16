import { TradingSignalsScreen } from '@/features/strategy/TradingSignalsScreen';

export default async function SignalsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const raw = Array.isArray(query.candidate) ? query.candidate[0] : query.candidate;
  const candidate = raw && raw.length <= 200 && /^[A-Za-z0-9._:-]+$/.test(raw) ? raw : null;
  return <TradingSignalsScreen initialCandidateId={candidate} />;
}
