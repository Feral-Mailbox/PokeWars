import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useAuth } from './auth.ts';
import type { InvitationWsEvent } from '../types/invitation';

type GlobalWsListener = (payload: InvitationWsEvent | Record<string, unknown>) => void;

type WebSocketContextType = {
  socket: WebSocket | null;
  lastInvitationEvent: InvitationWsEvent | null;
  subscribe: (listener: GlobalWsListener) => () => void;
};

const WebSocketContext = createContext<WebSocketContextType>({
  socket: null,
  lastInvitationEvent: null,
  subscribe: () => () => undefined,
});

export const useWebSocket = () => useContext(WebSocketContext);

export const WebSocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [lastInvitationEvent, setLastInvitationEvent] = useState<InvitationWsEvent | null>(null);
  const { user, loading } = useAuth();
  const listenersRef = useRef(new Set<GlobalWsListener>());

  const subscribe = useCallback((listener: GlobalWsListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  useEffect(() => {
    if (loading || !user) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}://${host}/api/ws/global`);

    ws.onopen = () => {
      setSocket(ws);
    };

    ws.onclose = () => {
      setSocket(null);
    };

    ws.onmessage = (e) => {
      if (typeof e.data !== 'string' || !e.data.startsWith('{')) return;
      try {
        const payload = JSON.parse(e.data) as InvitationWsEvent | Record<string, unknown>;
        if (
          payload &&
          typeof payload === 'object' &&
          (payload as InvitationWsEvent).event === 'invitation'
        ) {
          setLastInvitationEvent(payload as InvitationWsEvent);
        }
        listenersRef.current.forEach((listener) => listener(payload));
      } catch {
        // ignore malformed payloads
      }
    };

    ws.onerror = () => {
      // connection errors surface via onclose
    };

    return () => {
      ws.close();
    };
  }, [user, loading]);

  return (
    <WebSocketContext.Provider value={{ socket, lastInvitationEvent, subscribe }}>
      {children}
    </WebSocketContext.Provider>
  );
};
