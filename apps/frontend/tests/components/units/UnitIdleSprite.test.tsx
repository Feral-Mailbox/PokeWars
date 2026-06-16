// tests/components/UnitIdleSprite.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import UnitIdleSprite from '@/components/units/UnitIdleSprite';

describe('UnitIdleSprite', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
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
});
