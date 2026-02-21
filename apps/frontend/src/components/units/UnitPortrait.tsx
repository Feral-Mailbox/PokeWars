import React, { useEffect, useState } from "react";

interface UnitPortraitProps {
  assetFolder: string;
  size?: number;
}

export default function UnitPortrait({ assetFolder, size = 40 }: UnitPortraitProps) {
  const [src, setSrc] = useState("");

  useEffect(() => {
    const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
    const normalizedBase = assetBase.startsWith("http")
      ? assetBase
      : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
    const base = normalizedBase.replace(/\/$/, "");
    const basePath = `${base}/units/${assetFolder}/portraits/portrait.png`;
    const malePath = `${base}/units/${assetFolder}/portraits/male/portrait.png`;

    const testImage = (url: string): Promise<boolean> =>
      new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(true);
        img.onerror = () => resolve(false);
        img.src = url;
      });

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

  const style: React.CSSProperties = {
    width: size,
    height: size,
    objectFit: "none",
    imageRendering: "pixelated",
    objectPosition: "left top",
  };

  return src ? (
    <img src={src} alt="Unit Portrait" style={style} />
  ) : (
    <div style={{ ...style, backgroundColor: "#222" }} />
  );
}
