import { parseMessage } from './contracts';
import type { MarketMessage, Timeframe } from '@/types/market.generated';
import { getValidAccessToken } from '@/lib/auth-coordinator';
import { clearSession } from '@/lib/api';

export type ConnectionState =
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'STALE'
  | 'DISCONNECTED'
  | 'ERROR';

export const reconnectDelay = (attempt: number) => Math.min(1000 * 2 ** attempt, 30000);

function defaultMarketWsUrl(): string {
  if (process.env.NEXT_PUBLIC_WS_URL) return `${process.env.NEXT_PUBLIC_WS_URL}/market`;
  if (typeof window !== 'undefined') {
    const host =
      window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}:8000/ws/market`;
  }
  return 'ws://127.0.0.1:8000/ws/market';
}

/** A connection owns its socket, timers and subscriptions; resubscribe always requests a fresh snapshot. */
export class MarketConnection {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private stopped = true;
  private attempts = 0;
  private lastMessage = 0;
  private opened = 0;
  private lastSequence = -1;
  private authRetryCount = 0;

  constructor(
    private token: () => Promise<string> = () => getValidAccessToken(),
    private onMessage: (message: MarketMessage) => void,
    private onState: (state: ConnectionState) => void,
    private symbol: string,
    private timeframe: Timeframe,
    private url = defaultMarketWsUrl(),
  ) {}

  start() {
    this.stopped = false;
    this.authRetryCount = 0;
    void this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.watchdog) clearInterval(this.watchdog);
    this.timer = this.watchdog = null;
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
  }

  private async connect(forceRefreshToken = false) {
    if (this.stopped) return;
    this.onState(this.attempts ? 'RECONNECTING' : 'CONNECTING');
    try {
      const token = forceRefreshToken
        ? await getValidAccessToken({ forceRefresh: true })
        : await this.token();
      if (this.stopped) return;

      const socket = new WebSocket(this.url);
      this.socket = socket;
      this.lastSequence = -1;
      this.lastMessage = Date.now();
      this.opened = 0;

      socket.onopen = () => {
        this.opened = Date.now();
        socket.send(JSON.stringify({ type: 'auth', token }));
        socket.send(
          JSON.stringify({
            type: 'subscribe',
            symbol: this.symbol,
            timeframe: this.timeframe,
          }),
        );
      };

      socket.onmessage = (event) => {
        try {
          const message = parseMessage(JSON.parse(event.data));
          if (
            message.symbol !== this.symbol ||
            message.timeframe !== this.timeframe
          ) {
            return;
          }
          this.lastMessage = Date.now();
          if (message.type === 'update' && message.sequence <= this.lastSequence) {
            return;
          }
          this.lastSequence = Math.max(this.lastSequence, message.sequence);
          // Only a sustained healthy connection resets the bounded retry budget.
          if (Date.now() - this.opened >= 10000) {
            this.attempts = 0;
            this.authRetryCount = 0;
          }
          this.onState(message.status.status);
          this.onMessage(message);
        } catch {
          this.onState('ERROR');
          socket.close(1008, 'Invalid market contract');
        }
      };

      socket.onerror = () => this.onState('RECONNECTING');

      socket.onclose = (event) => {
        if (this.watchdog) clearInterval(this.watchdog);
        this.watchdog = null;
        this.socket = null;

        if (event.code === 1008) {
          this.onState('ERROR');
          return;
        }

        if (event.code === 4401) {
          if (this.authRetryCount >= 1) {
            this.onState('ERROR');
            clearSession();
            return;
          }
          this.authRetryCount++;
          this.onState('RECONNECTING');
          this.timer = setTimeout(() => {
            this.timer = null;
            void this.connect(true);
          }, 1000);
          return;
        }

        this.retry();
      };

      this.watchdog = setInterval(() => {
        if (Date.now() - this.lastMessage > 8000) {
          this.onState('STALE');
          socket.close();
        }
      }, 1000);
    } catch {
      this.retry();
    }
  }

  private retry() {
    if (this.stopped) return;
    if (this.attempts >= 10) {
      this.onState('DISCONNECTED');
      return;
    }
    this.onState('RECONNECTING');
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.connect();
    }, reconnectDelay(this.attempts++));
  }
}
