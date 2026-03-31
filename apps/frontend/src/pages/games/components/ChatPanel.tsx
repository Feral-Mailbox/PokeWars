import { useEffect, useRef, useState } from "react";

type ChatEntry = {
  id: string;
  kind: "chat" | "system";
  text: string;
  username?: string;
  playerId?: number;
};

type MoveBullet = {
  text: string;
};

type RenderRow =
  | {
      id: string;
      kind: "chat";
      username?: string;
      playerId?: number;
      text: string;
    }
  | {
      id: string;
      kind: "system";
      group: "move" | "other";
      text: string;
      bullets?: MoveBullet[];
    };

interface ChatPanelProps {
  chatEntries: ChatEntry[];
  chatInput: string;
  onChatInputChange: (value: string) => void;
  onSendChat: () => void;
  playerColorMap: Record<number, string>;
  usernameColorMap: Record<string, string>;
}

function getPlayerColor(playerId: number, playerColorMap: Record<number, string>): string {
  return playerColorMap[playerId] ?? "#00000000";
}

function getPlayerTextColor(playerId: number | undefined, playerColorMap: Record<number, string>): string {
  if (typeof playerId !== "number") return "#ffffff";
  const fillColor = getPlayerColor(playerId, playerColorMap);
  if (!fillColor || fillColor.length < 7) return "#ffffff";
  if (fillColor.length === 9) {
    return `${fillColor.slice(0, 7)}FF`;
  }
  return fillColor;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function toOpaquePlayerColor(fillColor: string): string {
  if (!fillColor || fillColor.length < 7) return "#ffffff";
  if (fillColor.length === 9) return `${fillColor.slice(0, 7)}FF`;
  return fillColor;
}

function renderTextWithMentions(
  text: string,
  usernameColorMap: Record<string, string>,
  defaultClassName: string,
) {
  const rawText = String(text ?? "");
  const usernames = Object.keys(usernameColorMap).filter((name) => Boolean(name && name.trim()));
  if (usernames.length === 0) {
    return <span className={defaultClassName}>{rawText}</span>;
  }

  usernames.sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(${usernames.map((name) => escapeRegex(name)).join("|")})`, "gi");
  const colorByLower = new Map(
    Object.entries(usernameColorMap).map(([name, color]) => [name.toLowerCase(), toOpaquePlayerColor(color)]),
  );

  const nodes = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(rawText)) !== null) {
    const start = match.index;
    const end = start + match[0].length;

    if (start > cursor) {
      nodes.push(
        <span key={`text-${cursor}`} className={defaultClassName}>
          {rawText.slice(cursor, start)}
        </span>,
      );
    }

    const mention = match[0];
    const mentionColor = colorByLower.get(mention.toLowerCase()) ?? "#ffffff";
    nodes.push(
      <span key={`mention-${start}`} className="font-semibold" style={{ color: mentionColor }}>
        {mention}
      </span>,
    );

    cursor = end;
  }

  if (cursor < rawText.length) {
    nodes.push(
      <span key={`text-tail-${cursor}`} className={defaultClassName}>
        {rawText.slice(cursor)}
      </span>,
    );
  }

  if (nodes.length === 0) {
    return <span className={defaultClassName}>{rawText}</span>;
  }

  return <>{nodes}</>;
}

function isTurnBannerMessage(text: string): boolean {
  return /^Turn\s+\d+$/i.test(String(text || "").trim());
}

function isPlayerTurnMessage(text: string): boolean {
  return /^.+\'s\s+turn$/i.test(String(text || "").trim());
}

function getSystemMessageClassName(text: string): string {
  if (isTurnBannerMessage(text)) {
    return "text-slate-100 font-bold text-base";
  }
  if (isPlayerTurnMessage(text)) {
    return "text-slate-200 font-semibold text-[15px]";
  }
  return "text-slate-300";
}

function isMoveUseMessage(text: string): boolean {
  return /\sused\s/i.test(String(text || "").trim());
}

function parseDirectMoveDamageUnit(text: string): string | null {
  const normalized = String(text || "").trim();
  const match = normalized.match(/^(.*?)\s+took\s+\d+\s+damage(?:\s+as\s+recoil)?(?:\s+\(Critical Hit!\))?$/i);
  if (!match) return null;
  return String(match[1] || "").trim() || null;
}

function parseMoveHealingUnit(text: string): string | null {
  const normalized = String(text || "").trim();
  const match = normalized.match(/^(.*?)\s+regained\s+\d+\s+health$/i);
  if (!match) return null;
  return String(match[1] || "").trim() || null;
}

function parseMoveDodgeUnit(text: string): string | null {
  const normalized = String(text || "").trim();
  const match = normalized.match(/^(.*?)\s+dodged\s+the\s+attack$/i);
  if (!match) return null;
  return String(match[1] || "").trim() || null;
}

function isStatusInflictionMessage(text: string): boolean {
  const normalized = String(text || "").trim();
  return /^(.*?)\s+was\s+(burned|asleep|poisoned|badly\s+poisoned|frozen|paralyzed)$/i.test(normalized);
}

function isStatStageMessage(text: string): boolean {
  const normalized = String(text || "").trim();
  return /^(.*?)'s\s+.+\s+(rose|rose\s+sharply|rose\s+drastically|fell|harshly\s+fell|severely\s+fell|won't\s+go\s+higher|won't\s+go\s+lower)\.?$/i.test(normalized);
}

function parseFaintedUnit(text: string): string | null {
  const normalized = String(text || "").trim();
  const match = normalized.match(/^(.*?)\s+fainted!?$/i);
  if (!match) return null;
  return String(match[1] || "").trim() || null;
}

function buildRenderRows(chatEntries: ChatEntry[]): RenderRow[] {
  const rows: RenderRow[] = [];

  for (let i = 0; i < chatEntries.length; i++) {
    const entry = chatEntries[i];

    if (entry.kind === "chat") {
      rows.push({
        id: entry.id,
        kind: "chat",
        username: entry.username,
        playerId: entry.playerId,
        text: entry.text,
      });
      continue;
    }

    const text = String(entry.text || "").trim();
    if (!isMoveUseMessage(text)) {
      rows.push({
        id: entry.id,
        kind: "system",
        group: "other",
        text: entry.text,
      });
      continue;
    }

    const bullets: MoveBullet[] = [];
    let cursor = i + 1;

    while (cursor < chatEntries.length) {
      const candidate = chatEntries[cursor];
      if (candidate.kind !== "system") break;

      const candidateText = String(candidate.text || "").trim();
      if (isMoveUseMessage(candidateText)) break;

      const damageUnit = parseDirectMoveDamageUnit(candidateText);
      const healUnit = parseMoveHealingUnit(candidateText);
      const dodgeUnit = parseMoveDodgeUnit(candidateText);
      const isStatusInfliction = isStatusInflictionMessage(candidateText);
      const isStatStage = isStatStageMessage(candidateText);
      const affectedUnit = damageUnit ?? healUnit ?? dodgeUnit;
      const isRelatedMoveEffect = Boolean(affectedUnit) || isStatusInfliction || isStatStage;
      if (!isRelatedMoveEffect) break;

      let faintText: string | null = null;
      const nextEntry = cursor + 1 < chatEntries.length ? chatEntries[cursor + 1] : null;
      if (!dodgeUnit && nextEntry && nextEntry.kind === "system") {
        const faintedUnit = parseFaintedUnit(nextEntry.text);
        if (faintedUnit && faintedUnit.toLowerCase() === affectedUnit.toLowerCase()) {
          faintText = String(nextEntry.text || "").trim();
          cursor += 1;
        }
      }

      bullets.push({ text: candidateText });
      if (faintText) {
        bullets.push({ text: faintText });
      }
      cursor += 1;
    }

    rows.push({
      id: entry.id,
      kind: "system",
      group: "move",
      text: entry.text,
      bullets,
    });

    i = cursor - 1;
  }

  return rows;
}

function shouldRenderDivider(prevEntry: RenderRow | null, currentEntry: RenderRow): boolean {
  if (!prevEntry) return false;

  if (prevEntry.kind === "chat" && currentEntry.kind === "chat") return false;

  if (prevEntry.kind === "system" && currentEntry.kind === "system") {
    if (prevEntry.group === "move" && currentEntry.group === "move") return true;
    if (prevEntry.group === "move" || currentEntry.group === "move") return true;
    return true;
  }

  return true;
}

export default function ChatPanel({
  chatEntries,
  chatInput,
  onChatInputChange,
  onSendChat,
  playerColorMap,
  usernameColorMap,
}: ChatPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const stored = localStorage.getItem("chatPanelCollapsed");
    return stored ? JSON.parse(stored) : false;
  });
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatEntries]);

  useEffect(() => {
    localStorage.setItem("chatPanelCollapsed", JSON.stringify(isCollapsed));
  }, [isCollapsed]);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    onSendChat();
  };

  const renderRows = buildRenderRows(chatEntries);

  return (
    <>
      <aside
        className={`fixed top-24 right-4 z-30 w-[340px] h-[calc(100vh-7rem)] bg-slate-900/95 border border-slate-700 rounded-lg shadow-xl flex flex-col transition-transform duration-300 ${
          isCollapsed ? "translate-x-[120%] pointer-events-none" : "translate-x-0"
        }`}
      >
        <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-100">Game Chat</h2>
          <button
            onClick={() => setIsCollapsed(true)}
            className="text-slate-400 hover:text-slate-200 text-xs font-semibold"
            title="Collapse"
          >
            {">"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 text-sm">
          {renderRows.length === 0 && <p className="text-slate-400">No messages yet.</p>}

          {renderRows.map((entry, index) => {
            const prevEntry = index > 0 ? renderRows[index - 1] : null;
            const showDivider = shouldRenderDivider(prevEntry, entry);

            return (
              <div key={entry.id}>
                {showDivider && <div className="my-2 border-t border-slate-600"></div>}

                {entry.kind === "chat" ? (
                  <div className="break-words leading-snug">
                    <span
                      style={{ color: getPlayerTextColor(entry.playerId, playerColorMap) }}
                      className="font-semibold mr-2"
                    >
                      {entry.username}
                    </span>
                    {renderTextWithMentions(entry.text, usernameColorMap, "text-slate-100")}
                  </div>
                ) : (
                  <div className="break-words leading-snug">
                    {renderTextWithMentions(entry.text, usernameColorMap, getSystemMessageClassName(entry.text))}
                    {entry.group === "move" && Array.isArray(entry.bullets) && entry.bullets.length > 0 && (
                      <ul className="mt-1 ml-4 list-disc text-slate-300 space-y-1">
                        {entry.bullets.map((bullet, bulletIndex) => (
                          <li key={`${entry.id}-bullet-${bulletIndex}`}>
                            {renderTextWithMentions(bullet.text, usernameColorMap, "text-slate-300")}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          <div ref={chatEndRef} />
        </div>

        <form className="p-3 border-t border-slate-700 flex gap-2" onSubmit={handleSubmit}>
          <input
            value={chatInput}
            onChange={(e) => onChatInputChange(e.target.value)}
            maxLength={300}
            placeholder="Send a message..."
            className="flex-1 bg-slate-800 text-white text-sm rounded px-2 py-1 outline-none border border-slate-600 focus:border-blue-400"
          />
          <button
            type="submit"
            className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold"
          >
            Send
          </button>
        </form>
      </aside>

      {isCollapsed && (
        <button
          onClick={() => setIsCollapsed(false)}
          className="fixed top-24 right-4 z-30 w-12 h-12 bg-slate-900/95 border border-slate-700 rounded shadow-xl text-slate-400 hover:text-slate-200 text-lg font-bold flex items-center justify-center"
          title="Expand chat"
        >
          {"<"}
        </button>
      )}
    </>
  );
}
