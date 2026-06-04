import { createPortal } from "react-dom";
import type { StateTooltipContent } from "./unitStates";

type UnitStateTooltipProps = {
  content: StateTooltipContent | null;
  x: number;
  y: number;
  visible: boolean;
};

export default function UnitStateTooltip({ content, x, y, visible }: UnitStateTooltipProps) {
  if (!visible || !content) return null;

  return createPortal(
    <div
      className="fixed z-[60] pointer-events-none max-w-xs rounded border border-gray-500 bg-gray-900 px-3 py-2 shadow-lg"
      style={{ left: x, top: y + 14 }}
      role="tooltip"
    >
      <p className="text-sm font-semibold leading-snug text-white">{content.name}</p>
      <p className="mt-0.5 text-xs leading-snug text-gray-500">{content.description}</p>
      {content.roundsLine && (
        <p className="mt-1 text-xs text-gray-300">{content.roundsLine}</p>
      )}
    </div>,
    document.body
  );
}
