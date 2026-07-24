import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import ActiveGames from "@/pages/games/ActiveGames";
import CompletedGames from "@/pages/games/CompletedGames";
import JoinGame from "@/pages/games/JoinGame";

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

const sampleGames = [
  {
    id: 1,
    link: "forest-a",
    game_name: "Forest Fight",
    gamemode: "Conquest",
    max_players: 2,
    map_name: "Forest",
    timestamp: "2026-01-02T00:00:00Z",
    host: { username: "ash" },
    host_id: 10,
    players: [
      { player_id: 10, username: "ash" },
      { player_id: 20, username: "misty" },
    ],
  },
  {
    id: 2,
    link: "beach-b",
    game_name: "",
    gamemode: "War",
    max_players: 4,
    map_name: "Beach",
    timestamp: "2026-01-01T00:00:00Z",
    host: { username: "brock" },
    host_id: 30,
    players: [{ player_id: 30, username: "brock" }],
  },
];

function mockListApis(listUrl: string) {
  vi.mocked(secureFetch).mockImplementation(async (url) => {
    if (String(url).includes(listUrl)) {
      return { ok: true, json: async () => sampleGames } as Response;
    }
    if (String(url).includes("/api/me")) {
      return { ok: true, json: async () => ({ id: 10 }) } as Response;
    }
    if (String(url).includes("/join/")) {
      return { ok: true, json: async () => ({ link: "joined-link" }) } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}

describe("game list pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  it("ActiveGames lists, filters, reloads, and spectates", async () => {
    const user = userEvent.setup();
    mockListApis("/games/in_progress");

    render(
      <MemoryRouter>
        <ActiveGames />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();
    expect(screen.getByText("Untitled Game")).toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue("All Players"), "2");
    expect(screen.getByText("Forest Fight")).toBeInTheDocument();
    expect(screen.queryByText("Untitled Game")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue("2 Players"), "All");
    const mapFilter = screen.getByPlaceholderText(/Filter by Map/i);
    await user.clear(mapFilter);
    await user.type(mapFilter, "Beach");
    expect(screen.getByText("Untitled Game")).toBeInTheDocument();
    expect(screen.queryByText("Forest Fight")).not.toBeInTheDocument();

    await user.click(screen.getByTitle("Reload games"));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith("/api/games/in_progress");
    });

    await user.clear(mapFilter);
    await user.type(mapFilter, "All");
    await user.click(screen.getAllByRole("button", { name: "Spectate" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/games/forest-a");
  });

  it("CompletedGames lists and spectates", async () => {
    const user = userEvent.setup();
    mockListApis("/games/completed");

    render(
      <MemoryRouter>
        <CompletedGames />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Review" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/games/forest-a");
  });

  it("JoinGame joins open games and disables join when already seated", async () => {
    const user = userEvent.setup();
    mockListApis("/games/open");

    render(
      <MemoryRouter>
        <JoinGame />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();

    // User id 10 is already in Forest Fight
    const joinButtons = screen.getAllByRole("button", { name: "Join" });
    expect(joinButtons[0]).toBeDisabled();
    expect(joinButtons[1]).toBeEnabled();

    await user.click(joinButtons[1]);
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith("/api/games/join/2", { method: "POST" });
      expect(mockNavigate).toHaveBeenCalledWith("/games/joined-link");
    });

    await user.click(screen.getAllByRole("button", { name: "Spectate" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/games/forest-a");
  });

  it("JoinGame alerts when join fails", async () => {
    const user = userEvent.setup();
    vi.mocked(secureFetch).mockImplementation(async (url) => {
      if (String(url).includes("/games/open")) {
        return {
          ok: true,
          json: async () => [sampleGames[1]],
        } as Response;
      }
      if (String(url).includes("/api/me")) {
        return { ok: true, json: async () => ({ id: 99 }) } as Response;
      }
      if (String(url).includes("/join/")) {
        return { ok: false, json: async () => ({}) } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(
      <MemoryRouter>
        <JoinGame />
      </MemoryRouter>
    );

    expect(await screen.findByText("Untitled Game")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Join" }));
    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith("Failed to join game");
    });
  });
});
