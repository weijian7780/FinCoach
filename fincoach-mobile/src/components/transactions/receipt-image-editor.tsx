import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image as NativeImage, Modal, PanResponder, Pressable, ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { containImageBounds, cropFromDrag, cropPixels, FULL_RECEIPT_CROP, pointOnImage, type CropSelection, type ImagePoint } from '@/lib/receipt-image-edit';
import type { ReceiptImageDraft } from '@/lib/receipt-ocr';

type Props = { image: ReceiptImageDraft; onApply: (image: ReceiptImageDraft) => void; onClose: () => void };

export function ReceiptImageEditor({ image, onApply, onClose }: Props) {
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const [uri, setUri] = useState(image.uri);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [selection, setSelection] = useState<CropSelection>(FULL_RECEIPT_CROP);
  const [transforms, setTransforms] = useState(image.transforms ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const anchor = useRef<ImagePoint | null>(null);
  const bounds = containImageBounds(size, viewport);
  const interaction = useRef({ bounds, busy });
  interaction.current = { bounds, busy };

  useEffect(() => {
    let active = true;
    setSize({ width: 0, height: 0 });
    NativeImage.getSize(uri, (width, height) => {
      if (active) setSize({ width, height });
    }, () => { if (active) setError('Could not open this receipt image.'); });
    return () => { active = false; };
  }, [uri]);

  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => !interaction.current.busy && interaction.current.bounds.width > 0,
    onMoveShouldSetPanResponder: () => !interaction.current.busy,
    onPanResponderGrant: (event) => {
      const { locationX, locationY } = event.nativeEvent;
      anchor.current = pointOnImage({ x: locationX, y: locationY }, interaction.current.bounds);
    },
    onPanResponderMove: (event) => {
      if (!anchor.current) return;
      const { locationX, locationY } = event.nativeEvent;
      const crop = cropFromDrag(anchor.current, pointOnImage({ x: locationX, y: locationY }, interaction.current.bounds));
      if (crop) setSelection(crop);
    },
    onPanResponderRelease: () => { anchor.current = null; },
    onPanResponderTerminate: () => { anchor.current = null; },
  }), []);

  async function rotate(degrees: number) {
    if (busy || !size.width) return;
    setBusy(true); setError(null);
    try {
      // Transform real local pixels; rotating the preview alone would still
      // upload the original sideways image to OCR.
      const context = ImageManipulator.manipulate(uri).rotate(degrees);
      const rendered = await context.renderAsync();
      const result = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: .95 });
      setUri(result.uri);
      setSelection(FULL_RECEIPT_CROP);
      setTransforms((current) => [...current, { kind: 'rotate', degrees }]);
    } catch { setError('Could not rotate the receipt. Try another photo.'); }
    finally { setBusy(false); }
  }

  async function apply() {
    if (busy || !size.width) return;
    setBusy(true); setError(null);
    try {
      const crop = cropPixels(selection, size);
      const context = ImageManipulator.manipulate(uri).crop(crop);
      const rendered = await context.renderAsync();
      const result = await rendered.saveAsync({ format: SaveFormat.JPEG, compress: .95 });
      onApply({ ...image, uri: result.uri, mimeType: 'image/jpeg', fileName: 'prepared-receipt.jpg',
        width: result.width, height: result.height,
        originalUri: image.originalUri ?? image.uri,
        originalMimeType: image.originalMimeType ?? image.mimeType,
        transforms: [...transforms, { kind: 'crop', ...crop }] });
    } catch { setError('Could not prepare the selected area. Try selecting it again.'); }
    finally { setBusy(false); }
  }

  return <Modal visible animationType="slide" onRequestClose={() => { if (!busy) onClose(); }}>
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
      <View style={styles.header}>
        <Pressable disabled={busy} accessibilityLabel="Close receipt editor" onPress={onClose} style={styles.icon}><MaterialIcons name="close" size={26} color="white" /></Pressable>
        <Text style={styles.title}>Prepare receipt</Text><View style={styles.icon} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.hint}>Rotate first, then drag a rectangle around one receipt.</Text>
        <View {...responder.panHandlers} onLayout={(event) => setViewport(event.nativeEvent.layout)}
          style={[styles.preview, { height: Math.max(200, Math.min(460, window.height * .5)) }]}>
          <Image pointerEvents="none" source={{ uri }} contentFit="contain" style={StyleSheet.absoluteFill} />
          {bounds.width > 0 ? <View pointerEvents="none" style={[styles.selection, {
            left: bounds.left + selection.left * bounds.width, top: bounds.top + selection.top * bounds.height,
            width: selection.width * bounds.width, height: selection.height * bounds.height,
          }]} /> : <ActivityIndicator color="white" />}
        </View>
        <View style={styles.tools}>
          <Tool label="Rotate left" icon="rotate-left" disabled={busy || !size.width} onPress={() => void rotate(-90)} />
          <Tool label="Rotate right" icon="rotate-right" disabled={busy || !size.width} onPress={() => void rotate(90)} />
          <Tool label="Full image" icon="crop-free" disabled={busy} onPress={() => setSelection(FULL_RECEIPT_CROP)} />
        </View>
        <Pressable disabled={busy} onPress={() => { setUri(image.originalUri ?? image.uri); setTransforms([]); setSelection(FULL_RECEIPT_CROP); setError(null); }}><Text style={styles.reset}>Reset edits</Text></Pressable>
        <Text style={styles.hint}>Include the merchant, date, items and final payment. Leave camera watermarks and other receipts outside the selection.</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable disabled={busy || !size.width} style={[styles.apply, (busy || !size.width) && { opacity: .55 }]} onPress={() => void apply()}>
          {busy ? <ActivityIndicator color="white" /> : <MaterialIcons name="check" color="white" size={22} />}<Text style={styles.applyText}>Use selected receipt</Text>
        </Pressable>
      </ScrollView>
    </View>
  </Modal>;
}

function Tool({ label, icon, disabled, onPress }: { label: string; icon: keyof typeof MaterialIcons.glyphMap; disabled: boolean; onPress: () => void }) {
  return <Pressable accessibilityLabel={label} disabled={disabled} onPress={onPress} style={[styles.tool, disabled && { opacity: .5 }]}>
    <MaterialIcons name={icon} color="white" size={25} /><Text style={styles.toolText}>{label}</Text>
  </Pressable>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#11111A' },
  header: { minHeight: 60, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  icon: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  title: { color: 'white', fontFamily: authFont.bold, fontSize: 20 },
  content: { padding: 16, gap: 16, paddingBottom: 28 },
  hint: { color: 'rgba(255,255,255,.85)', fontFamily: authFont.regular, fontSize: 14, textAlign: 'center', lineHeight: 21 },
  preview: { width: '100%', backgroundColor: '#25252E', justifyContent: 'center', alignItems: 'center', overflow: 'hidden', borderRadius: 14 },
  selection: { position: 'absolute', borderColor: '#C7C2FF', borderWidth: 3, backgroundColor: 'rgba(92,80,225,.08)' },
  tools: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10 },
  tool: { padding: 12, minWidth: 90, alignItems: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,.1)', borderRadius: 14 },
  toolText: { color: 'white', fontFamily: authFont.semibold, fontSize: 12 },
  reset: { color: '#C7C2FF', fontFamily: authFont.semibold, textAlign: 'center', padding: 8 },
  error: { color: '#FFB4AB', fontFamily: authFont.regular, textAlign: 'center' },
  apply: { minHeight: 54, backgroundColor: authColors.primary, borderRadius: 27, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 },
  applyText: { color: 'white', fontFamily: authFont.bold, fontSize: 15 },
});
