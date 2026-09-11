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

  constructor(baseUrl?: string) {
    if (baseUrl) {
      this.url = baseUrl;
    } else if (process.env.NEXT_PUBLIC_WS_URL) {
      this.url = process.env.NEXT_PUBLIC_WS_URL;
    } else if (typeof window !== 'undefined') {
      const host = window.location.hostname === 'localhost' ? '127.0.0.1' : window.location.hostname;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.url = `${protocol}//${host}:8000/ws`;
    } else {
      this.url = 'ws://127.0.0.1:8000/ws';
    }
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.intentionalClose = false;
    let connectUrl = this.url;
    
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        const separator = this.url.includes('?') ? '&' : '?';
        connectUrl = `${this.url}${separator}token=${encodeURIComponent(token)}`;
      }
    }

    this.ws = new WebSocket(connectUrl);

    this.ws.onopen = this.onOpen.bind(this);
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
    } else {
      console.warn('WebSocket is not connected. Cannot send message.');
    }
  }

  private onOpen(): void {
    console.log('[WsClient] Connected to', this.url);
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.startHeartbeat();
  }

  private onMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data);
      if (data && data.type) {
        const topicHandlers = this.handlers.get(data.type);
        if (topicHandlers) {
          topicHandlers.forEach(handler => handler(data.payload));
        }
      }
    } catch (err) {
      console.error('[WsClient] Failed to parse message', err);
    }
  }

  private onClose(event: CloseEvent): void {
    console.log('[WsClient] Disconnected', event.reason);
    this.stopHeartbeat();
    if (!this.intentionalClose) {
      this.scheduleReconnect();
    }
  }

  private onError(event: Event): void {
    console.error('[WsClient] WebSocket Error', event);
    // onClose will be called right after onError, where reconnect happens.
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
      console.error('[WsClient] Max reconnect attempts reached');
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
      console.log(`[WsClient] Reconnecting... (Attempt ${this.reconnectAttempts})`);
      this.connect();
    }, this.reconnectDelay);
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new WsClient();
