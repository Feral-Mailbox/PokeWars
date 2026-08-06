import { afterEach, describe, expect, it } from "vitest";
import { useAuth } from "@/state/auth";

describe("auth state", () => {
  afterEach(() => {
    useAuth.setState({ user: null, loading: true, authPrompt: null });
  });

  it("logs out and marks authentication as finished", () => {
    useAuth.getState().setUser({
      id: 1, trainer_id: "A1B2C3D4", username: "ash", email: "ash@example.com", avatar: "",
      elo_conquest: 1000, elo_war: 1000, currency: 0, role: "user",
    });

    useAuth.getState().logout();

    expect(useAuth.getState()).toMatchObject({ user: null, loading: false });
  });

  it("opens and clears each auth prompt mode", () => {
    useAuth.getState().requestAuthPrompt("login");
    expect(useAuth.getState().authPrompt).toBe("login");

    useAuth.getState().requestAuthPrompt("register");
    expect(useAuth.getState().authPrompt).toBe("register");

    useAuth.getState().clearAuthPrompt();
    expect(useAuth.getState().authPrompt).toBeNull();
  });
});
