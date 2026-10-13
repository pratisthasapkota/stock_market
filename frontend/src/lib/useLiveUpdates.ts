import { useEffect, useRef, useState } from "react";
import { getToken } from "./api";

export interface LiveEvent {
  type: string;
  [key: string]: unknown;
}

const BASE = (import.meta.env.VITE_API_BASE as string) || "";

function wsUrl(token: string): string {
  if (BASE) {
    const url = new URL(BASE);
    const proto = url.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${url.host}/ws/updates?token=${encodeURIComponent(token)}`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/updates?token=${encodeURIComponent(token)}`;
}

/** Opens one socket and hands every frame to onEvent. Reconnects with a
 *  backoff so a dropped wifi or a backend restart doesn't kill the dashboard. */
export function useLiveUpdates(onEvent: (e: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let socket: WebSocket | null = null;
    let closed = false;
    let delay = 1000;

    const connect = () => {
      socket = new WebSocket(wsUrl(token));
      socket.onopen = () => {
        setConnected(true);
        delay = 1000;
      };
      socket.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as LiveEvent;
          if (data.type !== "hello") handler.current(data);
        } catch {
          /* ignore malformed frame */
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) {
          setTimeout(connect, delay);
          delay = Math.min(delay * 2, 15000);
        }
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    const ping = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, 25000);

    return () => {
      closed = true;
      clearInterval(ping);
      socket?.close();
    };
  }, []);

  return { connected };
}
