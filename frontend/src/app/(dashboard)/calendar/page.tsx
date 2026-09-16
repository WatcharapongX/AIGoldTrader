import { CalendarWorkspace } from '@/features/news/CalendarWorkspace';
export default async function CalendarPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const raw = Array.isArray(query.event) ? query.event[0] : query.event;
  const event = raw && raw.length <= 200 && /^[A-Za-z0-9._:-]+$/.test(raw) ? raw : null;
  return <CalendarWorkspace initialEventId={event} />;
}
