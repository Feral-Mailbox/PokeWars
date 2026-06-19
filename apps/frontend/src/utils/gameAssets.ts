export function getAssetBase(): string {
  const assetBase = import.meta.env.VITE_ASSET_BASE ?? "/game-assets";
  if (assetBase.startsWith("http")) {
    return assetBase.replace(/\/$/, "");
  }
  const normalized = assetBase.startsWith("/") ? assetBase : `/${assetBase}`;
  return `${window.location.origin}${normalized}`.replace(/\/$/, "");
}

export function getTilesetUrl(filename: string): string {
  return `${getAssetBase()}/tilesets/${encodeURIComponent(filename)}`;
}

export function getTilesetManifestUrl(): string {
  return `${getAssetBase()}/tilesets/manifest.json`;
}

/** TM machine sprites are 48×48; map tiles draw at 32×32 logical pixels. */
export const TM_SOURCE_SIZE = 48;

/** Pokeball / Master Ball map sprites use the same 48×48 source size as TM machines. */
export const POKEBALL_SOURCE_SIZE = TM_SOURCE_SIZE;

export function moveTypeToTmAssetKey(type: string): string {
  return type.trim().toUpperCase();
}

export function getTmMachineUrl(moveType: string): string {
  const key = moveTypeToTmAssetKey(moveType);
  return `${getAssetBase()}/objects/tms/machine_${key}.png`;
}

export function getPokeballUrl(): string {
  return `${getAssetBase()}/objects/pokeballs/POKEBALL.png`;
}

export function getMasterBallUrl(): string {
  return `${getAssetBase()}/objects/pokeballs/MASTERBALL.png`;
}
