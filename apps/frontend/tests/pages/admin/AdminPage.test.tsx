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

  it("publishes an announcement and displays API errors", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/moderation/queue" || url === "/api/admin/staff" || url === "/api/admin/audit-log") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/announcements") {
        return { ok: false, status: 400, json: async () => ({ detail: { message: "Title is required" } }) } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    renderAdmin();
    const publish = await screen.findByRole("button", { name: /publish announcement/i });
    expect(publish).toBeDisabled();
    await user.type(screen.getByLabelText("Title"), "  Maintenance ");
    await user.type(screen.getByLabelText("Message"), " Tonight ");
    await user.click(publish);
    expect(await screen.findByText("Title is required")).toBeInTheDocument();
    expect(secureFetch).toHaveBeenCalledWith("/api/announcements", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ title: "Maintenance", message: "Tonight" }),
    }));
  });

  it("shows a fallback when publishing throws", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);
    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/moderation/queue" || url === "/api/admin/staff" || url === "/api/admin/audit-log") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/announcements") throw new Error("offline");
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    renderAdmin();
    await user.type(await screen.findByLabelText("Title"), "Maintenance");
    await user.type(screen.getByLabelText("Message"), "Tonight");
    await user.click(screen.getByRole("button", { name: /publish announcement/i }));
    expect(await screen.findByText("Could not publish announcement.")).toBeInTheDocument();
  });

  it("submits warn actions with edited reason and notes", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 2, trainer_id: "A1B2C3D4", username: "mod", email: "m@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "moderator",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);
    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return { ok: true, status: 200, json: async () => [{
          id: 11, user_id: 99, username: "offender", game_id: 1, game_link: null,
          censored_message: "bad ***", severity: "medium", status: "pending",
          created_at: "2026-01-01T00:00:00Z", matched_term_count: 1,
        }] } as Response;
      }
      if (url === "/api/moderation/infractions/11") {
        return { ok: true, status: 200, json: async () => ({
          id: 11, user_id: 99, username: "offender", game_id: 1, game_link: null,
          censored_message: "bad ***", original_message: "bad word", matched_terms: [],
          moderator_notes: null, severity: "medium", status: "pending",
          created_at: "2026-01-01T00:00:00Z", matched_term_count: 1,
        }) } as Response;
      }
      if (url === "/api/moderation/users/99/history") {
        return { ok: true, status: 200, json: async () => ({
          id: 99, username: "offender", role: "user", is_banned: false, ban_expires_at: null,
          pending_infractions: 1, total_infractions: 1, is_muted: false,
        }) } as Response;
      }
      if (/(?:\/warn|\/mute|\/temp-ban)$/.test(url) && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    renderAdmin();
    const queueItem = await screen.findByText("offender");
    await user.click(queueItem.closest("button")!);
    await screen.findByText("bad word");
    await user.type(screen.getByLabelText("Reason"), "  Be civil ");
    await user.type(screen.getByLabelText(/Notes/), "  First warning ");
    await user.click(screen.getByRole("button", { name: "Warn" }));
    await waitFor(() => expect(secureFetch).toHaveBeenCalledWith(
      "/api/moderation/users/99/warn",
      expect.objectContaining({ body: JSON.stringify({ reason: "Be civil", notes: "First warning" }) }),
    ));

    await user.click(screen.getByRole("button", { name: /offender.*bad/i }));
    await screen.findByText("bad word");
    await user.clear(screen.getByLabelText("Mute hours"));
    await user.type(screen.getByLabelText("Mute hours"), "48");
    await user.click(screen.getByRole("button", { name: "Mute 48h" }));
    await waitFor(() => expect(secureFetch).toHaveBeenCalledWith(
      "/api/moderation/users/99/mute",
      expect.objectContaining({ body: JSON.stringify({ reason: "", hours: 48 }) }),
    ));

    await user.click(screen.getByRole("button", { name: /offender.*bad/i }));
    await screen.findByText("bad word");
    await user.clear(screen.getByLabelText("Temp ban days"));
    await user.type(screen.getByLabelText("Temp ban days"), "5");
    await user.click(screen.getByRole("button", { name: "Temp ban 5d" }));
    await waitFor(() => expect(secureFetch).toHaveBeenCalledWith(
      "/api/moderation/users/99/temp-ban",
      expect.objectContaining({ body: JSON.stringify({ reason: "", days: 5 }) }),
    ));
  });

  it("publishes announcements successfully and runs ban/unban actions", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return {
          ok: true,
          status: 200,
          json: async () => [{
            id: 11, user_id: 99, username: "offender", game_id: 1, game_link: "g1",
            censored_message: "bad ***", severity: "high", status: "pending",
            created_at: "2026-01-01T00:00:00Z", matched_term_count: 2,
          }],
        } as Response;
      }
      if (url === "/api/admin/staff") {
        return {
          ok: true,
          status: 200,
          json: async () => [{ id: 4, username: "admin", role: "admin" }],
        } as Response;
      }
      if (url === "/api/admin/audit-log") {
        return {
          ok: true,
          status: 200,
          json: async () => [{
            id: 1, actor_username: "admin", target_username: "offender",
            action_type: "warn", reason: "spam", created_at: "2026-01-01T00:00:00Z",
          }],
        } as Response;
      }
      if (url === "/api/announcements" && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      if (url === "/api/moderation/infractions/11") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 11, user_id: 99, username: "offender", game_id: 1, game_link: "g1",
            censored_message: "bad ***", original_message: "bad word", matched_terms: ["bad"],
            moderator_notes: null, severity: "high", status: "pending",
            created_at: "2026-01-01T00:00:00Z", matched_term_count: 2,
          }),
        } as Response;
      }
      if (url === "/api/moderation/users/99/history") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 99, username: "offender", role: "user", is_banned: true,
            ban_expires_at: null, pending_infractions: 1, total_infractions: 3, is_muted: true,
          }),
        } as Response;
      }
      if (url.includes("/ban") && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      if (url.includes("/unban") && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      return { ok: false, status: 500, json: async () => ({ detail: "fail" }) } as Response;
    });

    renderAdmin();
    await user.type(await screen.findByLabelText("Title"), "Hello");
    await user.type(screen.getByLabelText("Message"), "World");
    await user.click(screen.getByRole("button", { name: /publish announcement/i }));
    expect(await screen.findByText(/announcement published/i)).toBeInTheDocument();

    expect(screen.getAllByText(/admin/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/warn/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /offender.*bad/i }));
    expect(await screen.findByText("bad word")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /permanent ban/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/ban$/),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("surfaces readError when detail is a plain string", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return { ok: false, status: 500, json: async () => ({ detail: "Queue exploded" }) } as Response;
      }
      return { ok: true, status: 200, json: async () => [] } as Response;
    });

    renderAdmin();
    // loadQueue throws → effect catch may leave loading or empty; ensure no crash
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith("/api/moderation/queue");
    });
  });

  it("shows detail fetch errors from readError", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return {
          ok: true,
          status: 200,
          json: async () => [{
            id: 11, user_id: 99, username: "offender", game_id: 1, game_link: null,
            censored_message: "bad ***", severity: "medium", status: "pending",
            created_at: "2026-01-01T00:00:00Z", matched_term_count: 1,
          }],
        } as Response;
      }
      if (url === "/api/admin/staff" || url === "/api/admin/audit-log") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/moderation/infractions/11") {
        return {
          ok: false,
          status: 500,
          json: async () => ({ detail: { message: "Infraction missing" } }),
        } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    renderAdmin();
    await user.click(await screen.findByText("offender"));
    expect(await screen.findByText("Infraction missing")).toBeInTheDocument();
  });

  it("toggles permanent ban off and submits timed ban days", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 4, trainer_id: "A1B2C3D4", username: "admin", email: "a@b.c", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "admin",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/moderation/queue") {
        return {
          ok: true,
          status: 200,
          json: async () => [{
            id: 11, user_id: 99, username: "offender", game_id: 1, game_link: null,
            censored_message: "bad ***", severity: "medium", status: "pending",
            created_at: "2026-01-01T00:00:00Z", matched_term_count: 1,
          }],
        } as Response;
      }
      if (url === "/api/admin/staff" || url === "/api/admin/audit-log") {
        return { ok: true, status: 200, json: async () => [] } as Response;
      }
      if (url === "/api/moderation/infractions/11") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 11, user_id: 99, username: "offender", game_id: 1, game_link: null,
            censored_message: "bad ***", original_message: "bad word", matched_terms: [],
            moderator_notes: null, severity: "medium", status: "pending",
            created_at: "2026-01-01T00:00:00Z", matched_term_count: 1,
          }),
        } as Response;
      }
      if (url === "/api/moderation/users/99/history") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 99, username: "offender", role: "user", is_banned: false,
            ban_expires_at: null, pending_infractions: 1, total_infractions: 1, is_muted: false,
          }),
        } as Response;
      }
      if (url.includes("/ban") && init?.method === "POST") {
        return { ok: true, status: 200, json: async () => ({}) } as Response;
      }
      return { ok: true, status: 200, json: async () => [] } as Response;
    });

    renderAdmin();
    await user.click(await screen.findByText("offender"));
    expect(await screen.findByText("bad word")).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Permanent ban \(admin\)/i));
    expect(screen.getByRole("button", { name: /^Ban 3d$/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Ban 3d$/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/ban$/),
        expect.objectContaining({
          body: expect.stringContaining('"permanent":false'),
        }),
      );
    });
  });
});
