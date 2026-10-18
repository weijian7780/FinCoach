import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, test } from 'vitest';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...parts: string[]) => readFileSync(join(root, ...parts), 'utf8');

describe('receipt scanner live camera', () => {
  test('renders an embedded camera and captures without opening the system camera', () => {
    const source = read('src', 'app', 'transactions', 'scan.tsx');

    expect(source).toContain("from 'expo-camera'");
    expect(source).toContain('<CameraView');
    expect(source).toContain('useCameraPermissions');
    expect(source).toContain('takePictureAsync');
    expect(source).toContain('onCameraReady');
    expect(source).not.toContain('launchCameraAsync');
  });

  test('keeps flash, gallery, manual entry, and permission recovery controls', () => {
    const source = read('src', 'app', 'transactions', 'scan.tsx');

    expect(source).toContain('enableTorch');
    expect(source).toContain('flash-on');
    expect(source).toContain('launchImageLibraryAsync');
    expect(source).toContain('Grant camera access');
    expect(source).toContain("'/transactions/manage'");
  });

  test('registers the SDK camera package and Android permission', () => {
    const packageJson = JSON.parse(read('package.json')) as { dependencies: Record<string, string> };
    const appJson = read('app.json');
    const manifest = read('android', 'app', 'src', 'main', 'AndroidManifest.xml');

    expect(packageJson.dependencies['expo-camera']).toBe('~56.0.8');
    expect(appJson).toContain('"expo-camera"');
    expect(manifest).toContain('android.permission.CAMERA');
  });
});
