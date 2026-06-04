import { describe, expect, it } from "vitest";
import {
  formatStateTooltipContent,
  getActiveUnitState,
  getStateEffect,
  getStateLabel,
  PERMANENT_STATE_TURN_COUNT,
  stateShowsRoundCount,
} from "@/pages/games/components/unit-menus/unitStates";

describe("unitStates", () => {
  it("returns null when no active state is present", () => {
    expect(getActiveUnitState(null)).toBeNull();
    expect(getActiveUnitState([])).toBeNull();
    expect(getActiveUnitState(["reflect", 0])).toBeNull();
  });

  it("parses active state tuples from the backend", () => {
    expect(getActiveUnitState(["reflect", 4])).toEqual({
      name: "reflect",
      turnsRemaining: 4,
    });
  });

  it("formats confusion tooltip with name and description only", () => {
    expect(
      formatStateTooltipContent({
        name: "confusion",
        turnsRemaining: 3,
      })
    ).toEqual({
      name: "Confusion",
      description: "May hurt itself when acting",
    });
    expect(stateShowsRoundCount({ name: "confusion", turnsRemaining: 3 })).toBe(false);
  });

  it("formats timed states with name, description, and rounds remaining", () => {
    expect(
      formatStateTooltipContent({
        name: "reflect",
        turnsRemaining: 2,
      })
    ).toEqual({
      name: "Reflect",
      description: "Reduces physical damage taken",
      roundsLine: "2 rounds left",
    });
  });

  it("uses a singular round label when one round remains", () => {
    expect(
      formatStateTooltipContent({
        name: "flinch",
        turnsRemaining: 1,
      })
    ).toEqual({
      name: "Flinch",
      description: "Cannot act this turn",
      roundsLine: "1 round left",
    });
  });

  it("omits round count for permanent effects", () => {
    expect(
      formatStateTooltipContent({
        name: "nightmare",
        turnsRemaining: PERMANENT_STATE_TURN_COUNT,
      })
    ).toEqual({
      name: "Nightmare",
      description: "Loses HP while asleep",
    });
    expect(
      stateShowsRoundCount({
        name: "nightmare",
        turnsRemaining: PERMANENT_STATE_TURN_COUNT,
      })
    ).toBe(false);
  });

  it("falls back to formatted state names for unknown effects", () => {
    expect(getStateLabel("custom_state")).toBe("Custom State");
    expect(getStateEffect("custom_state")).toBe("Custom State");
  });
});
