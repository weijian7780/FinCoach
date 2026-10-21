import { MaterialIcons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image as NativeImage, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { authFont } from '@/constants/auth-theme';
import { containImageBounds } from '@/lib/receipt-image-edit';

type Props = { uri: string; originalUri?: string; visible: boolean; onClose: () => void };

export function ReceiptImageViewer({ uri, originalUri, visible, onClose }: Props) {
  const insets = useSafeAreaInsets();
  const [zoom, setZoom] = useState(1);
  const [showOriginal, setShowOriginal] = useState(false);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [error, setError] = useState(false);
  const selectedUri = showOriginal && originalUri ? originalUri : uri;
  useEffect(() => {
    if (!visible) return;
    let active = true;
    setZoom(1); setSize({ width: 0, height: 0 }); setError(false);
    NativeImage.getSize(selectedUri, (width, height) => { if (active) setSize({ width, height }); },
      () => { if (active) setError(true); });
    return () => { active = false; };
  }, [selectedUri, visible]);
  const bounds = containImageBounds(size, viewport);

  return <Modal visible={visible} animationType="fade" onRequestClose={onClose}>
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
      <View style={styles.header}>
        <Pressable accessibilityLabel="Close receipt image" onPress={onClose} style={styles.button}><MaterialIcons name="close" size={25} color="white" /></Pressable>
        <Text style={styles.title}>{showOriginal ? 'Original photo' : 'Receipt image'}</Text><View style={styles.button} />
      </View>
      <View style={styles.body} onLayout={(event) => setViewport(event.nativeEvent.layout)}>
        {bounds.width > 0 ? <ScrollView nestedScrollEnabled contentContainerStyle={{ minHeight: viewport.height, justifyContent: 'center' }}>
          <ScrollView horizontal nestedScrollEnabled contentContainerStyle={{ minWidth: viewport.width, justifyContent: 'center', alignItems: 'center' }}>
            <Image source={{ uri: selectedUri }} contentFit="contain" style={{ width: bounds.width * zoom, height: bounds.height * zoom }} />
          </ScrollView>
        </ScrollView> : error ? <Text style={styles.text}>Could not open this image.</Text> : <ActivityIndicator color="white" />}
      </View>
      <View style={styles.controls}>
        <Pressable accessibilityLabel="Zoom out receipt" disabled={zoom <= 1} onPress={() => setZoom((current) => Math.max(1, current - .5))} style={styles.button}><MaterialIcons name="remove" size={25} color="white" /></Pressable>
        <Text style={styles.text}>{Math.round(zoom * 100)}%</Text>
        <Pressable accessibilityLabel="Zoom in receipt" disabled={zoom >= 4} onPress={() => setZoom((current) => Math.min(4, current + .5))} style={styles.button}><MaterialIcons name="add" size={25} color="white" /></Pressable>
        {originalUri && originalUri !== uri ? <Pressable onPress={() => setShowOriginal((current) => !current)} style={styles.original}><Text style={styles.text}>{showOriginal ? 'Prepared receipt' : 'Original photo'}</Text></Pressable> : null}
      </View>
      <Text style={styles.hint}>Zoom in, then scroll to check the printed fields.</Text>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#11111A' },
  header: { minHeight: 60, paddingHorizontal: 16, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: 'white', fontFamily: authFont.bold, fontSize: 19 },
  body: { flex: 1, minHeight: 0, justifyContent: 'center', alignItems: 'stretch' },
  button: { minWidth: 44, minHeight: 44, justifyContent: 'center', alignItems: 'center' },
  controls: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', padding: 10, gap: 8 },
  text: { color: 'white', fontFamily: authFont.semibold, textAlign: 'center', fontSize: 14 },
  original: { padding: 12, borderRadius: 20, backgroundColor: 'rgba(255,255,255,.12)' },
  hint: { color: 'rgba(255,255,255,.7)', fontFamily: authFont.regular, fontSize: 12, textAlign: 'center', paddingBottom: 16 },
});
