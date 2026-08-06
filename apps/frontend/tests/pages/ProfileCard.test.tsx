import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AvatarMark, normalizeProfileView, ProfileCard, roleLabel } from '@/pages/ProfileCard';

describe('ProfileCard helpers', () => {
  it('normalizes legacy, invalid, and missing profile values', () => {
    expect(normalizeProfileView({ elo: 1200, username: 'Misty' })).toMatchObject({
      username: 'Misty',
      avatar: 'default.png',
      elo_conquest: 1200,
      elo_war: 1200,
      currency: 0,
      role: 'user',
    });
    expect(normalizeProfileView({ elo_conquest: Number.NaN, elo_war: null, currency: Number.NaN }))
      .toMatchObject({ elo_conquest: 1000, elo_war: 1000, currency: 0 });
    expect(roleLabel('admin')).toBe('Admin');
    expect(roleLabel('moderator')).toBe('Moderator');
    expect(roleLabel('user')).toBe('Trainer');
  });

  it('renders initials or a custom avatar and optional email', () => {
    const { rerender, container } = render(<AvatarMark username=" misty" avatar="default.png" />);
    expect(screen.getByText('M')).toBeInTheDocument();

    rerender(<AvatarMark username="" avatar="/misty.png" />);
    expect(container.querySelector('img')).toHaveAttribute('src', '/misty.png');

    render(
      <ProfileCard
        profile={{
          trainer_id: 'T1',
          username: 'Misty',
          avatar: 'default.png',
          elo_conquest: 1100,
          elo_war: 900,
          currency: 20,
          role: 'moderator',
          email: 'misty@example.com',
        }}
        showEmail
      >
        <p>Extra content</p>
      </ProfileCard>,
    );
    expect(screen.getByText('misty@example.com')).toBeInTheDocument();
    expect(screen.getByText('Extra content')).toBeInTheDocument();
    expect(screen.getByText('Moderator')).toBeInTheDocument();
  });

  it('does not expose an email when disabled or absent', () => {
    render(
      <ProfileCard
        profile={{
          trainer_id: 'T1', username: 'Brock', avatar: 'default.png', elo_conquest: 1000,
          elo_war: 1000, currency: 0, role: 'user', email: 'brock@example.com',
        }}
      />,
    );
    expect(screen.queryByText('brock@example.com')).not.toBeInTheDocument();
  });
});
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AvatarMark,
  normalizeProfileView,
  ProfileCard,
  roleLabel,
} from "@/pages/ProfileCard";

describe("ProfileCard helpers", () => {
  it("normalizes legacy elo and invalid numbers", () => {
    expect(normalizeProfileView({ username: "ash", elo: 1200 })).toMatchObject({
      elo_conquest: 1200,
      elo_war: 1200,
      avatar: "default.png",
      role: "user",
      currency: 0,
    });
    expect(
      normalizeProfileView({
        username: "misty",
        elo_conquest: Number.NaN,
        elo_war: Number.POSITIVE_INFINITY,
        currency: Number.NaN,
        avatar: undefined,
        role: undefined,
      }),
    ).toMatchObject({
      elo_conquest: 1000,
      elo_war: 1000,
      currency: 0,
      avatar: "default.png",
      role: "user",
    });
  });

  it("maps role labels", () => {
    expect(roleLabel("admin")).toBe("Admin");
    expect(roleLabel("moderator")).toBe("Moderator");
    expect(roleLabel("user")).toBe("Trainer");
  });

  it("renders custom avatars, email, and children", () => {
    render(
      <ProfileCard
        showEmail
        profile={{
          trainer_id: "ABCD1234",
          username: "ash",
          avatar: "https://example.com/a.png",
          elo_conquest: 1100,
          elo_war: 900,
          currency: 50,
          role: "admin",
          email: "ash@example.com",
        }}
      >
        <button type="button">Edit</button>
      </ProfileCard>,
    );

    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("ash@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(document.querySelector("img")?.getAttribute("src")).toBe(
      "https://example.com/a.png",
    );
  });

  it("falls back to username initial when avatar is default", () => {
    render(<AvatarMark username="  misty" avatar="default.png" />);
    expect(screen.getByText("M")).toBeInTheDocument();
  });

  it("uses question mark initial for blank usernames", () => {
    render(<AvatarMark username="   " avatar="" />);
    expect(screen.getByText("?")).toBeInTheDocument();
  });
});
