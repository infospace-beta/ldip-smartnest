// Shared geometry keeps the circular preview and saved square crop identical.
export function profileCrop(width: number, height: number, zoom: number, x: number, y: number) {
  const side = Math.min(width, height) / Math.max(1, zoom);
  const left = (width - side) * (Math.max(-1, Math.min(1, x)) + 1) / 2;
  const top = (height - side) * (Math.max(-1, Math.min(1, y)) + 1) / 2;
  return { left, top, side };
}
