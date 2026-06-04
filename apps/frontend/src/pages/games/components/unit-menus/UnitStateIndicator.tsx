import { useCallback, useState } from "react";
import UnitStateTooltip from "./UnitStateTooltip";
import {
  formatStateTooltipContent,
  getActiveUnitState,
  getStateLabel,
} from "./unitStates";

function getStateIconUrl(): string {
  const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
  const normalizedBase = assetBase.startsWith("http")
    ? assetBase
    : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
  return `${normalizedBase.replace(/\/$/, "")}/misc/status_icon.svg`;
}

type UnitStateIndicatorProps = {
  states?: unknown;
};

export default function UnitStateIndicator({ states }: UnitStateIndicatorProps) {
  const activeState = getActiveUnitState(states);
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });

  const updateTooltipPosition = useCallback((clientX: number, clientY: number) => {
    setTooltipPosition({ x: clientX, y: clientY });
  }, []);

  if (!activeState) return null;

  const tooltipContent = formatStateTooltipContent(activeState);

  return (
    <>
      <button
        type="button"
        className="inline-flex shrink-0 items-center justify-center p-0 border-0 bg-transparent cursor-help"
        aria-label={`Active state: ${getStateLabel(activeState.name)}`}
        onMouseEnter={(e) => {
          updateTooltipPosition(e.clientX, e.clientY);
          setTooltipOpen(true);
        }}
        onMouseMove={(e) => updateTooltipPosition(e.clientX, e.clientY)}
        onMouseLeave={() => setTooltipOpen(false)}
        onFocus={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          updateTooltipPosition(rect.left + rect.width / 2, rect.bottom);
          setTooltipOpen(true);
        }}
        onBlur={() => setTooltipOpen(false)}
      >
        <img
          src={getStateIconUrl()}
          alt=""
          className="w-5 h-5 object-contain invert"
          aria-hidden
        />
      </button>
      <UnitStateTooltip
        content={tooltipContent}
        x={tooltipPosition.x}
        y={tooltipPosition.y}
        visible={tooltipOpen}
      />
    </>
  );
}
