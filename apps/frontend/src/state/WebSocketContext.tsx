import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth } from './auth.ts';

  type WebSocketContextType = {
    socket: WebSocket | null;
  };
  
  const WebSocketContext = createContext<WebSocketContextType>({
    socket: null,
  });
  
  export const useWebSocket = () => useContext(WebSocketContext);
  
  export const WebSocketProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const { user, loading } = useAuth();
  
    useEffect(() => {
        if (loading || !user) return; 

        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const host = window.location.host;
        const ws = new WebSocket(`${protocol}://${host}/api/ws/global`);
      
        console.log("[WebSocket] Attempting connection to", ws.url);
      
        ws.onopen = () => {
          console.log('[WebSocket] Connected');
          setSocket(ws);
        };
      
        ws.onclose = () => {
          console.log('[WebSocket] Disconnected');
          setSocket(null);
        };

        ws.onmessage = (e) => {
          console.log("[WebSocket] Message received:", e.data);
        };          
      
        ws.onerror = (e) => {
          console.error('[WebSocket] Error', e);
        };
      
        return () => {
          console.log("[WebSocket] Closing socket...");
          ws.close();
        };
    }, [user, loading]);      
  
    return (
      <WebSocketContext.Provider value={{ socket }}>
        {children}
      </WebSocketContext.Provider>
    );
  };
  