import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Login from "@/pages/Login";

const navigate = vi.fn();

vi.mock("@/state/auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigate };
});

import { useAuth } from "@/state/auth";

describe("Login", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderLogin(entry = "/login") {
    return render(
      <MemoryRouter initialEntries={[entry]}>
        <Login />
      </MemoryRouter>,
    );
  }

  it("explains where signed-out players can log in", () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false } as ReturnType<typeof useAuth>);

    renderLogin();

    expect(screen.getByRole("heading", { name: /welcome.*login/i })).toBeInTheDocument();
    expect(screen.getByText(/login form in the navbar/i)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("redirects authenticated players to their requested next path", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 1, trainer_id: "A1B2C3D4", username: "ash", email: "ash@example.com", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "user",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    renderLogin("/login?next=/games/abc123");

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/games/abc123"));
  });

  it("redirects authenticated players home without a next parameter", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 1, trainer_id: "A1B2C3D4", username: "ash", email: "ash@example.com", avatar: "",
        elo_conquest: 1000, elo_war: 1000, currency: 0, role: "user",
      },
      loading: false,
    } as ReturnType<typeof useAuth>);

    renderLogin();

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/"));
  });
});
