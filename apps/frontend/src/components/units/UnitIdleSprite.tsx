import { useEffect, useRef, useState } from "react";

interface UnitIdleSpriteProps {
  assetFolder: string;
}

export default function UnitIdleSprite({ assetFolder }: UnitIdleSpriteProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [durations, setDurations] = useState<number[]>([]);
  const [frameSize, setFrameSize] = useState<[number, number]>([24, 48]);
  const [animName, setAnimName] = useState<"Idle" | "Walk">("Idle");

  useEffect(() => {
    const loadAnimFromPath = async (spritePath: string, isFinalAttempt = false): Promise<boolean> => {
      const xmlUrl = `${spritePath}/AnimData.xml`;

      try {
        const fileCheckUrl = `${spritePath}/Idle-Anim.png`; // use image to test path

        const exists = await fileExistsSilently(fileCheckUrl);
        if (!exists) return false;

        const res = await fetch(`${spritePath}/AnimData.xml`, { mode: "cors" });
        if (!res.ok) return false;


        const text = await res.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, "application/xml");
        const anims = xml.getElementsByTagName("Anims")[0];
        if (!anims) return false;

        const animElements = Array.from(anims.getElementsByTagName("Anim"));
        let selected = animElements.find(a => a.querySelector("Name")?.textContent?.trim() === "Idle");
        let fallback = false;

        if (!selected) {
          selected = animElements.find(a => a.querySelector("Name")?.textContent?.trim() === "Walk");
          fallback = true;
        }

        if (!selected) return false;

        const fw = parseInt(selected.querySelector("FrameWidth")?.textContent || "24");
        const fh = parseInt(selected.querySelector("FrameHeight")?.textContent || "48");
        const ds = Array.from(selected.getElementsByTagName("Duration")).map(d =>
          parseInt(d.textContent || "10")
        );

        setFrameSize([fw, fh]);
        setDurations(ds);
        setAnimName(fallback ? "Walk" : "Idle");

        const img = new Image();
        img.src = `${spritePath}/${fallback ? "Walk-Anim.png" : "Idle-Anim.png"}`;
        img.onload = () => setImage(img);
        img.onerror = () => {
          if (isFinalAttempt) {
            console.error(`❌ Failed to load sprite sheet: ${img.src}`);
          }
        };

        return true;
      } catch {
        return false;
      }
    };

    const fileExistsSilently = (url: string): Promise<boolean> => {
        return new Promise(resolve => {
            const img = new Image();
            img.src = url;
            img.onload = () => resolve(true);
            img.onerror = () => resolve(false); // no log, silent fail
        });
    };


    const loadAssets = async () => {
      const origin = window.location.origin.replace(":5173", "");
      const basePath = `${origin}/assets/units/${assetFolder}/sprites`;
      const malePath = `${origin}/assets/units/${assetFolder}/sprites/male`;

      const baseSuccess = await loadAnimFromPath(basePath);
      if (!baseSuccess) {
        await loadAnimFromPath(malePath, true);
      }
    };

    loadAssets();
  }, [assetFolder]);

  useEffect(() => {
    if (!image || durations.length === 0) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let frameIndex = 0;
    let tick = 0;
    const [fw, fh] = frameSize;

    const animate = () => {
      ctx.clearRect(0, 0, fw, fh);
      ctx.drawImage(image, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);

      tick++;
      if (tick >= durations[frameIndex]) {
        tick = 0;
        frameIndex = (frameIndex + 1) % durations.length;
      }

      requestAnimationFrame(animate);
    };

    animate();
  }, [image, durations, frameSize]);

  return (
    <canvas
      ref={canvasRef}
      width={frameSize[0]}
      height={frameSize[1]}
      style={{ imageRendering: "pixelated" }}
      title={animName}
    />
  );
}
