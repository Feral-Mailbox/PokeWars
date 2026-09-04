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
    host_username: "ash",
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
    host_username: null,
    host_id: 30,
    players: [{ player_id: 30, username: "brock" }],
  },
];

function mockPagedListApis(listUrl: string, allGames = sampleGames) {
  vi.mocked(secureFetch).mockImplementation(async (url) => {
    const raw = String(url);
    if (raw.includes(listUrl)) {
      const parsed = new URL(raw, "http://local.test");
      const page = Number(parsed.searchParams.get("page") || 1);
      const pageSize = Number(parsed.searchParams.get("page_size") || 10);
      const maxPlayers = parsed.searchParams.get("max_players");
      const mapName = parsed.searchParams.get("map_name");
      let filtered = [...allGames];
      if (maxPlayers) {
        filtered = filtered.filter((g) => String(g.max_players) === maxPlayers);
      }
      if (mapName) {
        filtered = filtered.filter(
          (g) => g.map_name.toLowerCase() === mapName.toLowerCase()
        );
      }
      filtered.sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      const start = (page - 1) * pageSize;
      return {
        ok: true,
        json: async () => ({
          items: filtered.slice(start, start + pageSize),
          page,
          page_size: pageSize,
          total: filtered.length,
          as_of: "2026-01-15T00:00:00.000Z",
        }),
      } as Response;
    }
    if (raw.includes("/api/me")) {
      return { ok: true, json: async () => ({ id: 10 }) } as Response;
    }
    if (raw.includes("/join/")) {
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
    mockPagedListApis("/games/in_progress");

    render(
      <MemoryRouter>
        <ActiveGames />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();
    expect(screen.getByText("Untitled Game")).toBeInTheDocument();

    await user.selectOptions(screen.getByDisplayValue("All Players"), "2");
    await waitFor(() => {
      expect(screen.getByText("Forest Fight")).toBeInTheDocument();
      expect(screen.queryByText("Untitled Game")).not.toBeInTheDocument();
    });

    await user.selectOptions(screen.getByDisplayValue("2 Players"), "All");
    const mapFilter = screen.getByPlaceholderText(/Filter by Map/i);
    await user.clear(mapFilter);
    await user.type(mapFilter, "Beach");
    await waitFor(() => {
      expect(screen.getByText("Untitled Game")).toBeInTheDocument();
      expect(screen.getByText("brock")).toBeInTheDocument();
      expect(screen.queryByText("Forest Fight")).not.toBeInTheDocument();
    });

    await user.click(screen.getByTitle("Reload games"));
    await waitFor(() => {
      expect(
        vi.mocked(secureFetch).mock.calls.some(([url]) =>
          String(url).includes("/api/games/in_progress")
        )
      ).toBe(true);
    });

    await user.clear(mapFilter);
    await user.type(mapFilter, "All");
    await waitFor(() => {
      expect(screen.getByText("Forest Fight")).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole("button", { name: "Spectate" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/games/forest-a");
  });

  it("CompletedGames lists, filters, reloads, and spectates", async () => {
    const user = userEvent.setup();
    mockPagedListApis("/games/completed");

    render(
      <MemoryRouter>
        <CompletedGames />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();
    await user.selectOptions(screen.getByDisplayValue("All Players"), "2");
    await waitFor(() => {
      expect(screen.queryByText("Untitled Game")).not.toBeInTheDocument();
    });
    await user.selectOptions(screen.getByDisplayValue("2 Players"), "All");
    const mapFilter = screen.getByPlaceholderText(/Filter by Map/i);
    await user.clear(mapFilter);
    await user.type(mapFilter, "Beach");
    await waitFor(() => {
      expect(screen.getByText("Untitled Game")).toBeInTheDocument();
    });
    await user.clear(mapFilter);
    await user.type(mapFilter, "All");
    await user.click(screen.getByTitle("Reload games"));
    await waitFor(() => {
      expect(
        vi.mocked(secureFetch).mock.calls.some(([url]) =>
          String(url).includes("/api/games/completed")
        )
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText("Forest Fight")).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole("button", { name: "Review" })[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/games/forest-a");
  });

  it("JoinGame filters, reloads, joins open games, and disables already-seated players", async () => {
    const user = userEvent.setup();
    mockPagedListApis("/games/open");

    render(
      <MemoryRouter>
        <JoinGame />
      </MemoryRouter>
    );

    expect(await screen.findByText("Forest Fight")).toBeInTheDocument();
    await user.selectOptions(screen.getByDisplayValue("All Players"), "2");
    await waitFor(() => {
      expect(screen.queryByText("Untitled Game")).not.toBeInTheDocument();
    });
    await user.selectOptions(screen.getByDisplayValue("2 Players"), "All");
    const mapFilter = screen.getByPlaceholderText(/Filter by Map/i);
    await user.clear(mapFilter);
    await user.type(mapFilter, "Beach");
    await waitFor(() => {
      expect(screen.getByText("Untitled Game")).toBeInTheDocument();
    });
    await user.clear(mapFilter);
    await user.type(mapFilter, "All");
    await user.click(screen.getByTitle("Reload games"));
    await waitFor(() => {
      expect(
        vi.mocked(secureFetch).mock.calls.some(([url]) =>
          String(url).includes("/api/games/open")
        )
      ).toBe(true);
    });

    await waitFor(() => {
      expect(screen.getByText("Forest Fight")).toBeInTheDocument();
    });

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
      const raw = String(url);
      if (raw.includes("/games/open")) {
        return {
          ok: true,
          json: async () => ({
            items: [sampleGames[1]],
            page: 1,
            page_size: 10,
            total: 1,
            as_of: "2026-01-15T00:00:00.000Z",
          }),
        } as Response;
      }
      if (raw.includes("/api/me")) {
        return { ok: true, json: async () => ({ id: 99 }) } as Response;
      }
      if (raw.includes("/join/")) {
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

  it("paginates ActiveGames, CompletedGames, and JoinGame lists", async () => {
    const user = userEvent.setup();
    const manyGames = Array.from({ length: 12 }, (_, i) => ({
      id: i + 1,
      link: `game-${i + 1}`,
      game_name: `Match ${i + 1}`,
      gamemode: "Conquest",
      max_players: 2,
      map_name: "Forest",
      timestamp: `2026-01-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
      host_username: "ash",
      host_id: 10,
      players: [{ player_id: 10, username: "ash" }],
    }));

    for (const [Component, listUrl] of [
      [ActiveGames, "/games/in_progress"],
      [CompletedGames, "/games/completed"],
      [JoinGame, "/games/open"],
    ] as const) {
      vi.clearAllMocks();
      vi.spyOn(window, "alert").mockImplementation(() => {});
      mockPagedListApis(listUrl, manyGames);

      const { unmount } = render(
        <MemoryRouter>
          <Component />
        </MemoryRouter>
      );

      expect(await screen.findByText("Match 12")).toBeInTheDocument();
      expect(screen.queryByText("Match 1")).not.toBeInTheDocument();

      const nextButtons = screen.getAllByRole("button", { name: ">" });
      await user.click(nextButtons[0]);
      expect(await screen.findByText("Match 1")).toBeInTheDocument();

      const lastButtons = screen.getAllByRole("button", { name: ">>" });
      await user.click(lastButtons[0]);
      expect(screen.getByText("Match 1")).toBeInTheDocument();

      const prevButtons = screen.getAllByRole("button", { name: "<" });
      await user.click(prevButtons[0]);
      expect(await screen.findByText("Match 12")).toBeInTheDocument();

      const firstButtons = screen.getAllByRole("button", { name: "<<" });
      await user.click(firstButtons[0]);
      expect(screen.getByText("Match 12")).toBeInTheDocument();

      await user.click(screen.getAllByRole("button", { name: ">" })[1]);
      expect(await screen.findByText("Match 1")).toBeInTheDocument();
      await user.click(screen.getAllByRole("button", { name: "<" })[1]);
      expect(await screen.findByText("Match 12")).toBeInTheDocument();
      await user.click(screen.getAllByRole("button", { name: ">>" })[1]);
      expect(await screen.findByText("Match 1")).toBeInTheDocument();
      await user.click(screen.getAllByRole("button", { name: "<<" })[1]);
      expect(await screen.findByText("Match 12")).toBeInTheDocument();

      unmount();
    }
  });

  it("keeps pagination on the reload snapshot instead of picking up newer games", async () => {
    const user = userEvent.setup();
    const snapshotGames = Array.from({ length: 12 }, (_, i) => ({
      id: i + 1,
      link: `game-${i + 1}`,
      game_name: `Match ${i + 1}`,
      gamemode: "Conquest",
      max_players: 2,
      map_name: "Forest",
      timestamp: `2026-01-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
      host_username: "ash",
      host_id: 10,
      players: [{ player_id: 10, username: "ash" }],
    }));

    vi.mocked(secureFetch).mockImplementation(async (url) => {
      const raw = String(url);
      if (raw.includes("/games/in_progress")) {
        const parsed = new URL(raw, "http://local.test");
        const page = Number(parsed.searchParams.get("page") || 1);
        const asOf = parsed.searchParams.get("as_of");
        const source = asOf
          ? snapshotGames
          : [
              {
                id: 99,
                link: "game-new",
                game_name: "Brand New",
                gamemode: "Conquest",
                max_players: 2,
                map_name: "Forest",
                timestamp: "2026-02-01T00:00:00Z",
                host_username: "ash",
                host_id: 10,
                players: [{ player_id: 10, username: "ash" }],
              },
              ...snapshotGames,
            ];
        const start = (page - 1) * 10;
        return {
          ok: true,
          json: async () => ({
            items: source.slice(start, start + 10),
            page,
            page_size: 10,
            total: source.length,
            as_of: asOf || "2026-01-15T00:00:00.000Z",
          }),
        } as Response;
      }
      return { ok: true, json: async () => ({ id: 1 }) } as Response;
    });

    render(
      <MemoryRouter>
        <ActiveGames />
      </MemoryRouter>
    );

    expect(await screen.findByText("Brand New")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: ">" })[0]);
    await waitFor(() => {
      expect(screen.getAllByText("Page 2 / 2").length).toBeGreaterThan(0);
    });

    const pageTwoCalls = vi
      .mocked(secureFetch)
      .mock.calls.map(([url]) => String(url))
      .filter((url) => url.includes("page=2"));
    expect(pageTwoCalls.length).toBeGreaterThan(0);
    expect(pageTwoCalls.every((url) => url.includes("as_of="))).toBe(true);
    // Snapshot paging uses the frozen list (no Brand New on later pages).
    expect(screen.queryByText("Brand New")).not.toBeInTheDocument();
  });

  it("handles ActiveGames fetch failures without crashing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(secureFetch).mockRejectedValue(new Error("offline"));
    render(
      <MemoryRouter>
        <ActiveGames />
      </MemoryRouter>
    );
    expect(await screen.findByText(/In-Progress Games/i)).toBeInTheDocument();
  });

  it("handles CompletedGames API failures without crashing", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(secureFetch).mockRejectedValue(new Error("offline"));
    render(
      <MemoryRouter>
        <CompletedGames />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Completed Games/i)).toBeInTheDocument();
  });

  it("alerts when a JoinGame request throws", async () => {
    const user = userEvent.setup();
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(secureFetch).mockImplementation(async (url) => {
      const raw = String(url);
      if (raw.includes("/games/open")) {
        return {
          ok: true,
          json: async () => ({
            items: [sampleGames[1]],
            page: 1,
            page_size: 10,
            total: 1,
            as_of: "2026-01-15T00:00:00.000Z",
          }),
        } as Response;
      }
      if (raw.includes("/api/me")) {
        return { ok: true, json: async () => ({ id: 99 }) } as Response;
      }
      if (raw.includes("/join/")) {
        throw new Error("offline");
      }
      return { ok: true, json: async () => ({}) } as Response;
    });

    render(
      <MemoryRouter>
        <JoinGame />
      </MemoryRouter>
    );

    await user.click(await screen.findByRole("button", { name: "Join" }));
    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith(
        "An error occurred while trying to join the game."
      );
    });
  });
});
