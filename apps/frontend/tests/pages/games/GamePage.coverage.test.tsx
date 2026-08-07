import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect } from "react";

const mockNavigate = vi.fn();
const wsInstances: any[] = [];

class MockWebSocket {
  static OPEN = 1;
  readyState = 1;
  onopen: ((ev?: any) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev?: any) => void) | null = null;
  onerror: ((ev?: any) => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor(_url: string) {
    wsInstances.push(this);
    queueMicrotask(() => this.onopen?.({}));
  }
}

vi.stubGlobal("WebSocket", MockWebSocket);

vi.mock("@/state/auth", () => ({
  useAuth: () => ({ user: { id: 1, username: "testuser" } }),
}));

vi.mock("@/utils/bugReport", () => ({
  openBugReportWindow: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

vi.mock("@/pages/games/components/GameMapStage", () => ({
  default: (props: any) => {
    useEffect(() => {
      const rect = {
        left: 0,
        top: 0,
        width: 64,
        height: 64,
        right: 64,
        bottom: 64,
        x: 0,
        y: 0,
        toJSON() {},
      };
      if (props.overlayRef) {
        const canvas = document.createElement("canvas");
        canvas.id = "overlayCanvas";
        canvas.width = 64;
        canvas.height = 64;
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.overlayRef.current = canvas;
      }
      if (props.overlay2Ref) {
        const canvas = document.createElement("canvas");
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.overlay2Ref.current = canvas;
      }
      if (props.overlay3Ref) {
        const canvas = document.createElement("canvas");
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.overlay3Ref.current = canvas;
      }
      if (props.canvasRef) {
        const canvas = document.createElement("canvas");
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.canvasRef.current = canvas;
      }
      if (props.itemsCanvasRef) {
        const canvas = document.createElement("canvas");
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.itemsCanvasRef.current = canvas;
      }
      if (props.objectivesCanvasRef) {
        const canvas = document.createElement("canvas");
        canvas.getBoundingClientRect = () => rect as DOMRect;
        props.objectivesCanvasRef.current = canvas;
      }
      if (props.mapStageRef) {
        const div = document.createElement("div");
        div.getBoundingClientRect = () =>
          ({
            left: 0,
            top: 80,
            width: 200,
            height: 200,
            right: 200,
            bottom: 280,
            x: 0,
            y: 80,
            toJSON() {},
          }) as DOMRect;
        props.mapStageRef.current = div;
      }
    }, [
      props.overlayRef,
      props.overlay2Ref,
      props.overlay3Ref,
      props.canvasRef,
      props.itemsCanvasRef,
      props.objectivesCanvasRef,
      props.mapStageRef,
    ]);

    return (
      <div data-testid="map-stage" data-unit-count={String(props.placedUnits?.length ?? 0)}>
        <button
          type="button"
          data-unit
          onClick={() => {
            const unit = props.placedUnits?.[0];
            if (unit) props.onUnitClick?.(unit);
          }}
        >
          Click unit
        </button>
        <button
          type="button"
          data-unit
          onClick={() => {
            const unit = props.placedUnits?.[1] ?? props.placedUnits?.[0];
            if (unit) props.onUnitClick?.(unit);
          }}
        >
          Click second unit
        </button>
        <button
          type="button"
          data-unit
          onClick={() => {
            const unit = props.placedUnits?.[0];
            if (unit) props.onUnitMouseEnter?.(unit);
          }}
        >
          Hover unit
        </button>
        <button
          type="button"
          data-unit
          onClick={() => props.onUnitMouseLeave?.()}
        >
          Leave unit
        </button>
        <button
          type="button"
          onClick={() => props.onMapItemHover?.(3, 10, 10)}
        >
          Hover map item
        </button>
        <button type="button" onClick={() => props.onMapItemLeave?.()}>
          Leave map item
        </button>
        <button
          type="button"
          data-unit-info
          onClick={() => {
            const canvas = props.overlayRef?.current;
            if (!canvas) return;
            // tile (1,0) on 2x2 map — dispatch on overlay canvas (has #overlayCanvas id)
            canvas.dispatchEvent(
              new MouseEvent("click", { bubbles: true, clientX: 48, clientY: 16 })
            );
          }}
        >
          Click overlay tile
        </button>
        <button
          type="button"
          data-unit-info
          onClick={() => {
            const canvas = props.overlayRef?.current;
            if (!canvas) return;
            canvas.dispatchEvent(
              new MouseEvent("mousemove", { bubbles: true, clientX: 48, clientY: 16 })
            );
            canvas.dispatchEvent(new MouseEvent("mouseleave", { bubbles: true }));
          }}
        >
          Move overlay pointer
        </button>
      </div>
    );
  },
}));

vi.mock("@/pages/games/components/ChatPanel", () => ({
  default: (props: any) => (
    <div data-testid="chat-panel">
      <input
        aria-label="chat-input"
        value={props.chatInput}
        onChange={(e) => props.onChatInputChange(e.target.value)}
      />
      <button type="button" onClick={() => props.onSendChat()}>
        Send chat
      </button>
      {props.canInvitePlayers && (
        <button type="button" onClick={() => props.onInvitePlayers?.()}>
          Invite players
        </button>
      )}
      <div>{props.chatEntries?.map((e: any) => e.text).join(" | ")}</div>
    </div>
  ),
}));

vi.mock("@/pages/games/components/unit-menus/PreparationUnitSelectMenu", () => ({
  default: (props: any) => (
    <button
      type="button"
      onClick={() =>
        props.onSelectUnit({
          id: 25,
          name: "Pikachu",
          cost: 100,
          asset_folder: "025_pikachu",
          types: ["Electric"],
        })
      }
    >
      Place unit
    </button>
  ),
}));

vi.mock("@/pages/games/components/unit-menus/PreparationPlacedUnitMenu", () => ({
  default: (props: any) => (
    <div data-testid="prep-placed-menu" data-unit-info>
      <button type="button" onClick={() => props.onRemoveUnit()}>
        Remove unit
      </button>
      <button type="button" onClick={() => props.onChangeAbility(7)}>
        Change ability
      </button>
      <button type="button" onClick={() => props.onChangeItem(3)}>
        Change item
      </button>
      <button type="button" onClick={() => props.onRemoveItem()}>
        Remove item
      </button>
      <button type="button" onClick={() => props.onMoveHoverStart({ id: 1, name: "Thunderbolt", range_type: "adjacent" })}>
        Prep hover move
      </button>
      <button type="button" onClick={() => props.onMoveHoverEnd()}>
        Prep leave move
      </button>
    </div>
  ),
}));

vi.mock("@/pages/games/components/unit-menus/InProgressUnitMenu", () => ({
  default: (props: any) => {
    props.getStatColor?.(props.activeUnit, "attack");
    return (
    <div data-testid="in-progress-menu" data-unit-info>
      <button
        type="button"
        onClick={() =>
          props.onMoveHoverStart({
            id: 1,
            name: "Thunderbolt",
            range_type: "adjacent",
            pp: 10,
            type: "Electric",
            power: 90,
          })
        }
      >
        Hover move
      </button>
      <button type="button" onClick={() => props.onMoveHoverEnd?.()}>
        Leave move
      </button>
      <button
        type="button"
        onClick={() =>
          props.onMoveSelect({
            id: 1,
            name: "Thunderbolt",
            range_type: "adjacent",
            pp: 10,
            type: "Electric",
            power: 90,
          })
        }
      >
        Select move
      </button>
      <button
        type="button"
        onClick={() =>
          props.onMoveSelect({
            id: 99,
            name: "Recover",
            range_type: "self",
            pp: 5,
            type: "Normal",
            power: 0,
          })
        }
      >
        Select self move
      </button>
      <button
        type="button"
        onClick={() =>
          props.onMoveSelect({
            id: 2,
            name: "Volt Tackle",
            range_type: "dash_attack",
            pp: 5,
            type: "Electric",
            power: 120,
          })
        }
      >
        Select dash move
      </button>
      <button type="button" onClick={() => props.onExecuteMove()}>
        Execute move
      </button>
      <button type="button" onClick={() => props.onCancelMove()}>
        Cancel move
      </button>
      <button type="button" onClick={() => props.onWait()}>
        Wait
      </button>
      {props.showPickUpButton && (
        <button type="button" onClick={() => props.onPickUpItem?.()}>
          Pick Up
        </button>
      )}
      {props.showCaptureButton && (
        <button type="button" onClick={() => props.onCapture?.()}>
          Capture
        </button>
      )}
    </div>
    );
  },
}));

vi.mock("@/pages/games/modes/ConquestGame", () => ({
  default: (props: any) => (
    <button type="button" onClick={() => props.onTileSelect?.([0, 0])}>
      Select spawn tile
    </button>
  ),
}));

vi.mock("@/pages/games/modes/WarGame", async () => {
  const actual = await vi.importActual<typeof import("@/pages/games/modes/WarGame")>(
    "@/pages/games/modes/WarGame"
  );
  return {
    ...actual,
    default: (props: any) => (
      <div>
        <p>War Mode: stub</p>
        <button type="button" onClick={() => props.onObjectiveSelect?.([0, 0])}>
          Select objective
        </button>
      </div>
    ),
  };
});

vi.mock("@/pages/games/modes/CaptureTheFlagGame", () => ({
  default: () => <p>Capture The Flag mode</p>,
}));

import { secureFetch } from "@/utils/secureFetch";
import GamePage from "@/pages/games/GamePage";

const miniMap = {
  width: 2,
  height: 2,
  tileset_names: ["a.png"],
  tile_data: {
    base: [
      [
        [0, 0],
        [0, 0],
      ],
      [
        [0, 0],
        [0, 0],
      ],
    ],
    overlay: [
      [null, null],
      [null, null],
    ],
    movement_cost: [
      [1, 1],
      [1, 1],
    ],
    spawn_points: [
      [1, null],
      [null, 2],
    ],
    special_tiles: [
      [null, null],
      [null, null],
    ],
    item_id_tiles: [
      [null, null],
      [null, null],
    ],
  },
};

const sampleUnit = {
  id: 11,
  game_id: 1,
  unit_id: 25,
  user_id: 1,
  unit: {
    id: 25,
    name: "Pikachu",
    asset_folder: "025_pikachu",
    types: ["Electric"],
    cost: 100,
    base_stats: { hp: 35, attack: 55, defense: 40, special_attack: 50, special_defense: 50, speed: 90 },
  },
  current_x: 0,
  current_y: 0,
  starting_x: 0,
  starting_y: 0,
  level: 50,
  current_hp: 30,
  current_stats: { hp: 35, attack: 55, speed: 90, movement: 4 },
  is_fainted: false,
  can_move: true,
  equipped_move_ids: [1],
  move_pp: [10],
  held_item: null,
  held_item_slug: null,
  ability: "Static",
  ability_id: 7,
};

const enemyUnit = {
  ...sampleUnit,
  id: 22,
  user_id: 2,
  current_x: 1,
  current_y: 1,
  starting_x: 1,
  starting_y: 1,
  unit: { ...sampleUnit.unit, name: "Eevee", asset_folder: "133_eevee", types: ["Normal"] },
};

function baseGame(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    link: "cq-link",
    game_name: "Coverage Match",
    gamemode: "Conquest",
    status: "preparation",
    map_name: "Arena",
    map: miniMap,
    map_state: {},
    max_players: 2,
    unit_limit: 6,
    starting_cash: 3000,
    host_id: 1,
    players: [
      { id: 1, player_id: 1, username: "testuser", is_ready: false, cash_remaining: 3000, unit_count: 0 },
      { id: 2, player_id: 2, username: "rival", is_ready: false, cash_remaining: 3000, unit_count: 0 },
    ],
    player_order: [1, 2],
    current_turn: null,
    max_turns: 50,
    start_with_tms: false,
    replay_log: [],
    ...overrides,
  };
}

type Fixture = {
  game?: any;
  units?: any[];
  player?: any;
  posts?: Record<string, any>;
};

function installFetch(fixture: Fixture = {}) {
  const game = fixture.game ?? baseGame();
  const units = fixture.units ?? [];
  const player = fixture.player ?? { cash_remaining: 3000, is_ready: false, game_units: units.map((u) => u.id) };
  const posts = fixture.posts ?? {};

  vi.mocked(secureFetch).mockImplementation(async (input: any, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();

    if (method === "POST" || method === "DELETE" || method === "PUT" || method === "PATCH") {
      for (const [key, body] of Object.entries(posts)) {
        if (url.includes(key)) {
          if (body?.ok === false) {
            return {
              ok: false,
              status: 400,
              json: async () => body.json ?? { detail: "fail" },
            } as Response;
          }
          let payload = body ?? {};
          if (typeof body === "function") {
            payload = body(method, url);
          } else if (method === "DELETE" && key.includes("item")) {
            payload = {
              cash_remaining: 2900,
              unit: { ...sampleUnit, held_item: null, held_item_slug: null },
            };
          }
          return {
            ok: true,
            status: 200,
            json: async () => payload,
          } as Response;
        }
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    }

    if (url.includes("/api/me")) {
      return { ok: true, json: async () => ({ id: 1 }) } as Response;
    }
    if (url.includes("/turnlock")) {
      return {
        ok: true,
        json: async () => ({
          "11": { origin: [0, 0], tiles: [[0, 0], [0, 1], [1, 0]] },
          "22": { origin: [1, 1], tiles: [[1, 1], [1, 0], [0, 1]] },
        }),
      } as Response;
    }
    if (url.includes("/moves/all")) {
      return {
        ok: true,
        json: async () => [
          { id: 1, name: "Thunderbolt", range_type: "adjacent", pp: 10, type: "Electric", power: 90 },
          { id: 2, name: "Volt Tackle", range_type: "dash_attack", pp: 5, type: "Electric", power: 120 },
          { id: 99, name: "Recover", range_type: "self", pp: 5, type: "Normal", power: 0 },
        ],
      } as Response;
    }
    if (url.includes("/units/summary") || url.includes("/units/all")) {
      return {
        ok: true,
        json: async () => [
          {
            id: 25,
            name: "Pikachu",
            cost: 100,
            asset_folder: "025_pikachu",
            types: ["Electric"],
            species_id: 25,
            form_id: 1,
          },
        ],
      } as Response;
    }
    if (url.includes("/abilities/all")) {
      return { ok: true, json: async () => [{ id: 7, name: "Static" }] } as Response;
    }
    if (url.includes("/items/all")) {
      return {
        ok: true,
        json: async () => [
          { id: 3, name: "Oran Berry", slug: "oran-berry", category: "berry", cost: 50 },
          { id: 9, name: "TM01", slug: "tm01", category: "tm", cost: 100, move_id: 1 },
          { id: 10, name: "TM99", slug: "tm99", category: "tm", cost: 100, move_id: 404 },
        ],
      } as Response;
    }
    if (url.includes("/units") && url.includes("/games/")) {
      return { ok: true, json: async () => units } as Response;
    }
    if (url.includes("/player")) {
      return { ok: true, json: async () => player } as Response;
    }
    if (url.includes("/games/")) {
      return { ok: true, json: async () => game } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}

function renderGame(path = "/games/cq-link") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/games/:gameId" element={<GamePage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("GamePage coverage suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Keep a safe default so in-flight GamePage effects never see undefined.
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);
    wsInstances.length = 0;
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.mocked(secureFetch).mockReset();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);
  });

  it("prep: ready, place, remove, and start", async () => {
    const user = userEvent.setup();
    const game = baseGame({
      players: [
        { id: 1, player_id: 1, username: "testuser", is_ready: false },
        { id: 2, player_id: 2, username: "rival", is_ready: true },
      ],
    });
    installFetch({
      game,
      posts: {
        "/player/ready": { ready: true, cash_remaining: 2900, game_units: [11] },
        "/units/place": sampleUnit,
        "/units/remove": {},
        "/ability": {
          cash_remaining: 2900,
          unit: { ...sampleUnit, ability: "Static", ability_id: 7 },
        },
        "/item": {
          cash_remaining: 2850,
          unit: {
            ...sampleUnit,
            held_item: "Oran Berry",
            held_item_slug: "oran-berry",
          },
        },
        "/start": {},
      },
    });

    renderGame();
    expect(await screen.findByText("Coverage Match")).toBeInTheDocument();
    expect(screen.getByText(/Preparation phase/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Select spawn tile/i }));
    expect(await screen.findByRole("button", { name: /Place unit/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Place unit/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/units/place"),
        expect.objectContaining({ method: "POST" })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "1");
    });

    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("prep-placed-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Prep hover move/i }));
    await user.click(screen.getByRole("button", { name: /Prep leave move/i }));
    await user.click(screen.getByRole("button", { name: /Change ability/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/ability"),
        expect.objectContaining({ method: "POST" })
      );
    });
    expect(await screen.findByTestId("prep-placed-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Change item/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/item"),
        expect.objectContaining({ method: "POST" })
      );
    });
    expect(await screen.findByTestId("prep-placed-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Remove item/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/item"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
    expect(await screen.findByTestId("prep-placed-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Remove unit/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/units/remove"),
        expect.objectContaining({ method: "DELETE" })
      );
    });

    await user.click(screen.getByRole("button", { name: /Select spawn tile/i }));
    await user.click(await screen.findByRole("button", { name: /Place unit/i }));
    await waitFor(() => {
      expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "1");
    });
    await user.click(screen.getByRole("button", { name: /Ready/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/player/ready"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("shows completed win and draw status copy", async () => {
    installFetch({
      game: baseGame({
        status: "completed",
        winner_id: 1,
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
      }),
    });
    const { unmount } = renderGame();
    expect(await screen.findByText(/testuser wins the match!/i)).toBeInTheDocument();
    unmount();

    installFetch({
      game: baseGame({
        status: "completed",
        draw_player_ids: [1, 2],
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
      }),
    });
    renderGame();
    expect(await screen.findByText(/Draw between testuser, rival/i)).toBeInTheDocument();
  });

  it("completed match shows generic copy without winner or draw ids", async () => {
    installFetch({
      game: baseGame({
        status: "completed",
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
      }),
    });
    renderGame();
    expect(await screen.findByText(/Match completed/i)).toBeInTheDocument();
  });

  it("open lobby and CTF mode", async () => {
    const user = userEvent.setup();
    installFetch({ game: baseGame({ status: "open", players: [{ id: 1, player_id: 1, username: "testuser" }] }) });
    const openView = renderGame();
    expect(await screen.findByText(/Waiting for players/i)).toBeInTheDocument();
    openView.unmount();

    installFetch({
      game: baseGame({
        status: "closed",
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
      }),
      posts: { "/start": {} },
    });
    const closedView = renderGame();
    expect(await screen.findByText(/Players have been found/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Start Game/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/start"),
        expect.objectContaining({ method: "POST" })
      );
    });
    closedView.unmount();

    installFetch({
      game: baseGame({
        link: "ctf-link",
        gamemode: "Capture The Flag",
        status: "in_progress",
        current_turn: 0,
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
      }),
      units: [sampleUnit],
      player: { cash_remaining: 100, is_ready: true, game_units: [11] },
    });
    renderGame("/games/ctf-link");
    expect(await screen.findByText(/Capture The Flag mode/i)).toBeInTheDocument();
  });

  it("in-progress: end turn, wait, hover/select/execute move", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 120000).toISOString(),
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
        map_state: {
          item_id_tiles: [
            [3, null],
            [null, null],
          ],
          weather_tiles: [
            [1, 0],
            [0, 2],
          ],
          hazard_tiles: [
            [[1], null],
            [null, [1]],
          ],
        },
      }),
      units: [sampleUnit, enemyUnit],
      player: { cash_remaining: 200, is_ready: true, game_units: [11] },
      posts: {
        "/end_turn": {},
        "/wait": { id: 11, can_move: false },
        "/execute_move": {
          targets: [{ id: 22, current_hp: 10 }],
          removed_ids: [],
          move_pp: [9],
        },
        "/move": { x: 1, y: 0, movement_locked: false },
        "/pick_up_item": {
          id: 11,
          held_item: "Oran Berry",
          held_item_slug: "oran-berry",
          x: 0,
          y: 0,
          move_pp: [10],
        },
      },
    });

    renderGame();
    expect(await screen.findByText(/testuser's Turn/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "2");
    });

    await user.click(screen.getByRole("button", { name: /Hover map item/i }));
    await user.click(screen.getByRole("button", { name: /Leave map item/i }));

    await user.click(screen.getByRole("button", { name: /End Turn/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/end_turn"),
        expect.objectContaining({ method: "POST" })
      );
    });

    await user.click(screen.getByRole("button", { name: /Hover unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Leave unit/i }));

    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(screen.getByTestId("in-progress-menu")).toBeInTheDocument();

    // move unit via overlay
    await user.click(screen.getByRole("button", { name: /Click overlay tile/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/move"),
        expect.objectContaining({ method: "POST" })
      );
    });

    // ensure menu still open after movement
    if (!screen.queryByTestId("in-progress-menu")) {
      await user.click(screen.getByRole("button", { name: /Click unit/i }));
    }
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Hover move/i }));
    await user.click(screen.getByRole("button", { name: /Leave move/i }));
    await user.click(screen.getByRole("button", { name: /Select move/i }));
    await user.click(screen.getByRole("button", { name: /Move overlay pointer/i }));
    await user.click(screen.getByRole("button", { name: /Click overlay tile/i }));
    await user.click(screen.getByRole("button", { name: /Execute move/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/execute_move"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("in-progress: self move, wait, pick up, and unlock", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
        map_state: {
          item_id_tiles: [
            [3, null],
            [null, null],
          ],
        },
      }),
      units: [sampleUnit],
      player: { cash_remaining: 200, is_ready: true, game_units: [11] },
      posts: {
        "/wait": { id: 11, can_move: false },
        "/execute_move": { targets: [], removed_ids: [], move_pp: [4] },
        "/pick_up_item": {
          held_item: "Oran Berry",
          held_item_slug: "oran-berry",
          x: 0,
          y: 0,
          move_pp: [10],
        },
      },
    });

    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await waitFor(() => expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "1"));

    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();

    // pick up item on tile
    expect(screen.getByRole("button", { name: /Pick Up/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Pick Up/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/pick_up_item"),
        expect.objectContaining({ method: "POST" })
      );
    });

    // unlock by clicking same unit again (after pick-up can_move false may block wait)
    // re-click to clear selection
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
  });

  it("in-progress: wait and self-target execute", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [{ ...sampleUnit, equipped_move_ids: [1, 99], move_pp: [10, 5] }],
      player: { cash_remaining: 200, is_ready: true, game_units: [11] },
      posts: {
        "/wait": { id: 11, can_move: false },
        "/execute_move": { targets: [], removed_ids: [22], move_pp: [10, 4] },
      },
    });

    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Select self move/i }));
    await user.click(screen.getByRole("button", { name: /Execute move/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/execute_move"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("handles websocket chat, map, unit, and lifecycle events", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        replay_log: [
          { kind: "system", message: "Match begin" },
          { kind: "chat", message: "gl", username: "rival", player_id: 2 },
        ],
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
        map_state: {
          item_id_tiles: [
            [3, null],
            [null, null],
          ],
          objective_tiles: [[{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20 }, null]],
        },
      }),
      units: [sampleUnit],
      player: { cash_remaining: 200, is_ready: true, game_units: [11] },
    });

    renderGame();
    await screen.findByText("Coverage Match");
    await waitFor(() => expect(wsInstances.length).toBeGreaterThan(0));
    const ws = wsInstances[wsInstances.length - 1];

    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();

    await act(async () => {
      ws.onmessage?.({
        data: JSON.stringify({
          event: "chat_message",
          message: "hello there",
          username: "rival",
          player_id: 2,
        }),
      });
      ws.onmessage?.({
        data: JSON.stringify({ event: "system_log", message: "Turn 2" }),
      });
      ws.onmessage?.({ data: "map_item_picked:0:0" });
      ws.onmessage?.({ data: "map_item_swapped:1:1:5" });
      ws.onmessage?.({ data: "objective_updated:0:0:10:2:pokeball" });
      ws.onmessage?.({ data: "unit_moved:11:ignored:1:0" });
      ws.onmessage?.({ data: "unit_pp_updated:11" });
      ws.onmessage?.({ data: "unit_stats_updated:11" });
      ws.onmessage?.({ data: "unit_item_updated:11" });
      ws.onmessage?.({ data: "unit_removed:22" });
      ws.onmessage?.({ data: "turn_advanced" });
      ws.onmessage?.({ data: "player_joined" });
      ws.onmessage?.({ data: "game_completed" });
      ws.onmessage?.({ data: "{not-json" });
    });

    await waitFor(() => {
      expect(screen.getByTestId("chat-panel")).toHaveTextContent(/hello there|Turn 2|Match begin|gl/);
    });
  });

  it("sends chat messages", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({ status: "in_progress", current_turn: 0 }),
      units: [sampleUnit],
      posts: { "/chat": {} },
    });
    renderGame();
    await screen.findByText("Coverage Match");

    await user.type(screen.getByLabelText("chat-input"), "glhf");
    await user.click(screen.getByRole("button", { name: /Send chat/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/chat"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("war in_progress objective select, summon, and capture", async () => {
    const user = userEvent.setup();
    const warUnit = { ...sampleUnit, current_x: 0, current_y: 0 };
    installFetch({
      game: baseGame({
        link: "war-link",
        gamemode: "War",
        status: "in_progress",
        current_turn: 0,
        cash_per_turn: 100,
        unit_limit: 6,
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
        map_state: {
          objective_tiles: [
            [{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20, last_summon_round: null }, { kind: "pokeball", owner: 2, hp: 20, max_hp: 20 }],
            [null, null],
          ],
        },
      }),
      units: [],
      player: { cash_remaining: 500, is_ready: true, game_units: [] },
      posts: { "/units/place": warUnit },
    });

    const { unmount } = renderGame("/games/war-link");
    expect(await screen.findByText(/War Mode/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Select objective/i }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Place unit/i })).toBeTruthy();
    });
    await user.click(screen.getByRole("button", { name: /Place unit/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/units/place"),
        expect.objectContaining({ method: "POST" })
      );
    });
    unmount();

    // Capture enemy objective under unit
    installFetch({
      game: baseGame({
        link: "war-cap",
        gamemode: "War",
        status: "in_progress",
        current_turn: 0,
        players: [
          { id: 1, player_id: 1, username: "testuser" },
          { id: 2, player_id: 2, username: "rival" },
        ],
        map_state: {
          objective_tiles: [
            [{ kind: "pokeball", owner: 2, hp: 20, max_hp: 20 }, null],
            [null, null],
          ],
        },
      }),
      units: [warUnit],
      player: { cash_remaining: 500, is_ready: true, game_units: [11] },
      posts: {
        "/war/capture": { objective: { hp: 15, owner: 1, kind: "pokeball" } },
      },
    });
    renderGame("/games/war-cap");
    await screen.findByText(/War Mode/i);
    await waitFor(() => expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "1"));
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Capture/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Capture/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/war/capture"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("handles API error toasts for ready, end turn, and chat", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "preparation",
        players: [
          { id: 1, player_id: 1, username: "testuser", is_ready: false },
          { id: 2, player_id: 2, username: "rival", is_ready: false },
        ],
      }),
      units: [sampleUnit],
      player: { cash_remaining: 3000, is_ready: false, game_units: [11] },
      posts: {
        "/player/ready": { ok: false, json: { detail: "nope" } },
      },
    });
    const { unmount } = renderGame();
    await screen.findByText(/Preparation phase/i);
    await waitFor(() => expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "1"));
    await user.click(screen.getByRole("button", { name: /Ready/i }));
    await waitFor(() => {
      expect(screen.getByText(/Unable to toggle readiness/i)).toBeInTheDocument();
    });
    unmount();

    installFetch({
      game: baseGame({ status: "in_progress", current_turn: 0 }),
      units: [sampleUnit],
      posts: {
        "/end_turn": { ok: false, json: { detail: "busy" } },
        "/chat": { ok: false, json: { detail: "muted" } },
      },
    });
    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /End Turn/i }));
    await waitFor(() => {
      expect(screen.getByText(/Unable to end turn/i)).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText("chat-input"), "hi");
    await user.click(screen.getByRole("button", { name: /Send chat/i }));
    await waitFor(() => {
      expect(screen.getByText(/Unable to send chat message/i)).toBeInTheDocument();
    });
  });

  it("cancels move targeting and waits successfully", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [sampleUnit],
      posts: { "/wait": { id: 11, can_move: false, removed_ids: [] } },
    });
    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Select move/i }));
    await user.click(screen.getByRole("button", { name: /Cancel move/i }));
    await user.click(screen.getByRole("button", { name: /Wait/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/wait"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("clicks enemy unit and rejects off-range overlay click", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [sampleUnit, enemyUnit],
      posts: { "/move": { ok: false, json: { detail: "blocked" } } },
    });
    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await waitFor(() => expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "2"));
    await user.click(screen.getByRole("button", { name: /Click second unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    // switch to own unit then try move that fails
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    await user.click(screen.getByRole("button", { name: /Click overlay tile/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/move"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("war preparation phase copy", async () => {
    installFetch({
      game: baseGame({
        link: "war-prep",
        gamemode: "War",
        status: "preparation",
        map_state: {
          objective_tiles: [
            [{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20, last_summon_round: null }, null],
            [null, null],
          ],
        },
      }),
    });
    renderGame("/games/war-prep");
    expect(await screen.findByText(/place units on your objectives/i)).toBeInTheDocument();
  });

  it("non-host all-ready waiting copy", async () => {
    installFetch({
      game: baseGame({
        host_id: 2,
        status: "preparation",
        players: [
          { id: 1, player_id: 1, username: "testuser", is_ready: true },
          { id: 2, player_id: 2, username: "rival", is_ready: true },
        ],
      }),
      player: { cash_remaining: 2900, is_ready: true, game_units: [11] },
      units: [sampleUnit],
    });
    renderGame();
    expect(
      await screen.findByText(/Waiting for the host to start the game/i)
    ).toBeInTheDocument();
  });

    it("all-ready preparation shows host start copy", async () => {
    installFetch({
      game: baseGame({
        status: "preparation",
        players: [
          { id: 1, player_id: 1, username: "testuser", is_ready: true },
          { id: 2, player_id: 2, username: "rival", is_ready: true },
        ],
      }),
      units: [sampleUnit],
      player: { cash_remaining: 2900, is_ready: true, game_units: [11] },
      posts: { "/start": {} },
    });
    const user = userEvent.setup();
    renderGame();
    expect(
      await screen.findByText(/All players are ready. Start the game when you're ready!/i)
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Start Game/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/start"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  it("computes client movement when turnlock is empty and locks after move", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
        map: {
          ...miniMap,
          tile_data: {
            ...miniMap.tile_data,
            special_tiles: [
              ["water", null],
              [null, null],
            ],
          },
        },
      }),
      units: [sampleUnit, enemyUnit],
      posts: {
        "/move": { x: 1, y: 0, movement_locked: true },
      },
    });
    const previous = vi.mocked(secureFetch).getMockImplementation()!;
    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      if (String(input).includes("/turnlock")) {
        return { ok: true, json: async () => ({}) } as Response;
      }
      return previous(input, init);
    });

    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await waitFor(() => expect(screen.getByTestId("map-stage")).toHaveAttribute("data-unit-count", "2"));
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Click overlay tile/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringContaining("/move"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("recalculates turn timer on visibility change and opens invite modal", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "open",
        start_with_tms: true,
        turn_deadline: new Date(Date.now() + 45000).toISOString(),
      }),
      posts: {
        "/api/invitations": { ok: true },
      },
    });
    const previous = vi.mocked(secureFetch).getMockImplementation()!;
    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/players/search")) {
        return {
          ok: true,
          json: async () => [{ id: 9, username: "misty", trainer_id: "T1" }],
        } as Response;
      }
      if (url.includes("/api/invitations") && (init?.method ?? "GET").toUpperCase() === "POST") {
        return { ok: true, json: async () => ({ ok: true }) } as Response;
      }
      return previous(input, init);
    });

    renderGame();
    expect(await screen.findByRole("button", { name: /Invite players/i })).toBeInTheDocument();

    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));

    await user.click(screen.getByRole("button", { name: /Invite players/i }));
    expect(await screen.findByRole("dialog", { name: /invite player/i })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/username or trainer id/i), "mis");
    await waitFor(
      () => {
        expect(secureFetch).toHaveBeenCalledWith(expect.stringContaining("/api/players/search"));
      },
      { timeout: 2000 },
    );
    expect(await screen.findByText("misty")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^invite$/i }));
    await waitFor(() => {
      expect(screen.getByText(/Invitation sent to misty/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /close/i }));
  });

  it("validates displacement dash moves against landing tiles", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
        map: {
          ...miniMap,
          width: 4,
          height: 4,
          tile_data: {
            ...miniMap.tile_data,
            base: Array.from({ length: 4 }, () =>
              Array.from({ length: 4 }, () => [0, 0] as [number, number]),
            ),
            overlay: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => null)),
            movement_cost: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => 1)),
            spawn_points: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => null)),
            special_tiles: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => null)),
            item_id_tiles: Array.from({ length: 4 }, () => Array.from({ length: 4 }, () => null)),
          },
        },
      }),
      units: [
        { ...sampleUnit, equipped_move_ids: [1, 2], move_pp: [10, 5] },
        { ...enemyUnit, current_x: 3, current_y: 3, starting_x: 3, starting_y: 3 },
      ],
      posts: {
        "/execute_move": { ok: false, json: { detail: "This cannot work." } },
      },
    });
    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    expect(await screen.findByTestId("in-progress-menu")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Select dash move/i }));
    // Execute without a target first (validation path).
    await user.click(screen.getByRole("button", { name: /Execute move/i }));
    await waitFor(() => {
      expect(screen.getByText(/Select a target tile/i)).toBeInTheDocument();
    });
  });

  it("selects conquest spawn tiles in preparation", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({ status: "preparation" }),
    });
    renderGame();
    await screen.findByRole("button", { name: /Select spawn tile/i });
    await user.click(screen.getByRole("button", { name: /Select spawn tile/i }));
  });

  it("rejects wait off-turn", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 1,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [sampleUnit, enemyUnit],
    });
    renderGame();
    await screen.findByText(/rival's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    await user.click(screen.getByRole("button", { name: /Wait/i }));
    expect(await screen.findByText(/only wait on your turn/i)).toBeInTheDocument();
  });

  it("rejects wait for locked and enemy units", async () => {
    const user = userEvent.setup();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [{ ...sampleUnit, can_move: false }, enemyUnit],
    });
    const { unmount } = renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click unit/i }));
    await user.click(screen.getByRole("button", { name: /Wait/i }));
    expect(await screen.findByText(/locked and cannot act/i)).toBeInTheDocument();

    unmount();
    installFetch({
      game: baseGame({
        status: "in_progress",
        current_turn: 0,
        turn_deadline: new Date(Date.now() + 60000).toISOString(),
      }),
      units: [sampleUnit, enemyUnit],
    });
    renderGame();
    await screen.findByText(/testuser's Turn/i);
    await user.click(screen.getByRole("button", { name: /Click second unit/i }));
    await user.click(screen.getByRole("button", { name: /Wait/i }));
    expect(await screen.findByText(/only wait with your own unit/i)).toBeInTheDocument();
  });
});
