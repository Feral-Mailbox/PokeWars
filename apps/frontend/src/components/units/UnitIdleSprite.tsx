import { useEffect, useRef, useState } from "react";

interface UnitIdleSpriteProps {
  assetFolder: string;
  onFrameSize?: (size: [number, number]) => void;
  isMapPlacement?: boolean;
}

export default function UnitIdleSprite({
  assetFolder,
  onFrameSize,
  isMapPlacement,
}: UnitIdleSpriteProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [spriteImage, setSpriteImage] = useState<HTMLImageElement | null>(null);
  const [shadowImage, setShadowImage] = useState<HTMLImageElement | null>(null);
  const [durations, setDurations] = useState<number[]>([]);
  const [frameSize, setFrameSize] = useState<[number, number]>([24, 48]);
  const [animName, setAnimName] = useState<"Idle" | "Walk">("Idle");
  const verticalShiftRef = useRef<number>(0);

  const SPRITE_SCALE = 1.33;
  const CANVAS_PADDING_BOTTOM = 20;

  useEffect(() => {
    const loadAnimFromPath = async (spritePath: string, isFinalAttempt = false) => {
      const exists = await fileExistsSilently(`${spritePath}/Idle-Anim.png`);
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
      const ds = Array.from(selected.getElementsByTagName("Duration")).map((d) =>
        parseInt(d.textContent || "10")
      );

      setFrameSize([fw, fh]);
      if (onFrameSize) onFrameSize([fw, fh]);
      setDurations(ds);
      setAnimName(fallback ? "Walk" : "Idle");

      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = `${spritePath}/${fallback ? "Walk-Anim.png" : "Idle-Anim.png"}`;
      img.onload = () => setSpriteImage(img);

      if (isMapPlacement) {
        const shadowImg = new Image();
        shadowImg.crossOrigin = "anonymous";
        shadowImg.src = `${spritePath}/Idle-Shadow.png`;
        shadowImg.onload = () => {
          setShadowImage(shadowImg);
          computeVerticalShift(shadowImg, fw, fh);
        };
      }

      return true;
    };

    const fileExistsSilently = (url: string): Promise<boolean> =>
      new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(true);
        img.onerror = () => resolve(false);
        img.src = url;
      });

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

  const computeVerticalShift = (img: HTMLImageElement, fw: number, fh: number) => {
    const canvas = document.createElement("canvas");
    canvas.width = fw;
    canvas.height = fh;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, fw, fh).data;

    let lastVisibleY = 0;
    for (let y = fh - 1; y >= 0; y--) {
      for (let x = 0; x < fw; x++) {
        if (data[(y * fw + x) * 4 + 3] > 0) {
          lastVisibleY = y;
          break;
        }
      }
      if (lastVisibleY > 0) break;
    }

    verticalShiftRef.current = fh - lastVisibleY - 1;
  };

  useEffect(() => {
    let animationFrameId: number;
    let frameIndex = 0;
    let tick = 0;

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !spriteImage || durations.length === 0) return;

    const [fw, fh] = frameSize;
    canvas.width = fw;
    canvas.height = fh;

    const draw = () => {
      const shift = verticalShiftRef.current;

      ctx.clearRect(0, 0, fw, fh);
      ctx.save();
      ctx.translate(0, shift);

      if (isMapPlacement && shadowImage) {
        ctx.drawImage(shadowImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);
      }

      ctx.drawImage(spriteImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);

      ctx.restore();

      tick++;
      if (tick >= durations[frameIndex]) {
        tick = 0;
        frameIndex = (frameIndex + 1) % durations.length;
      }

      animationFrameId = requestAnimationFrame(draw);
    };

    const maybeStart = () => {
      frameIndex = 0;
      tick = 0;
      draw();
    };

    if (spriteImage.complete) {
      maybeStart();
    } else {
      spriteImage.onload = () => maybeStart();
    }

    return () => cancelAnimationFrame(animationFrameId);
  }, [spriteImage, shadowImage, durations, frameSize, isMapPlacement]);

  const [fw, fh] = frameSize;

  return isMapPlacement ? (
    <div
      style={{
        width: "32px",
        height: `${32 + CANVAS_PADDING_BOTTOM}px`,
        position: "relative",
        pointerEvents: "none",
        overflow: "visible",
      }}
    >
      <canvas
        ref={canvasRef}
        width={fw}
        height={fh}
        title={animName}
        style={{
          position: "absolute",
          bottom: `${CANVAS_PADDING_BOTTOM}px`,
          left: "50%",
          transform: `translateX(-50%) scale(${SPRITE_SCALE})`,
          transformOrigin: "bottom center",
          imageRendering: "pixelated",
          pointerEvents: "none",
        }}
      />
    </div>
  ) : (
    <canvas
      ref={canvasRef}
      width={fw}
      height={fh}
      title={animName}
      style={{
        imageRendering: "pixelated",
        pointerEvents: "none",
      }}
    />
  );
}
