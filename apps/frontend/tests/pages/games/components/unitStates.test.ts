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
  it("parses active unit states", () => {
    expect(getActiveUnitState(null)).toBeNull();
    expect(getActiveUnitState(["confusion", 3])).toEqual({
      name: "confusion",
      turnsRemaining: 3,
    });
    expect(getActiveUnitState(["", 3])).toBeNull();
    expect(getActiveUnitState(["flinch", 0])).toBeNull();
    expect(getActiveUnitState("Taunt")).toEqual({
      name: "taunt",
      turnsRemaining: 1,
    });
    expect(getActiveUnitState({})).toBeNull();
  });

  it("labels effects and formats tooltips", () => {
    expect(getStateLabel("light_screen")).toBe("Light Screen");
    expect(getStateLabel("mystery_buff")).toBe("Mystery Buff");
    expect(getStateEffect("reflect")).toMatch(/physical/i);
    expect(getStateEffect("unknown_state")).toBe("Unknown State");

    expect(stateShowsRoundCount({ name: "confusion", turnsRemaining: 2 })).toBe(false);
    expect(formatStateTooltipContent({ name: "confusion", turnsRemaining: 2 }).roundsLine).toBeUndefined();

    const timed = formatStateTooltipContent({ name: "taunt", turnsRemaining: 2 });
    expect(timed.name).toBe("Taunt");
    expect(timed.roundsLine).toBe("2 rounds left");
    expect(formatStateTooltipContent({ name: "taunt", turnsRemaining: 1 }).roundsLine).toBe(
      "1 round left"
    );

    const permanent = formatStateTooltipContent({
      name: "ingrain",
      turnsRemaining: PERMANENT_STATE_TURN_COUNT,
    });
    expect(permanent.roundsLine).toBeUndefined();
    expect(
      stateShowsRoundCount({
        name: "ingrain",
        turnsRemaining: PERMANENT_STATE_TURN_COUNT,
      })
    ).toBe(false);
  });
});
