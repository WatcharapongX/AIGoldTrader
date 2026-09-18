import { getValidAccessToken } from '@/lib/auth-coordinator';
import { clearSession } from '@/lib/api';

export type WsMessageHandler = (data: unknown) => void;

export class WsClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // starts at 1s, exponential backoff up to 30s
  private handlers: Map<string, Set<WsMessageHandler>> = new Map();
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;
  private authRetryCount = 0;
  private connectedAt = 0;

  constructor(baseUrl?: string, private onClearSession?: () => void) {
    if (baseUrl) {
      this.url = baseUrl;
    } else if (process.env.NEXT_PUBLIC_WS_URL) {
      this.url = process.env.NEXT_PUBLIC_WS_URL;
    } else if (typeof window !== 'undefined') {
      const host =
        window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.url = `${protocol}//${host}:8000/ws`;
    } else {
      this.url = 'ws://127.0.0.1:8000/ws';
    }
  }

  async connect(forceRefreshToken = false): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.intentionalClose = false;

    let token: string | null = null;
    try {
      token = forceRefreshToken
        ? await getValidAccessToken({ forceRefresh: true })
        : await getValidAccessToken();
    } catch {
      // Connection fails closed if token cannot be supplied
      return;
    }

    if (this.intentionalClose) return;

    // Strict invariant: token is NEVER placed in URL
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
      this.connectedAt = Date.now();
      // Notice: authRetryCount is NOT reset merely on TCP onopen before healthy auth is proven.
      // First frame authentication
      if (token && this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'auth', token }));
      }
      this.startHeartbeat();
    };

    this.ws.onmessage = this.onMessage.bind(this);
    this.ws.onclose = this.onClose.bind(this);
    this.ws.onerror = this.onError.bind(this);
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  subscribe(topic: string, handler: WsMessageHandler): () => void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, new Set());
    }
    this.handlers.get(topic)!.add(handler);

    return () => {
      const topicHandlers = this.handlers.get(topic);
      if (topicHandlers) {
        topicHandlers.delete(handler);
        if (topicHandlers.size === 0) {
          this.handlers.delete(topic);
        }
      }
    };
  }

  send(type: string, payload: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
    }
  }

  private onMessage(event: MessageEvent): void {
    try {
      // Valid message receipt proves authenticated connection; reset auth retry budget
      this.authRetryCount = 0;
      const data = JSON.parse(event.data);
      if (data && data.type) {
        const topicHandlers = this.handlers.get(data.type);
        if (topicHandlers) {
          topicHandlers.forEach((handler) => handler(data.payload));
        }
      }
    } catch {
      // Ignore malformed messages
    }
  }

  private onClose(event: CloseEvent): void {
    this.stopHeartbeat();
    if (this.intentionalClose) return;

    if (event.code === 4401) {
      if (this.authRetryCount >= 1) {
        if (this.onClearSession) {
          this.onClearSession();
        } else {
          clearSession({ broadcast: true });
        }
        return;
      }
      this.authRetryCount++;
      void this.connect(true);
      return;
    }

    if (event.code === 1008) {
      return;
    }

    this.scheduleReconnect();
  }

  private onError(): void {
    // onClose handles reconnection logic
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      this.send('ping', { timestamp: Date.now() });
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
      void this.connect();
    }, this.reconnectDelay);
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new WsClient();
