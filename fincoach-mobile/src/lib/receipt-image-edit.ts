export type ImageSize = { width: number; height: number };
export type ImagePoint = { x: number; y: number };
export type CropSelection = { left: number; top: number; width: number; height: number };

export const FULL_RECEIPT_CROP: CropSelection = { left: 0, top: 0, width: 1, height: 1 };
const clamp = (value: number) => Math.max(0, Math.min(1, value));

export function containImageBounds(image: ImageSize, viewport: ImageSize): CropSelection {
  if (image.width <= 0 || image.height <= 0 || viewport.width <= 0 || viewport.height <= 0) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }
  const scale = Math.min(viewport.width / image.width, viewport.height / image.height);
  const width = image.width * scale;
  const height = image.height * scale;
  return { left: (viewport.width - width) / 2, top: (viewport.height - height) / 2, width, height };
}

export function pointOnImage(point: ImagePoint, bounds: CropSelection): ImagePoint {
  return { x: clamp((point.x - bounds.left) / bounds.width), y: clamp((point.y - bounds.top) / bounds.height) };
}

export function cropFromDrag(start: ImagePoint, end: ImagePoint): CropSelection | null {
  const left = clamp(Math.min(start.x, end.x));
  const top = clamp(Math.min(start.y, end.y));
  const width = clamp(Math.max(start.x, end.x)) - left;
  const height = clamp(Math.max(start.y, end.y)) - top;
  // Ignore taps and very small gestures rather than accidentally uploading a
  // few pixels of the receipt. The selection can be drawn in either direction.
  return width >= .015 && height >= .015 ? { left, top, width, height } : null;
}

export function cropPixels(selection: CropSelection, image: ImageSize) {
  if (![image.width, image.height, ...Object.values(selection)].every(Number.isFinite)
      || image.width < 1 || image.height < 1) throw new Error('Receipt dimensions are unavailable.');
  // The preview is letterboxed. Convert its normalized image coordinates, not
  // the surrounding modal coordinates, and clamp all native crop arguments.
  const originX = Math.min(image.width - 1, Math.round(clamp(selection.left) * image.width));
  const originY = Math.min(image.height - 1, Math.round(clamp(selection.top) * image.height));
  const right = Math.max(originX + 1, Math.round(clamp(selection.left + selection.width) * image.width));
  const bottom = Math.max(originY + 1, Math.round(clamp(selection.top + selection.height) * image.height));
  return { originX, originY, width: Math.min(image.width, right) - originX, height: Math.min(image.height, bottom) - originY };
}
