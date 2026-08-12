import { createPortal } from "react-dom";

export type JailOccupant = {
  name: string;
  color: string;
};

type JailTooltipProps = {
  ownerLabel: string;
  occupants: JailOccupant[];
  x: number;
  y: number;
  visible: boolean;
};

export default function JailTooltip({
  ownerLabel,
  occupants,
  x,
  y,
  visible,
}: JailTooltipProps) {
  if (!visible) return null;

  return createPortal(
    <div
      className="fixed z-[60] pointer-events-none max-w-xs rounded border border-purple-400/70 bg-gray-900 px-3 py-2 shadow-lg"
      style={{ left: x, top: y + 14 }}
      role="tooltip"
    >
      <p className="text-sm font-semibold leading-snug text-purple-200">{ownerLabel}</p>
      {occupants.length === 0 ? (
        <p className="mt-1 text-xs text-gray-400">Empty</p>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {occupants.map((occupant, index) => (
            <li
              key={`${occupant.name}-${index}`}
              className="text-sm font-semibold leading-snug"
              style={{ color: occupant.color }}
            >
              {occupant.name}
            </li>
          ))}
        </ul>
      )}
    </div>,
    document.body
  );
}
