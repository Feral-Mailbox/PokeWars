import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getAssetBase,
  getMasterBallUrl,
  getPokeballUrl,
  getTilesetManifestUrl,
  getTilesetUrl,
  getTmMachineUrl,
  moveTypeToTmAssetKey,
  POKEBALL_SOURCE_SIZE,
  TM_SOURCE_SIZE,
} from "@/utils/gameAssets";

describe("gameAssets", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("exposes shared sprite sizes", () => {
    expect(TM_SOURCE_SIZE).toBe(48);
    expect(POKEBALL_SOURCE_SIZE).toBe(TM_SOURCE_SIZE);
  });

  it("normalizes relative asset bases against window origin", () => {
    vi.stubEnv("VITE_ASSET_BASE", "assets");
    expect(getAssetBase()).toBe(`${window.location.origin}/assets`);
  });

  it("strips trailing slashes from absolute asset bases", () => {
    vi.stubEnv("VITE_ASSET_BASE", "https://cdn.example.com/game/");
    expect(getAssetBase()).toBe("https://cdn.example.com/game");
  });

  it("builds tileset and object URLs", () => {
    vi.stubEnv("VITE_ASSET_BASE", "/game-assets");
    const base = getAssetBase();
    expect(getTilesetUrl("Brick City.png")).toBe(
      `${base}/tilesets/${encodeURIComponent("Brick City.png")}`
    );
    expect(getTilesetManifestUrl()).toBe(`${base}/tilesets/manifest.json`);
    expect(moveTypeToTmAssetKey(" fire ")).toBe("FIRE");
    expect(getTmMachineUrl("water")).toBe(`${base}/objects/tms/machine_WATER.png`);
    expect(getPokeballUrl()).toBe(`${base}/objects/pokeballs/POKEBALL.png`);
    expect(getMasterBallUrl()).toBe(`${base}/objects/pokeballs/MASTERBALL.png`);
  });
});
