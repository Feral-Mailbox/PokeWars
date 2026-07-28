export type UserRole = "user" | "moderator" | "admin";

export type User = {
  id: number;
  trainer_id: string;
  username: string;
  email: string;
  avatar: string;
  elo_conquest: number;
  elo_war: number;
  currency: number;
  role: UserRole;
};

export function isStaff(user: User | null | undefined): boolean {
  return user?.role === "moderator" || user?.role === "admin";
}

export function isModerator(user: User | null | undefined): boolean {
  return user?.role === "moderator";
}

export function isAdmin(user: User | null | undefined): boolean {
  return user?.role === "admin";
}
