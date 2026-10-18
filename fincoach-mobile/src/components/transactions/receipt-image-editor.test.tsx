import { act, create, type ReactTestRenderer } from 'react-test-renderer';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { ReceiptImageEditor } from './receipt-image-editor';

const native = vi.hoisted(() => ({
  getSize: vi.fn(), manipulate: vi.fn(), render: vi.fn(), rotate: vi.fn(), crop: vi.fn(),
  screen: { width: 360, height: 640 },
}));

vi.mock('@expo/vector-icons', () => ({ MaterialIcons: 'Icon' }));
vi.mock('expo-image', () => ({ Image: 'Image' }));
vi.mock('expo-image-manipulator', () => ({
  ImageManipulator: { manipulate: native.manipulate }, SaveFormat: { JPEG: 'jpeg' },
}));
vi.mock('react-native', () => ({
  ActivityIndicator: 'ActivityIndicator', Modal: 'Modal', Pressable: 'Pressable',
  ScrollView: 'ScrollView', View: 'View',
  Image: { getSize: native.getSize },
  PanResponder: { create: (handlers: object) => ({ panHandlers: handlers }) },
  StyleSheet: { create: (styles: object) => styles, absoluteFill: { position: 'absolute', inset: 0 } },
  useWindowDimensions: () => native.screen,
}));
vi.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 24, bottom: 24 }),
}));
vi.mock('@/components/ui/app-text', () => ({ AppText: 'Text' }));

let tree: ReactTestRenderer;
const onApply = vi.fn();
const image = { uri: 'original.jpg', mimeType: 'image/jpeg', fileName: 'receipt.jpg' };

function button(label: string) {
  return tree.root.findAllByType('Pressable' as never).find((node) =>
    node.props.accessibilityLabel === label || node.findAllByType('Text' as never)
      .some((text) => text.children.join('') === label))!;
}

function reference(width: number, height: number, uri: string) {
  return { width, height, saveAsync: vi.fn().mockResolvedValue({ width, height, uri }) };
}

async function mount() {
  await act(async () => { tree = create(<ReceiptImageEditor image={image} onApply={onApply} onClose={vi.fn()} />); });
}

beforeEach(() => {
  vi.clearAllMocks();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  native.getSize.mockImplementation((_uri, success) => success(1200, 1600));
  const context = { rotate: native.rotate, crop: native.crop, renderAsync: native.render };
  native.manipulate.mockReturnValue(context);
  native.rotate.mockReturnValue(context);
  native.crop.mockReturnValue(context);
});

afterEach(async () => { if (tree) await act(async () => tree.unmount()); });

describe('receipt editor native-coordinate contract', () => {
  test('rotate then drag crops the selected pixels using the new dimensions', async () => {
    await mount();
    native.render.mockResolvedValueOnce(reference(1600, 1200, 'rotated.jpg'));
    await act(async () => { await button('Rotate right').props.onPress(); });
    // Rotated dimensions come from saveAsync, not an independent stale lookup.
    expect(native.getSize).toHaveBeenCalledTimes(1);
    let viewport = tree.root.findByProps({ testID: 'receipt-crop-viewport' });
    await act(async () => viewport.props.onLayout({ nativeEvent: { layout: { width: 320, height: 400 } } }));
    viewport = tree.root.findByProps({ testID: 'receipt-crop-viewport' });
    await act(async () => viewport.props.onPanResponderGrant({ nativeEvent: { locationX: 32, locationY: 104 } }));
    expect(tree.root.findByType('ScrollView' as never).props.scrollEnabled).toBe(false);
    // Simulate a changed native event target: its local coordinates are wrong,
    // but PanResponder displacement still describes the correct finger path.
    await act(async () => viewport.props.onPanResponderMove(
      { nativeEvent: { locationX: 3, locationY: 4 } }, { dx: 256, dy: 192 }));
    await act(async () => viewport.props.onPanResponderRelease());
    expect(tree.root.findByType('ScrollView' as never).props.scrollEnabled).toBe(true);
    const decoded = reference(1600, 1200, 'rotated.jpg');
    native.render.mockResolvedValueOnce(decoded).mockResolvedValueOnce(reference(1280, 960, 'cropped.jpg'));
    await act(async () => { await button('Use selected receipt').props.onPress(); });
    expect(native.manipulate).toHaveBeenLastCalledWith(decoded);
    expect(native.crop).toHaveBeenCalledWith({ originX: 160, originY: 120, width: 1280, height: 960 });
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
      uri: 'cropped.jpg', width: 1280, height: 960, originalUri: 'original.jpg',
      transforms: [{ kind: 'rotate', degrees: 90 }, { kind: 'crop', originX: 160, originY: 120, width: 1280, height: 960 }],
    }));
  });

  test('final crop uses decoded pixels even when initial metadata dimensions differ', async () => {
    await mount();
    // EXIF-aware native decode can differ from the size metadata used to load.
    native.render.mockResolvedValueOnce(reference(1600, 1200, 'decoded.jpg'))
      .mockResolvedValueOnce(reference(1600, 1200, 'prepared.jpg'));
    await act(async () => { await button('Use selected receipt').props.onPress(); });
    expect(native.crop).toHaveBeenCalledWith({ originX: 0, originY: 0, width: 1600, height: 1200 });
  });

  test('confirmation remains outside scrolling content on a short screen', async () => {
    await mount();
    const scroller = tree.root.findByType('ScrollView' as never);
    expect(scroller.findAllByType('Pressable' as never)).not.toContain(button('Use selected receipt'));
    await act(async () => scroller.props.onLayout({ nativeEvent: { layout: { height: 360 } } }));
    const viewport = tree.root.findByProps({ testID: 'receipt-crop-viewport' });
    const previewStyle = viewport.props.style[1];
    expect(previewStyle.height).toBeLessThanOrEqual(360 - 222);
  });
});
