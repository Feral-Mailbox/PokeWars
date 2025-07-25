// tests/components/UnitIdleSprite.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { waitFor } from '@testing-library/react';
import UnitIdleSprite from '@/components/units/UnitIdleSprite';

vi.mock('@/components/utils/UnitIdleSprite', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    fileExistsSilently: vi.fn().mockResolvedValue(true),
  };
});

describe('UnitIdleSprite', () => {
  const originalFetch = global.fetch;
  const mockImageInstance = { onload: vi.fn(), complete: true } as unknown as HTMLImageElement;

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
    // Assert it is NOT styled as the wrapped version
    expect(canvas.style.position).not.toBe("absolute");
  });

  it('invokes onFrameSize callback with correct values', async () => {
    const onFrameSize = vi.fn();

    render(<UnitIdleSprite assetFolder="077_pikachu" onFrameSize={onFrameSize} />);

    // Force next animation frame to flush layout
    await new Promise((resolve) => requestAnimationFrame(resolve));

    // Wait until the callback is fired
    await waitFor(() => {
      expect(onFrameSize).toHaveBeenCalledWith([24, 48]);
    }, { timeout: 1000 });
  });
});
