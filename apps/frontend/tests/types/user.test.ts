import { describe, expect, it } from "vitest";
import { isAdmin, isStaff, type User } from "@/types/user";

const baseUser: User = {
  id: 1,
  username: "ash",
  email: "ash@example.com",
  avatar: "",
  elo: 1000,
  currency: 0,
  role: "user",
};

describe("user role helpers", () => {
  it("detects staff and admin roles", () => {
    expect(isStaff(null)).toBe(false);
    expect(isStaff(baseUser)).toBe(false);
    expect(isStaff({ ...baseUser, role: "moderator" })).toBe(true);
    expect(isStaff({ ...baseUser, role: "admin" })).toBe(true);
    expect(isAdmin(baseUser)).toBe(false);
    expect(isAdmin({ ...baseUser, role: "moderator" })).toBe(false);
    expect(isAdmin({ ...baseUser, role: "admin" })).toBe(true);
  });
});
