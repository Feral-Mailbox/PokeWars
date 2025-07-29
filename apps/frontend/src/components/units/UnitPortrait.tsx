import React, { useEffect, useState } from "react";

interface UnitPortraitProps {
  assetFolder: string;
  size?: number;
}

export default function UnitPortrait({ assetFolder, size = 40 }: UnitPortraitProps) {
  const [src, setSrc] = useState("");

  useEffect(() => {
    const origin = window.location.origin.replace(":5173", "");
    const basePath = `${origin}/assets/units/${assetFolder}/portraits/portrait.png`;
    const malePath = `${origin}/assets/units/${assetFolder}/portraits/male/portrait.png`;

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
