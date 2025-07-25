import { render, screen, waitFor, act } from "@testing-library/react";
import { WebSocketProvider, useWebSocket } from "@/state/WebSocketContext";
import { vi } from "vitest";

// @ts-ignore - We will mock WebSocket
global.WebSocket = vi.fn(() => ({
  onopen: null,
  onclose: null,
  onerror: null,
  onmessage: null,
  close: vi.fn(),
})) as any;

describe("WebSocketContext", () => {
  let mockSocket: any;

  beforeEach(() => {
    mockSocket = {
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
      close: vi.fn(),
      url: "ws://localhost/api/ws/global",
    };
    global.WebSocket = vi.fn(() => mockSocket);
  });

  it("renders children", () => {
    render(
      <WebSocketProvider>
        <div>Connected!</div>
      </WebSocketProvider>
    );
    expect(screen.getByText("Connected!")).toBeInTheDocument();
  });

  it("sets socket on open and clears on close", async () => {
    function TestComponent() {
      const { socket } = useWebSocket();
      return <div>{socket ? "Socket Connected" : "Socket Null"}</div>;
    }

    render(
      <WebSocketProvider>
        <TestComponent />
      </WebSocketProvider>
    );

    expect(screen.getByText("Socket Null")).toBeInTheDocument();

    act(() => {
      mockSocket.onopen();
    });

    await waitFor(() => {
      expect(screen.getByText("Socket Connected")).toBeInTheDocument();
    });

    act(() => {
      mockSocket.onclose();
    });

    await waitFor(() => {
      expect(screen.getByText("Socket Null")).toBeInTheDocument();
    });
  });

  it("logs messages received", () => {
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    render(<WebSocketProvider><div /></WebSocketProvider>);

    const message = { data: "hello" };
    act(() => {
      mockSocket.onmessage(message);
    });

    expect(spy).toHaveBeenCalledWith("[WebSocket] Message received:", "hello");
    spy.mockRestore();
  });

  it("logs errors", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<WebSocketProvider><div /></WebSocketProvider>);

    const error = new Event("error");
    act(() => {
      mockSocket.onerror(error);
    });

    expect(spy).toHaveBeenCalledWith("[WebSocket] Error", error);
    spy.mockRestore();
  });

  it("closes socket on unmount", () => {
    const { unmount } = render(<WebSocketProvider><div /></WebSocketProvider>);
    unmount();
    expect(mockSocket.close).toHaveBeenCalled();
  });
});
