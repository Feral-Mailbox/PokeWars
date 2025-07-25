import '@testing-library/jest-dom';

beforeAll(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    value: vi.fn(() => {
      return {
        clearRect: vi.fn(),
        drawImage: vi.fn(),
        getImageData: vi.fn(() => ({
          data: new Uint8ClampedArray(4 * 24 * 48), // mock transparent pixels
        })),
      };
    }),
  });
});
