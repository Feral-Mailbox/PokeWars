import { createPortal } from "react-dom";

type MapItemTooltipProps = {
  label: string;
  x: number;
  y: number;
  visible: boolean;
};

export default function MapItemTooltip({ label, x, y, visible }: MapItemTooltipProps) {
  if (!visible || !label) return null;

  return createPortal(
    <div
      className="fixed z-[60] pointer-events-none max-w-xs rounded border border-gray-500 bg-gray-900 px-3 py-2 shadow-lg"
      style={{ left: x, top: y + 14 }}
      role="tooltip"
    >
      <p className="text-sm font-semibold leading-snug text-white">{label}</p>
    </div>,
    document.body
  );
}
