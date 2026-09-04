import { useEffect, useRef, useState } from "react";
import { applyOpaquePixelOverlay } from "@/utils/spriteOverlay";

interface UnitIdleSpriteProps {
  assetFolder: string;
  onFrameSize?: (size: [number, number]) => void;
  isMapPlacement?: boolean;
  overlayColor?: string;
  outlineOnly?: boolean;
}

const imageCache = new Map<string, Promise<HTMLImageElement | null>>();
const xmlCache = new Map<string, Promise<string | null>>();

/** Test helper: drop cached sprite/XML promises between cases. */
export function clearUnitSpriteCaches(): void {
  imageCache.clear();
  xmlCache.clear();
}

function loadImageElement(url: string, crossOrigin = true): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    if (crossOrigin) {
      img.crossOrigin = "anonymous";
    }

    let settled = false;
    const finish = (result: HTMLImageElement | null) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    img.onload = () => finish(img);
    img.onerror = () => finish(null);
    img.src = url;

    if (img.complete) {
      finish(img.naturalWidth > 0 ? img : null);
    }
  });
}

function loadImageCached(url: string): Promise<HTMLImageElement | null> {
  let pending = imageCache.get(url);
  if (!pending) {
    pending = loadImageElement(url).then((img) => {
      if (!img) imageCache.delete(url);
      return img;
    });
    imageCache.set(url, pending);
  }
  return pending;
}

async function fetchAnimXmlCached(url: string): Promise<string | null> {
  let pending = xmlCache.get(url);
  if (!pending) {
    pending = (async () => {
      try {
        const res = await fetch(url, { mode: "cors" });
        if (!res.ok) {
          xmlCache.delete(url);
          return null;
        }
        return await res.text();
      } catch {
        xmlCache.delete(url);
        return null;
      }
    })();
    xmlCache.set(url, pending);
  }
  return pending;
}

function computeVerticalShiftFromImage(img: HTMLImageElement, fw: number, fh: number): number {
  const canvas = document.createElement("canvas");
  canvas.width = fw;
  canvas.height = fh;
  const ctx = canvas.getContext("2d");
  if (!ctx) return 0;
  ctx.drawImage(img, 0, 0, fw, fh, 0, 0, fw, fh);
  const data = ctx.getImageData(0, 0, fw, fh).data;

  let lastVisibleY = -1;
  for (let y = fh - 1; y >= 0; y--) {
    for (let x = 0; x < fw; x++) {
      if (data[(y * fw + x) * 4 + 3] > 0) {
        lastVisibleY = y;
        break;
      }
    }
    if (lastVisibleY >= 0) break;
  }

  if (lastVisibleY < 0) return 0;
  return Math.max(0, fh - lastVisibleY - 1);
}

export default function UnitIdleSprite({
  assetFolder,
  onFrameSize,
  isMapPlacement,
  overlayColor,
  outlineOnly = false,
}: UnitIdleSpriteProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const onFrameSizeRef = useRef(onFrameSize);
  onFrameSizeRef.current = onFrameSize;

  const [spriteImage, setSpriteImage] = useState<HTMLImageElement | null>(null);
  const [shadowImage, setShadowImage] = useState<HTMLImageElement | null>(null);
  const [durations, setDurations] = useState<number[]>([]);
  const [frameSize, setFrameSize] = useState<[number, number]>([24, 48]);
  const [animName, setAnimName] = useState<"Idle" | "Walk">("Idle");
  const [assetsReady, setAssetsReady] = useState(false);
  const verticalShiftRef = useRef<number>(0);

  const SPRITE_SCALE = 1.33;
  const CANVAS_PADDING_BOTTOM = 20;

  const drawSpriteOutline = (
    ctx: CanvasRenderingContext2D,
    data: Uint8ClampedArray,
    fw: number,
    fh: number,
    shift: number,
    color: string
  ) => {
    ctx.fillStyle = color;
    for (let y = 0; y < fh; y++) {
      for (let x = 0; x < fw; x++) {
        const i = (y * fw + x) * 4;
        if (data[i + 3] <= 0) continue;

        const isEdge =
          x === 0 ||
          y === 0 ||
          x === fw - 1 ||
          y === fh - 1 ||
          data[i - 4 + 3] === 0 ||
          data[i + 4 + 3] === 0 ||
          data[i - fw * 4 + 3] === 0 ||
          data[i + fw * 4 + 3] === 0;

        if (isEdge) {
          ctx.fillRect(x, y + shift, 1, 1);
        }
      }
    }
  };

  useEffect(() => {
    let cancelled = false;

    const loadAnimFromPath = async (spritePath: string) => {
      const idleImg = await loadImageCached(`${spritePath}/Idle-Anim.png`);
      const xmlText = await fetchAnimXmlCached(`${spritePath}/AnimData.xml`);
      if (!xmlText) return false;

      const parser = new DOMParser();
      const xml = parser.parseFromString(xmlText, "application/xml");
      const anims = xml.getElementsByTagName("Anims")[0];
      if (!anims) return false;

      const animElements = Array.from(anims.getElementsByTagName("Anim"));
      let selected = idleImg
        ? animElements.find((a) => a.querySelector("Name")?.textContent?.trim() === "Idle")
        : undefined;
      let useWalk = false;
      if (!selected) {
        selected = animElements.find(
          (a) => a.querySelector("Name")?.textContent?.trim() === "Walk"
        );
        useWalk = true;
      }
      if (!selected) return false;

      const spriteImg = useWalk
        ? await loadImageCached(`${spritePath}/Walk-Anim.png`)
        : idleImg;
      if (!spriteImg) return false;

      const fw = parseInt(selected.querySelector("FrameWidth")?.textContent || "24", 10);
      const fh = parseInt(selected.querySelector("FrameHeight")?.textContent || "48", 10);
      const ds = Array.from(selected.getElementsByTagName("Duration")).map((d) =>
        parseInt(d.textContent || "10", 10)
      );

      if (cancelled) return false;

      let shadowImg: HTMLImageElement | null = null;
      let shift = 0;
      if (isMapPlacement) {
        shadowImg = await loadImageCached(`${spritePath}/Idle-Shadow.png`);
        if (shadowImg) {
          shift = computeVerticalShiftFromImage(shadowImg, fw, fh);
        }
      }

      if (cancelled) return false;

      // Apply footprint shift before first paint so sprites don't pop down a few pixels.
      verticalShiftRef.current = shift;
      setFrameSize([fw, fh]);
      onFrameSizeRef.current?.([fw, fh]);
      setDurations(ds.length > 0 ? ds : [10]);
      setAnimName(useWalk ? "Walk" : "Idle");
      setShadowImage(shadowImg);
      setSpriteImage(spriteImg);
      setAssetsReady(true);
      return true;
    };

    const loadAssets = async () => {
      setSpriteImage(null);
      setShadowImage(null);
      setDurations([]);
      setAssetsReady(false);
      verticalShiftRef.current = 0;
      if (!assetFolder) return;

      const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
      const normalizedBase = assetBase.startsWith("http")
        ? assetBase
        : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
      const base = normalizedBase.replace(/\/$/, "");
      const basePath = `${base}/units/${assetFolder}/sprites`;
      const malePath = `${base}/units/${assetFolder}/sprites/male`;

      const baseSuccess = await loadAnimFromPath(basePath);
      if (!baseSuccess && !cancelled) {
        await loadAnimFromPath(malePath);
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, [assetFolder, isMapPlacement]);

  useEffect(() => {
    let animationFrameId: number;
    let frameIndex = 0;
    let tick = 0;

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !spriteImage || durations.length === 0 || !assetsReady) return;

    const [fw, fh] = frameSize;
    canvas.width = fw;
    canvas.height = fh;

    const draw = () => {
      const shift = verticalShiftRef.current;

      ctx.clearRect(0, 0, fw, fh);
      ctx.save();
      ctx.translate(0, shift);

      if (isMapPlacement && shadowImage && !outlineOnly) {
        ctx.drawImage(shadowImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);
      }

      if (outlineOnly && overlayColor) {
        const frameCanvas = document.createElement("canvas");
        frameCanvas.width = fw;
        frameCanvas.height = fh;
        const frameCtx = frameCanvas.getContext("2d")!;
        frameCtx.drawImage(spriteImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);
        drawSpriteOutline(ctx, frameCtx.getImageData(0, 0, fw, fh).data, fw, fh, 0, overlayColor);
      } else {
        ctx.drawImage(spriteImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);

        if (overlayColor) {
          const frameCanvas = document.createElement("canvas");
          frameCanvas.width = fw;
          frameCanvas.height = fh;
          const frameCtx = frameCanvas.getContext("2d")!;
          frameCtx.drawImage(spriteImage, frameIndex * fw, 0, fw, fh, 0, 0, fw, fh);

          const imageData = frameCtx.getImageData(0, 0, fw, fh);
          applyOpaquePixelOverlay(ctx, imageData, 0, 0, overlayColor);
        }
      }

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
  }, [
    spriteImage,
    shadowImage,
    durations,
    frameSize,
    isMapPlacement,
    overlayColor,
    outlineOnly,
    assetsReady,
  ]);

  const [fw, fh] = frameSize;

  return isMapPlacement ? (
    <div
      style={{
        width: "32px",
        height: `${32 + CANVAS_PADDING_BOTTOM}px`,
        position: "relative",
        pointerEvents: "none",
        overflow: "visible",
        visibility: assetsReady ? "visible" : "hidden",
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
