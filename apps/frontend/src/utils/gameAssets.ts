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
