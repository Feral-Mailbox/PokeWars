// tests/components/UnitIdleSprite.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import UnitIdleSprite, { clearUnitSpriteCaches } from '@/components/units/UnitIdleSprite';

describe('UnitIdleSprite', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    clearUnitSpriteCaches();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(`
        <Anims>
          <Anim>
            <Name>Idle</Name>
            <FrameWidth>24</FrameWidth>
            <FrameHeight>48</FrameHeight>
            <Duration>10</Duration>
          </Anim>
        </Anims>
      `),
    }) as any;

    vi.stubGlobal("Image", class {
      onload: () => void = () => {};
      onerror: () => void = () => {};
      crossOrigin = '';
      naturalWidth = 24;
      complete = false;
      set src(_val: string) {
        this.complete = true;
        this.onload();
      }
    } as any);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('renders canvas inside a div if isMapPlacement is true', async () => {
    render(<UnitIdleSprite assetFolder="077_pikachu" isMapPlacement />);
    const canvas = await screen.findByTitle(/Idle|Walk/i);
    expect(canvas.tagName).toBe('CANVAS');
    expect(canvas.parentElement?.tagName).toBe('DIV');
  });

  it('renders canvas directly if isMapPlacement is false', async () => {
    render(<UnitIdleSprite assetFolder="077_pikachu" />);
    const canvas = await screen.findByTitle(/Idle|Walk/i);
    expect(canvas.tagName).toBe('CANVAS');
    expect(canvas.style.position).not.toBe("absolute");
  });

  it('invokes onFrameSize callback with correct values', async () => {
    const onFrameSize = vi.fn();

    render(<UnitIdleSprite assetFolder="077_pikachu" onFrameSize={onFrameSize} />);

    await waitFor(() => {
      expect(onFrameSize).toHaveBeenCalledWith([24, 48]);
    }, { timeout: 1000 });
  });

  it('loads sprites when the browser image is already cached', async () => {
    vi.stubGlobal("Image", class {
      onload: () => void = () => {};
      onerror: () => void = () => {};
      crossOrigin = '';
      naturalWidth = 24;
      complete = true;
      set src(_val: string) {
        // Cached images can be complete before onload is assigned.
      }
    } as any);

    render(<UnitIdleSprite assetFolder="141_cobalion" isMapPlacement />);

    await waitFor(() => {
      expect(screen.getByTitle(/Idle|Walk/i)).toBeTruthy();
    }, { timeout: 1000 });
  });

  it('handles sprite image load errors', async () => {
    vi.stubGlobal("Image", class {
      onload: () => void = () => {};
      onerror: () => void = () => {};
      crossOrigin = '';
      naturalWidth = 0;
      complete = false;
      set src(_val: string) {
        queueMicrotask(() => this.onerror());
      }
    } as any);

    render(<UnitIdleSprite assetFolder="missing_unit" isMapPlacement />);

    await waitFor(() => {
      expect(screen.getByTitle(/Idle|Walk/i)).toBeTruthy();
    });
  });

  it('draws an outline overlay when outlineOnly is set', async () => {
    const fillRect = vi.fn();
    const getContext = vi.fn(() => ({
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
      getImageData: vi.fn(() => ({
        data: (() => {
          const data = new Uint8ClampedArray(24 * 48 * 4);
          for (let i = 0; i < data.length; i += 4) {
            data[i] = 10;
            data[i + 1] = 10;
            data[i + 2] = 10;
            data[i + 3] = 255;
          }
          // Transparent pixel in the middle creates interior edges.
          const mid = ((24 * 24) + 12) * 4;
          data[mid + 3] = 0;
          return data;
        })(),
      })),
      putImageData: vi.fn(),
      fillRect,
      fillStyle: "",
      imageSmoothingEnabled: true,
    }));
    HTMLCanvasElement.prototype.getContext = getContext as any;

    render(
      <UnitIdleSprite
        assetFolder="077_pikachu"
        isMapPlacement
        outlineOnly
        overlayColor="#ff0000"
      />,
    );

    await waitFor(() => {
      expect(fillRect).toHaveBeenCalled();
    }, { timeout: 2000 });
  });

  it('falls back to Walk anim and applies solid overlay color', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(`
        <Anims>
          <Anim>
            <Name>Walk</Name>
            <FrameWidth>24</FrameWidth>
            <FrameHeight>48</FrameHeight>
            <Duration>5</Duration>
            <Duration>5</Duration>
          </Anim>
        </Anims>
      `),
    }) as any;

    const drawImage = vi.fn();
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      clearRect: vi.fn(),
      drawImage,
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(24 * 48 * 4) })),
      putImageData: vi.fn(),
      fillRect: vi.fn(),
      fillStyle: "",
      imageSmoothingEnabled: true,
    })) as any;

    render(
      <UnitIdleSprite assetFolder="077_pikachu" overlayColor="#00ff00" />,
    );

    await waitFor(() => {
      expect(screen.getByTitle("Walk")).toBeTruthy();
    });
  });

  it('handles failed anim fetch and male path fallback', async () => {
    let imageCalls = 0;
    vi.stubGlobal("Image", class {
      onload: () => void = () => {};
      onerror: () => void = () => {};
      crossOrigin = '';
      naturalWidth = 0;
      complete = false;
      set src(val: string) {
        imageCalls += 1;
        // First Idle-Anim existence check fails; later male path succeeds.
        if (String(val).includes('/male/')) {
          this.naturalWidth = 24;
          this.complete = true;
          queueMicrotask(() => this.onload());
        } else {
          this.complete = true;
          queueMicrotask(() => this.onerror());
        }
      }
    } as any);

    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes('/male/')) {
        return {
          ok: true,
          text: async () => `
            <Anims>
              <Anim>
                <Name>Idle</Name>
                <FrameWidth>24</FrameWidth>
                <FrameHeight>48</FrameHeight>
                <Duration>10</Duration>
              </Anim>
            </Anims>
          `,
        };
      }
      return { ok: false, text: async () => "" };
    }) as any;

    render(<UnitIdleSprite assetFolder="077_pikachu" isMapPlacement />);
    await waitFor(() => {
      expect(imageCalls).toBeGreaterThan(1);
      expect(screen.getByTitle(/Idle|Walk/i)).toBeTruthy();
    }, { timeout: 2000 });
  });
});
