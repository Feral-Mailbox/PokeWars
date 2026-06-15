import { useEffect, useState } from "react";
import { computeMapDisplayScale, getMapDisplayMaxSize } from "@/utils/mapPointer";

export function useMapDisplayScale(logicalWidth: number, logicalHeight: number): number {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const update = () => {
      const { maxWidth, maxHeight } = getMapDisplayMaxSize();
      setScale(computeMapDisplayScale(logicalWidth, logicalHeight, maxWidth, maxHeight));
    };

    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [logicalWidth, logicalHeight]);

  return scale;
}
