import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import AdminPage from "@/pages/admin/AdminPage";

vi.mock("@/state/auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

import { useAuth } from "@/state/auth";
import { secureFetch } from "@/utils/secureFetch";

function renderAdmin() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>
  );
}

describe("AdminPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows NotFound for non-staff users", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 1,
        trainer_id: 'A1B2C3D4',
        username: "ash",
        email: "a@b.c",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "user",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    renderAdmin();
    expect(await screen.findByText(/404/i)).toBeInTheDocument();
  });

  it("loads moderation queue for staff", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 2,
        trainer_id: 'A1B2C3D4',
        username: "mod",
        email: "m@b.c",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "moderator",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    } as Response);

    renderAdmin();

    expect(await screen.findByRole("heading", { name: /Moderation/i })).toBeInTheDocument();
    expect(screen.getByText(/No pending infractions/i)).toBeInTheDocument();
    expect(secureFetch).toHaveBeenCalledWith("/api/moderation/queue");
  });

  it("shows NotFound when queue returns forbidden", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 3,
        trainer_id: 'A1B2C3D4',
        username: "mod2",
        email: "m2@b.c",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "moderator",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Forbidden" }),
    } as Response);

    renderAdmin();
    await waitFor(() => {
      expect(screen.getByText(/404/i)).toBeInTheDocument();
    });
  });

  it("loads infraction detail and completes a dismiss action", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();

    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4,
        trainer_id: 'A1B2C3D4',
        username: "admin",
        email: "a@b.c",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return {
          ok: true,
          status: 200,
          json: async () => [
            {
              id: 11,
              user_id: 99,
              trainer_id: 'A1B2C3D4',
              username: "offender",
              game_id: 1,
              game_link: "abc",
              censored_message: "bad ***",
              severity: "medium",
              status: "pending",
              created_at: "2026-01-01T00:00:00Z",
              matched_term_count: 1,
            },
          ],
        } as Response;
      }
      if (url === "/api/admin/staff") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/admin/audit-log") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/moderation/infractions/11") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 11,
            user_id: 99,
            trainer_id: 'A1B2C3D4',
            username: "offender",
            game_id: 1,
            game_link: "abc",
            censored_message: "bad ***",
            original_message: "bad word",
            matched_terms: ["word"],
            moderator_notes: null,
            severity: "medium",
            status: "pending",
            created_at: "2026-01-01T00:00:00Z",
            matched_term_count: 1,
          }),
        } as Response;
      }
      if (url === "/api/moderation/users/99/history") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 99,
            trainer_id: 'A1B2C3D4',
            username: "offender",
            role: "user",
            is_banned: false,
            ban_expires_at: null,
            pending_infractions: 1,
            total_infractions: 2,
            is_muted: false,
          }),
        } as Response;
      }
      if (url.includes("/dismiss") && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      return { ok: false, status: 500, json: async () => ({ detail: "fail" }) } as Response;
    });

    renderAdmin();
    expect(await screen.findByText("offender")).toBeInTheDocument();
    await user.click(screen.getByText("offender"));
    expect(await screen.findByText("bad word")).toBeInTheDocument();
    expect(screen.getByText(/History: 2 total/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Dismiss/i }));
    await waitFor(() => {
      expect(screen.getByText(/Action completed/i)).toBeInTheDocument();
    });
  });
});
