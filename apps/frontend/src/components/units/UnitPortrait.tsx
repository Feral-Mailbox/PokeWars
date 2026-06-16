import React, { useEffect, useState } from "react";

interface UnitPortraitProps {
  assetFolder: string;
  size?: number;
  frameX?: number;
  frameY?: number;
}

export default function UnitPortrait({ assetFolder, size = 40, frameX = 0, frameY = 0 }: UnitPortraitProps) {
  const [src, setSrc] = useState("");
  const [naturalWidth, setNaturalWidth] = useState(0);
  const [naturalHeight, setNaturalHeight] = useState(0);

  useEffect(() => {
    const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
    const normalizedBase = assetBase.startsWith("http")
      ? assetBase
      : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
    const base = normalizedBase.replace(/\/$/, "");
    const basePath = `${base}/units/${assetFolder}/portraits/portrait.png`;
    const malePath = `${base}/units/${assetFolder}/portraits/male/portrait.png`;

    const testImage = (url: string): Promise<boolean> => {
      return new Promise((resolve) => {
        const img = new Image();
        let settled = false;
        const finish = (ok: boolean) => {
          if (settled) return;
          settled = true;
          resolve(ok);
        };

        img.onload = () => finish(true);
        img.onerror = () => finish(false);
        img.src = url;

        if (img.complete) {
          finish(img.naturalWidth > 0);
        }
      });
    };

    const loadPortrait = async () => {
      const baseExists = await testImage(basePath);
      if (baseExists) {
        setSrc(basePath);
      } else {
        const maleExists = await testImage(malePath);
        if (maleExists) {
          setSrc(malePath);
        } else {
          setSrc("");
        }
      }
    };

    loadPortrait();
  }, [assetFolder]);

  const canUseRequestedFrame =
    naturalWidth >= frameX + size &&
    naturalHeight >= frameY + size;
  const objectPosition = canUseRequestedFrame ? `-${frameX}px -${frameY}px` : "left top";

  const style: React.CSSProperties = {
    width: size,
    height: size,
    objectFit: "none",
    imageRendering: "pixelated",
    objectPosition,
  };

  return src ? (
    <img
      src={src}
      alt="Unit Portrait"
      style={style}
      onLoad={(e) => {
        const img = e.currentTarget as HTMLImageElement;
        setNaturalWidth(img.naturalWidth || 0);
        setNaturalHeight(img.naturalHeight || 0);
      }}
    />
  ) : (
    <div style={{ ...style, backgroundColor: "#222" }} />
  );
}
