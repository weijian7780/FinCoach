import { describe, expect, test } from 'vitest';

import { containImageBounds, cropFromDrag, cropPixels, pointOnImage } from './receipt-image-edit';

describe('receipt selection maps preview coordinates to real image pixels', () => {
  test('portrait receipt is centred inside a wider preview', () => {
    const bounds = containImageBounds({ width: 100, height: 200 }, { width: 300, height: 300 });
    expect(bounds).toEqual({ left: 75, top: 0, width: 150, height: 300 });
    expect(pointOnImage({ x: 150, y: 150 }, bounds)).toEqual({ x: .5, y: .5 });
    expect(pointOnImage({ x: 0, y: 0 }, bounds)).toEqual({ x: 0, y: 0 });
  });

  test('reversed drag selects the same region and crop stays in bounds', () => {
    const crop = cropFromDrag({ x: .8, y: .9 }, { x: .2, y: .1 })!;
    expect(cropPixels(crop, { width: 1000, height: 2000 })).toEqual({ originX: 200, originY: 200, width: 600, height: 1600 });
    expect(cropPixels({ left: -.1, top: -.2, width: 2, height: 2 }, { width: 1000, height: 2000 })).toEqual({ originX: 0, originY: 0, width: 1000, height: 2000 });
  });

  test('actual upright receipt coordinates retain full height', () => {
    const crop = { left: 275 / 1159, top: 0, width: 525 / 1159, height: 1 };
    expect(cropPixels(crop, { width: 1159, height: 1545 })).toEqual({ originX: 275, originY: 0, width: 525, height: 1545 });
  });

  test('a tap cannot accidentally reduce the image to a tiny crop', () => {
    expect(cropFromDrag({ x: .5, y: .5 }, { x: .501, y: .501 })).toBeNull();
    expect(() => cropPixels({ left: 0, top: 0, width: 1, height: 1 }, { width: 0, height: 200 })).toThrow();
  });
});
