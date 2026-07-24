import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import MapBuilderPage from "@/pages/map-builder/MapBuilderPage";

vi.mock("@/state/auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

vi.mock("@/pages/map-builder/MapBuilderCanvas", () => ({
  default: () => <div data-testid="map-builder-canvas" />,
}));

vi.mock("@/pages/map-builder/TilePalette", () => ({
  default: () => <div data-testid="tile-palette" />,
}));

import { useAuth } from "@/state/auth";
import { secureFetch } from "@/utils/secureFetch";

describe("MapBuilderPage access", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ tilesets: ["Brick City.png"], items: [] }),
    } as Response);
  });

  it("shows NotFound for non-staff users", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 1,
        username: "ash",
        email: "a@b.c",
        avatar: "",
        elo: 1000,
        currency: 0,
        role: "user",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter>
        <MapBuilderPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/404/i)).toBeInTheDocument();
  });

  it("renders builder chrome for staff", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 2,
        username: "mod",
        email: "m@b.c",
        avatar: "",
        elo: 1000,
        currency: 0,
        role: "moderator",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    // Map builder may fetch multiple URLs — keep responses permissive.
    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("manifest")) {
        return {
          ok: true,
          json: async () => ({ tilesets: ["Brick City.png"] }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => [],
      } as Response;
    });

    render(
      <MemoryRouter>
        <MapBuilderPage />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: /Map Builder/i })).toBeInTheDocument();
    expect(screen.getByTestId("map-builder-canvas")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("tile-palette")).toBeInTheDocument();
    });
  });
});
