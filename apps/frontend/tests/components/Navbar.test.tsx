import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import Navbar from "@/components/Navbar";

const mockNavigate = vi.fn();
const mockSetUser = vi.fn();
const mockClearAuthPrompt = vi.fn();

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

vi.mock("@/state/auth", () => ({
  useAuth: vi.fn(),
}));

import { secureFetch } from "@/utils/secureFetch";
import { useAuth } from "@/state/auth";

function mockAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    setUser: mockSetUser,
    authPrompt: null,
    clearAuthPrompt: mockClearAuthPrompt,
    loading: false,
    ...overrides,
  } as ReturnType<typeof useAuth>);
}

describe("Navbar", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: false,
      json: async () => ({}),
    } as Response);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload: vi.fn() },
    });
    vi.spyOn(window, "alert").mockImplementation(() => {});
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
    vi.restoreAllMocks();
  });

  it("renders logo and guest nav", () => {
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    expect(screen.getByAltText(/logo/i)).toBeInTheDocument();
    expect(screen.getByText(/^Welcome$/)).toBeInTheDocument();
    expect(screen.getByText(/^Games$/)).toBeInTheDocument();
    expect(screen.getByText(/^Guide$/)).toBeInTheDocument();
    expect(screen.getByText(/^Login$/)).toBeInTheDocument();
  });

  it("loads session user on mount", async () => {
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 1,
        trainer_id: 'A1B2C3D4',
        username: "testuser",
        email: "t@e.com",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "user",
      }),
    } as Response);

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith("/api/me");
      expect(mockSetUser).toHaveBeenCalledWith(
        expect.objectContaining({ username: "testuser" })
      );
    });
  });

  it("clears user when session check fails", async () => {
    vi.mocked(secureFetch).mockRejectedValue(new Error("offline"));
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(mockSetUser).toHaveBeenCalledWith(null);
    });
  });

  it("opens games menu and navigates", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    await user.click(screen.getByText(/^Games$/));
    expect(screen.getByText("Create Game")).toBeInTheDocument();
    await user.click(screen.getByText("Create Game"));
    expect(mockNavigate).toHaveBeenCalledWith("/games/create");

    await user.click(screen.getByText(/^Games$/));
    await user.click(screen.getByText("Join Game"));
    expect(mockNavigate).toHaveBeenCalledWith("/games/join");

    await user.click(screen.getByText(/^Games$/));
    await user.click(screen.getByText("In-Progress"));
    expect(mockNavigate).toHaveBeenCalledWith("/games/in-progress");

    await user.click(screen.getByText(/^Games$/));
    await user.click(screen.getByText("Completed"));
    expect(mockNavigate).toHaveBeenCalledWith("/games/completed");
  });

  it("navigates home and guide", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await user.click(screen.getByAltText(/logo/i));
    expect(mockNavigate).toHaveBeenCalledWith("/");
    await user.click(screen.getByText(/^Guide$/));
    expect(mockNavigate).toHaveBeenCalledWith("/guide");
  });

  it("shows staff links and logout for staff users", async () => {
    const user = userEvent.setup();
    mockAuth({
      user: {
        id: 2,
        trainer_id: 'A1B2C3D4',
        username: "mod",
        email: "m@e.com",
        avatar: "",
        elo_conquest: 1000,
  elo_war: 1000,
        currency: 0,
        role: "moderator",
      },
    });

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    expect(screen.getByText(/Welcome,/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "mod" })).toBeInTheDocument();
    expect(screen.getByText("Map Builder")).toBeInTheDocument();
    expect(screen.getByText("Moderation")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "mod" }));
    expect(mockNavigate).toHaveBeenCalledWith("/player/A1B2C3D4");
    await user.click(screen.getByText("Map Builder"));
    expect(mockNavigate).toHaveBeenCalledWith("/map-builder");
    await user.click(screen.getByText("Moderation"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin");

    vi.mocked(secureFetch).mockResolvedValue({ ok: true, json: async () => ({}) } as Response);
    await user.click(screen.getByText("Logout"));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith("/api/logout", { method: "POST" });
      expect(mockSetUser).toHaveBeenCalledWith(null);
      expect(window.location.reload).toHaveBeenCalled();
    });
  });

  it("opens login form, toggles register, and submits login", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    await user.click(screen.getByText(/^Login$/));
    expect(screen.getByPlaceholderText("Username")).toBeInTheDocument();

    await user.click(screen.getByText("Create Account"));
    expect(screen.getByPlaceholderText("Confirm Password")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Email")).toBeInTheDocument();

    await user.click(screen.getByText("Back to Login"));
    await user.type(screen.getByPlaceholderText("Username"), "ash");
    await user.type(screen.getByPlaceholderText("Password"), "secret");

    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ id: 1 }),
    } as Response);

    await user.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        "/api/login",
        expect.objectContaining({ method: "POST" })
      );
      expect(window.location.reload).toHaveBeenCalled();
    });
  });

  it("alerts when register passwords mismatch", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await user.click(screen.getByText(/^Login$/));
    await user.click(screen.getByText("Create Account"));
    await user.type(screen.getByPlaceholderText("Username"), "ash");
    await user.type(screen.getByPlaceholderText("Password"), "a");
    await user.type(screen.getByPlaceholderText("Confirm Password"), "b");
    await user.type(screen.getByPlaceholderText("Email"), "a@b.c");
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(window.alert).toHaveBeenCalledWith("Passwords do not match");
  });

  it("alerts login failure detail messages", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await user.click(screen.getByText(/^Login$/));
    await user.type(screen.getByPlaceholderText("Username"), "ash");
    await user.type(screen.getByPlaceholderText("Password"), "bad");

    vi.mocked(secureFetch).mockResolvedValue({
      ok: false,
      json: async () => ({ detail: { message: "Banned", reason: "spam" } }),
    } as Response);

    await user.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => {
      expect(window.alert).toHaveBeenCalledWith("Banned: spam");
    });
  });

  it("opens auth prompt dropdown from homepage prompt", async () => {
    mockAuth({ authPrompt: "register" });
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByPlaceholderText("Confirm Password")).toBeInTheDocument();
      expect(mockClearAuthPrompt).toHaveBeenCalled();
    });
  });

  it("closes menus on outside click", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );
    await user.click(screen.getByText(/^Games$/));
    expect(screen.getByText("Create Game")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    await waitFor(() => {
      expect(screen.queryByText("Create Game")).not.toBeInTheDocument();
    });
  });
});
