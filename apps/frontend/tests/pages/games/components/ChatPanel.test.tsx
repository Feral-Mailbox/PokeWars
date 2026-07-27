import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPanel from "@/pages/games/components/ChatPanel";

describe("ChatPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    Element.prototype.scrollIntoView = vi.fn();
  });

  const baseProps = {
    chatInput: "",
    onChatInputChange: vi.fn(),
    onSendChat: vi.fn(),
    playerColorMap: { 1: "#0000FF80", 2: "#FF0000" },
    usernameColorMap: { Ash: "#0000FF80", Misty: "#FF000080" },
    playerSlots: [
      {
        kind: "joined" as const,
        slotIndex: 0,
        playerId: 1,
        username: "Ash",
        cash: 500,
        unitCount: 2,
      },
      { kind: "waiting" as const, slotIndex: 1 },
      {
        kind: "joined" as const,
        slotIndex: 2,
        playerId: 2,
        username: "Misty",
        cash: 100,
        unitCount: 30,
      },
    ],
    unitLimit: 30,
    currentUserId: 1,
  };

  it("renders players tab with waiting slots and unit limit coloring", () => {
    render(<ChatPanel {...baseProps} chatEntries={[]} />);
    expect(screen.getByText("Ash")).toBeInTheDocument();
    expect(screen.getByText("Waiting for Player...")).toBeInTheDocument();
    expect(screen.getByText("30/30")).toBeInTheDocument();
    expect(screen.queryByText("No players yet.")).not.toBeInTheDocument();
  });

  it("shows empty players message", () => {
    render(<ChatPanel {...baseProps} playerSlots={[]} chatEntries={[]} />);
    expect(screen.getByText("No players yet.")).toBeInTheDocument();
  });

  it("switches to chat, groups move effects, mentions, and sends", async () => {
    const user = userEvent.setup();
    const onChatInputChange = vi.fn();
    const onSendChat = vi.fn();

    render(
      <ChatPanel
        {...baseProps}
        chatInput="hi Ash"
        onChatInputChange={onChatInputChange}
        onSendChat={onSendChat}
        chatEntries={[
          { id: "1", kind: "chat", text: "hello Ash there", username: "Misty", playerId: 2 },
          { id: "2", kind: "system", text: "Turn 3" },
          { id: "3", kind: "system", text: "Ash's turn" },
          { id: "4", kind: "system", text: "Pikachu used Thunderbolt" },
          { id: "5", kind: "system", text: "Squirtle took 40 damage" },
          { id: "6", kind: "system", text: "Squirtle fainted!" },
          { id: "7", kind: "system", text: "Bulbasaur regained 10 health" },
          { id: "8", kind: "system", text: "Charmander dodged the attack" },
          { id: "9", kind: "system", text: "Oddish was poisoned" },
          { id: "10", kind: "system", text: "Geodude's Defense rose" },
          { id: "11", kind: "system", text: "Unrelated system note" },
        ]}
      />
    );

    await user.click(screen.getByRole("button", { name: "Chat" }));
    expect(screen.getByText("Misty")).toBeInTheDocument();
    expect(screen.getByText(/Pikachu used Thunderbolt/)).toBeInTheDocument();
    expect(screen.getByText(/Squirtle took 40 damage/)).toBeInTheDocument();
    expect(screen.getByText(/Squirtle fainted!/)).toBeInTheDocument();
    expect(screen.getByText("Turn 3")).toBeInTheDocument();
    expect(screen.getByText(/'s turn/)).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/Send a message/i);
    await user.type(input, "x");
    expect(onChatInputChange).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onSendChat).toHaveBeenCalled();
  });

  it("collapses and expands the sidebar", async () => {
    const user = userEvent.setup();
    render(<ChatPanel {...baseProps} chatEntries={[]} />);

    await user.click(screen.getByTitle("Collapse"));
    expect(screen.getByTitle("Expand sidebar")).toBeInTheDocument();
    expect(localStorage.getItem("chatPanelCollapsed")).toBe("true");

    await user.click(screen.getByTitle("Expand sidebar"));
    expect(screen.getByTitle("Collapse")).toBeInTheDocument();
  });

  it("renders spectator chat in gray without player colors", async () => {
    const user = userEvent.setup();
    render(
      <ChatPanel
        {...baseProps}
        chatEntries={[
          {
            id: "spec-1",
            kind: "chat",
            text: "nice play Misty",
            username: "Viewer",
            playerId: 99,
            isSpectator: true,
          },
        ]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Chat" }));
    const name = screen.getByText("Viewer");
    expect(name).toHaveStyle({ color: "#9ca3af" });
    expect(screen.getByText("nice play Misty")).toHaveClass("text-slate-400");
  });
});
