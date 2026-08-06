import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  formatTmDisplayName,
  normalizeCredits,
  UnitCredits,
  unitCanLearnTmMove,
} from "@/pages/games/components/unit-menus/UnitMenuShared";

describe("UnitMenuShared helpers", () => {
  it("formats TM display names", () => {
    expect(formatTmDisplayName("TM01", "Focus Punch")).toBe("TM01 - Focus Punch");
    expect(formatTmDisplayName("TM7")).toBe("TM07");
    expect(formatTmDisplayName("Oran Berry", "Heal")).toBe("Oran Berry - Heal");
    expect(formatTmDisplayName("Oran Berry")).toBe("Oran Berry");
    expect(formatTmDisplayName("")).toBe("");
    expect(formatTmDisplayName(null as unknown as string)).toBeNull();
  });

  it("checks TM learnsets and normalizes credits", () => {
    expect(unitCanLearnTmMove({ tm_moves: [12, 34] }, 34)).toBe(true);
    expect(unitCanLearnTmMove({ tm_moves: [12] }, 99)).toBe(false);
    expect(unitCanLearnTmMove({}, 1)).toBe(false);
    expect(unitCanLearnTmMove({ tm_moves: "nope" }, 1)).toBe(false);
    expect(normalizeCredits(["  a ", "", null, "b"])).toEqual(["a", "b"]);
    expect(normalizeCredits("nope")).toEqual([]);
  });

  it("renders unit credit lines when present", () => {
    const { rerender } = render(
      <UnitCredits
        unit={{
          portrait_credits: ["Alice"],
          sprite_credits: ["Bob"],
        }}
      />
    );
    expect(screen.getByText(/Portrait:/)).toBeInTheDocument();
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
    expect(screen.getByText(/Sprite:/)).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();

    rerender(<UnitCredits unit={{}} />);
    expect(screen.queryByText(/Portrait:/)).not.toBeInTheDocument();

    rerender(<UnitCredits unit={{ portrait_credits: ["Only"], sprite_credits: [] }} />);
    expect(screen.getByText(/Portrait:/)).toBeInTheDocument();
    expect(screen.queryByText(/Sprite:/)).not.toBeInTheDocument();

    rerender(<UnitCredits unit={{ portrait_credits: [], sprite_credits: ["Only"] }} />);
    expect(screen.queryByText(/Portrait:/)).not.toBeInTheDocument();
    expect(screen.getByText(/Sprite:/)).toBeInTheDocument();
  });
});
