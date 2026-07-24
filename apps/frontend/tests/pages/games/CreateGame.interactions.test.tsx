import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import CreateGame from "@/pages/games/CreateGame";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

import { secureFetch } from "@/utils/secureFetch";

const maps = [
  {
    id: 1,
    name: "Arena",
    width: 10,
    height: 10,
    allowed_modes: ["Conquest", "War", "Capture The Flag"],
    allowed_player_counts: [2, 4],
  },
];

describe("CreateGame", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(secureFetch).mockImplementation(async (url, init) => {
      if (String(url).includes("/maps")) {
        return { ok: true, json: async () => maps } as Response;
      }
      if (String(url).includes("/api/me")) {
        return { ok: true, json: async () => ({ id: 123 }) } as Response;
      }
      if (String(url).includes("/games/create") && init?.method === "POST") {
        return { ok: true, json: async () => ({ link: "new-game" }) } as Response;
      }
      return { ok: true, json: async () => [] } as Response;
    });
  });

  it("loads maps and creates a conquest game", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CreateGame />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Create a Game/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue(/Arena/)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Game Name/i), "My Match");
    await user.click(screen.getByLabelText(/Private Game/i));
    await user.click(screen.getByLabelText(/Allow TM items/i));
    await user.click(screen.getByRole("button", { name: /Create Game/i }));

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        "/api/games/create",
        expect.objectContaining({ method: "POST" })
      );
      expect(mockNavigate).toHaveBeenCalledWith("/games/new-game");
    });
  });

  it("applies War defaults and clamps max turns", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CreateGame />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue(/Arena/)).toBeInTheDocument();
    });

    const modeSelect = screen.getByDisplayValue(/Conquest/i);
    await user.selectOptions(modeSelect, "War");
    expect(screen.getByText(/Cash Per Turn/i)).toBeInTheDocument();
    expect(screen.getByText(/Unit Limit/i)).toBeInTheDocument();

    const maxTurns = screen.getByDisplayValue("10");
    await user.clear(maxTurns);
    await user.type(maxTurns, "5");
    fireEvent.blur(maxTurns);
    expect((maxTurns as HTMLInputElement).value).toBe("10");

    await user.clear(maxTurns);
    await user.type(maxTurns, "120");
    fireEvent.blur(maxTurns);
    expect((maxTurns as HTMLInputElement).value).toBe("99");
  });
});
