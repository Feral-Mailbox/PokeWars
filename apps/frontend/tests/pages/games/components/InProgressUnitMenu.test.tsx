import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import InProgressUnitMenu from "@/pages/games/components/unit-menus/InProgressUnitMenu";

const { headerSpy } = vi.hoisted(() => ({ headerSpy: vi.fn() }));

vi.mock("@/pages/games/components/unit-menus/UnitMenuShared", () => ({
  UNIT_MENU_WIDTH_CLASS: "unit-menu",
  UnitInfoHeader: (props: any) => {
    headerSpy(props);
    return <div data-testid="header">{props.unit.name}</div>;
  },
  UnitInfoStats: () => <div data-testid="stats" />,
  UnitMoveList: (props: any) => (
    <button type="button" onClick={() => props.onMoveSelect?.({ id: 1 })}>
      Select move
    </button>
  ),
  UnitCredits: () => <div data-testid="credits" />,
}));

const baseProps = {
  activeUnit: {
    unit: { name: "Pikachu" },
    user_id: 7,
    current_hp: 100,
    current_stats: { hp: 100 },
  },
  typeColors: {},
  statusIconSrc: null,
  getStatColor: vi.fn(() => "white"),
  moveMap: {},
  moveTargeting: false,
  selectedMove: null,
  onMoveHoverStart: vi.fn(),
  onMoveHoverEnd: vi.fn(),
  onMoveSelect: vi.fn(),
  onExecuteMove: vi.fn(),
  onCancelMove: vi.fn(),
  onWait: vi.fn(),
  getPlayerColor: vi.fn(() => "#123456"),
};

describe("InProgressUnitMenu", () => {
  it("renders normal, pain, and dizzy portrait frames", () => {
    const { rerender } = render(<InProgressUnitMenu {...baseProps} />);
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ portraitFrameX: 0, portraitFrameY: 0 })
    );

    rerender(
      <InProgressUnitMenu
        {...baseProps}
        activeUnit={{ ...baseProps.activeUnit, current_hp: 50 }}
      />
    );
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ portraitFrameX: 80, portraitFrameY: 0 })
    );

    rerender(
      <InProgressUnitMenu
        {...baseProps}
        activeUnit={{ ...baseProps.activeUnit, current_hp: 20 }}
      />
    );
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ portraitFrameX: 120, portraitFrameY: 80 })
    );
  });

  it("runs move and contextual actions when enabled", async () => {
    const user = userEvent.setup();
    const onPickUpItem = vi.fn();
    const onCapture = vi.fn();
    const props = {
      ...baseProps,
      moveTargeting: true,
      selectedMove: { id: 1 },
      showWaitButton: true,
      showCaptureButton: true,
      captureHpLabel: "10/20",
      onCapture,
      showPickUpButton: true,
      pickUpItemLabel: "Oran Berry",
      pickUpButtonText: "Collect",
      onPickUpItem,
    };

    render(<InProgressUnitMenu {...props} />);

    await user.click(screen.getByRole("button", { name: "Select move" }));
    await user.click(screen.getByRole("button", { name: "Collect: Oran Berry" }));
    await user.click(screen.getByRole("button", { name: "Capture Objective (10/20)" }));
    await user.click(screen.getByRole("button", { name: "Wait" }));
    await user.click(screen.getByRole("button", { name: "Execute Move" }));
    await user.click(screen.getByRole("button", { name: "Cancel Move" }));

    expect(props.onMoveSelect).toHaveBeenCalledWith({ id: 1 });
    expect(onPickUpItem).toHaveBeenCalledOnce();
    expect(onCapture).toHaveBeenCalledOnce();
    expect(props.onWait).toHaveBeenCalledOnce();
    expect(props.onExecuteMove).toHaveBeenCalledOnce();
    expect(props.onCancelMove).toHaveBeenCalledOnce();
  });

  it("renders pick-up/capture without labels and coerces missing hp", () => {
    render(
      <InProgressUnitMenu
        {...baseProps}
        activeUnit={{
          unit: { name: "Missing Stats" },
          user_id: 1,
          current_hp: undefined,
          current_stats: undefined,
        }}
        showPickUpButton
        onPickUpItem={() => {}}
        showCaptureButton
        onCapture={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Pick Up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Capture Objective" })).toBeInTheDocument();
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ currentHp: 0, maxHp: 0, portraitFrameX: 0 }),
    );
  });
});
