import '@testing-library/jest-dom';

function createMockCanvasContext() {
  return {
    canvas: document.createElement('canvas'),
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    setTransform: vi.fn(),
    scale: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    beginPath: vi.fn(),
    closePath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    strokeText: vi.fn(),
    setLineDash: vi.fn(),
    getLineDash: vi.fn(() => []),
    arc: vi.fn(),
    rect: vi.fn(),
    clip: vi.fn(),
    getImageData: vi.fn(() => ({
      data: new Uint8ClampedArray(4 * 24 * 48),
      width: 24,
      height: 48,
    })),
    putImageData: vi.fn(),
    createImageData: vi.fn(() => ({
      data: new Uint8ClampedArray(4 * 24 * 48),
      width: 24,
      height: 48,
    })),
    measureText: vi.fn(() => ({ width: 0 })),
    fillStyle: '#000',
    strokeStyle: '#000',
    lineWidth: 1,
    font: '10px sans-serif',
    textBaseline: 'alphabetic',
    textAlign: 'start',
    globalAlpha: 1,
    globalCompositeOperation: 'source-over',
    set imageSmoothingEnabled(_value: boolean) {},
    get imageSmoothingEnabled() {
      return false;
    },
  };
}

beforeAll(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn(() => createMockCanvasContext()),
  });
});
