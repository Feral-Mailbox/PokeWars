import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InvitePlayerModal from "@/components/InvitePlayerModal";

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

import { secureFetch } from "@/utils/secureFetch";

describe("InvitePlayerModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <InvitePlayerModal gameId={1} open={false} onClose={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("searches players and invites successfully", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClose = vi.fn();
    const onInvited = vi.fn();

    vi.mocked(secureFetch).mockImplementation(async (url: string) => {
      if (String(url).includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [{ id: 9, username: "misty", trainer_id: "T1" }],
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({ ok: true }),
      } as Response;
    });

    render(
      <InvitePlayerModal gameId={42} open onClose={onClose} onInvited={onInvited} />,
    );

    expect(screen.getByRole("dialog", { name: /invite player/i })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "mis");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(await screen.findByText("misty")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^invite$/i }));

    await waitFor(() => {
      expect(onInvited).toHaveBeenCalledWith("misty");
    });
    expect(screen.getByRole("status")).toHaveTextContent(/invited misty/i);

    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows API detail errors and empty search results", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    vi.mocked(secureFetch).mockImplementation(async (url: string) => {
      if (String(url).includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [],
        } as Response;
      }
      return {
        ok: false,
        json: async () => ({ detail: "Already invited" }),
      } as Response;
    });

    render(<InvitePlayerModal gameId={1} open onClose={vi.fn()} />);

    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "x");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(await screen.findByText(/no players found/i)).toBeInTheDocument();

    // Force invite path via a successful search then error invite
    vi.mocked(secureFetch).mockImplementation(async (url: string) => {
      if (String(url).includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [{ id: 3, username: "brock", trainer_id: "T2" }],
        } as Response;
      }
      return {
        ok: false,
        json: async () => ({ detail: "Already invited" }),
      } as Response;
    });

    await user.clear(screen.getByPlaceholderText(/username or trainer id/i));
    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "bro");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(await screen.findByText("brock")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^invite$/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/already invited/i);
  });

  it("handles search failure and invite network errors", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    vi.mocked(secureFetch).mockRejectedValueOnce(new Error("network"));

    render(<InvitePlayerModal gameId={1} open onClose={vi.fn()} />);
    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "ash");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    await waitFor(() => {
      expect(screen.queryByText(/searching/i)).not.toBeInTheDocument();
    });

    vi.mocked(secureFetch).mockImplementation(async (url: string) => {
      if (String(url).includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [{ id: 1, username: "ash", trainer_id: "T0" }],
        } as Response;
      }
      throw new Error("invite failed");
    });

    await user.clear(screen.getByPlaceholderText(/username or trainer id/i));
    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "ash");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(await screen.findByText("ash")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^invite$/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/could not send invitation/i);
  });

  it("falls back when invite errors lack a string detail", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.mocked(secureFetch).mockImplementation(async (url: string) => {
      if (String(url).includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [{ id: 8, username: "gary", trainer_id: "T9" }],
        } as Response;
      }
      return {
        ok: false,
        json: async () => ({ detail: { code: 1 } }),
      } as Response;
    });

    render(<InvitePlayerModal gameId={1} open onClose={vi.fn()} />);
    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "gar");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(await screen.findByText("gary")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^invite$/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/could not send invitation/i);
  });
});
