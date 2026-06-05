export type UserRole = "user" | "moderator" | "admin";

export type User = {
  id: number;
  username: string;
  email: string;
  avatar: string;
  elo: number;
  currency: number;
  role: UserRole;
};

export function isStaff(user: User | null | undefined): boolean {
  return user?.role === "moderator" || user?.role === "admin";
}

export function isAdmin(user: User | null | undefined): boolean {
  return user?.role === "admin";
}
