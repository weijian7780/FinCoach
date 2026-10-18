import { MaterialIcons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText as Text } from '@/components/ui/app-text';
import { ReceiptImageEditor } from '@/components/transactions/receipt-image-editor';
import { appDialog } from '@/components/ui/app-dialog';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { extractReceipt, setReceiptDraft, type ReceiptImageDraft } from '@/lib/receipt-ocr';

const READY_HINT = 'Align the receipt clearly before taking the photo';

export default function ScanReceiptScreen() {
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const { session } = useAuth();
  const cameraRef = useRef<CameraView>(null);
  const requestedPermission = useRef(false);
  const [permission, requestPermission] = useCameraPermissions();
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [capturedImage, setCapturedImage] = useState<ReceiptImageDraft | null>(null);
  const [editingImage, setEditingImage] = useState(false);
  const [isFocused, setIsFocused] = useState(true);
  const [torchEnabled, setTorchEnabled] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [status, setStatus] = useState(READY_HINT);

  useFocusEffect(
    useCallback(() => {
      setIsFocused(true);
      return () => setIsFocused(false);
    }, []),
  );

  useEffect(() => {
    if (permission && !permission.granted && permission.canAskAgain && !requestedPermission.current) {
      requestedPermission.current = true;
      void requestPermission();
    }
  }, [permission, requestPermission]);

  // Reserve room for the new preparation control on short phones rather than
  // letting the preview extend underneath the header or capture buttons.
  const maxFrameHeight = Math.max(120, height - insets.top - insets.bottom - (capturedImage ? 340 : 270));
  const frameWidth = Math.max(100, Math.min(width - 60, 340, maxFrameHeight * 0.72));

  async function processImage(image: ReceiptImageDraft) {
    if (!session?.access_token || processing) return;
    setProcessing(true);
    setStatus('Checking receipt text…');
    try {
      const extraction = await extractReceipt(image, session.access_token);
      setReceiptDraft(image, extraction);
      router.push('/transactions/review' as never);
    } catch (caught) {
      appDialog.open('Receipt could not be read', caught instanceof Error ? caught.message : 'Try another photo or enter it manually.');
      setStatus('Receipt was not clear. Retake it or try this photo again.');
    } finally {
      setProcessing(false);
    }
  }

  async function takePhoto() {
    if (!cameraReady || processing || !cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.85 });
      if (!photo?.uri) throw new Error('The camera did not return a photo.');
      setTorchEnabled(false);
      setCapturedImage({ uri: photo.uri, width: photo.width, height: photo.height, fileName: `receipt-${Date.now()}.jpg`, mimeType: 'image/jpeg' });
      setStatus('Check that the receipt is sharp and fully visible.');
    } catch (caught) {
      appDialog.open('Photo could not be taken', caught instanceof Error ? caught.message : 'Please try again.');
    }
  }

  async function chooseFromGallery() {
    if (processing) return;
    const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permissionResult.granted) {
      appDialog.open('Permission needed', 'Allow photo access to choose a receipt image.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.85, allowsEditing: false });
    if (result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    setCapturedImage({
      uri: asset.uri,
      width: asset.width,
      height: asset.height,
      fileName: asset.fileName ?? `receipt-${Date.now()}.jpg`,
      mimeType: asset.mimeType ?? 'image/jpeg',
    });
    setStatus('Check that the receipt is sharp and fully visible.');
  }

  function retakePhoto() {
    setCapturedImage(null);
    setStatus(READY_HINT);
    setCameraError(null);
    setCameraReady(false);
  }

  const permissionDenied = permission && !permission.granted;
  const cameraVisible = isFocused && permission?.granted && !capturedImage;

  return (
    <View style={{ flex: 1, backgroundColor: '#11111A', paddingTop: insets.top }}>
      <View style={header}>
        <Pressable accessibilityLabel="Close receipt scanner" onPress={() => router.back()} style={iconButton}>
          <MaterialIcons name="close" size={27} color="white" />
        </Pressable>
        <Text style={title}>Scan Receipt</Text>
        <Pressable
          accessibilityLabel={torchEnabled ? 'Turn flash off' : 'Turn flash on'}
          disabled={!cameraVisible || processing}
          onPress={() => setTorchEnabled((enabled) => !enabled)}
          style={[iconButton, (!cameraVisible || processing) && { opacity: 0.35 }]}
        >
          <MaterialIcons name={torchEnabled ? 'flash-on' : 'flash-off'} size={25} color="white" />
        </Pressable>
      </View>

      <View style={frameArea}>
        <View style={[frame, { width: frameWidth }]}>
          {cameraVisible ? (
            <CameraView
              ref={cameraRef}
              enableTorch={torchEnabled}
              facing="back"
              mode="picture"
              onCameraReady={() => {
                setCameraReady(true);
                setCameraError(null);
              }}
              onMountError={(event) => {
                setCameraReady(false);
                setCameraError(event.message);
              }}
              style={StyleSheet.absoluteFill}
            />
          ) : null}
          {capturedImage ? <Image key={capturedImage.uri} contentFit="contain" contentPosition="center"
            source={{ uri: capturedImage.uri }} style={[StyleSheet.absoluteFill, { width: '100%', height: '100%' }]} /> : null}
          {!permission && !capturedImage ? <ActivityIndicator color="white" size="large" /> : null}
          {permissionDenied && !capturedImage ? (
            <View style={emptyState}>
              <MaterialIcons name="no-photography" size={48} color="rgba(255,255,255,0.72)" />
              <Text style={emptyTitle}>Camera access is required</Text>
              <Text style={emptyBody}>FinCoach uses the camera only when you scan a receipt.</Text>
              <Pressable onPress={() => void (permission.canAskAgain ? requestPermission() : Linking.openSettings())} style={permissionButton}>
                <Text style={permissionButtonText}>Grant camera access</Text>
              </Pressable>
            </View>
          ) : null}
          {cameraError && !capturedImage ? (
            <View style={emptyState}>
              <MaterialIcons name="camera-alt" size={48} color="rgba(255,255,255,0.72)" />
              <Text style={emptyTitle}>Camera unavailable</Text>
              <Text style={emptyBody}>{cameraError}</Text>
            </View>
          ) : null}
          {processing ? (
            <View style={processingOverlay}>
              <ActivityIndicator color="white" size="large" />
              <Text style={processingText}>Reading receipt…</Text>
            </View>
          ) : null}
          <Corner position="tl" />
          <Corner position="tr" />
          <Corner position="bl" />
          <Corner position="br" />
        </View>
        <Text style={hint}>{status}</Text>
        {capturedImage ? <Pressable accessibilityLabel="Crop or rotate receipt" disabled={processing}
          onPress={() => setEditingImage(true)} style={prepareButton}>
          <MaterialIcons name="crop-rotate" size={22} color="white" /><Text style={prepareText}>Crop / rotate</Text>
        </Pressable> : null}
      </View>
      {editingImage && capturedImage ? <ReceiptImageEditor image={capturedImage} onClose={() => setEditingImage(false)}
        onApply={(prepared) => { setCapturedImage(prepared); setEditingImage(false); setStatus('Check that the merchant, date and final payment are included.'); }} /> : null}

      <View style={[controls, { paddingBottom: Math.max(insets.bottom + 22, 30) }]}>
        <Pressable
          accessibilityLabel={capturedImage ? 'Retake receipt photo' : 'Choose receipt from gallery'}
          disabled={processing}
          onPress={capturedImage ? retakePhoto : () => void chooseFromGallery()}
          style={[sideButton, processing && { opacity: 0.5 }]}
        >
          <MaterialIcons name={capturedImage ? 'refresh' : 'photo-library'} size={25} color="white" />
        </Pressable>
        <Pressable
          accessibilityLabel={capturedImage ? 'Use receipt photo' : 'Take receipt photo'}
          disabled={processing || (!capturedImage && (!cameraReady || !permission?.granted))}
          onPress={capturedImage ? () => void processImage(capturedImage) : () => void takePhoto()}
          style={[capture, (processing || (!capturedImage && (!cameraReady || !permission?.granted))) && { opacity: 0.55 }]}
        >
          {processing ? <ActivityIndicator color={authColors.primary} /> : <MaterialIcons name={capturedImage ? 'check' : 'photo-camera'} size={31} color={authColors.primary} />}
        </Pressable>
        <Pressable
          accessibilityLabel="Enter transaction manually"
          disabled={processing}
          onPress={() => router.replace('/transactions/manage' as never)}
          style={[sideButton, processing && { opacity: 0.5 }]}
        >
          <MaterialIcons name="edit" size={25} color="white" />
        </Pressable>
      </View>
    </View>
  );
}

function Corner({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) {
  return <View pointerEvents="none" style={[corner, position.includes('t') ? { top: 0, borderTopWidth: 4 } : { bottom: 0, borderBottomWidth: 4 }, position.includes('l') ? { left: 0, borderLeftWidth: 4 } : { right: 0, borderRightWidth: 4 }]} />;
}
const header = { height: 62, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const;
const iconButton = { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' } as const;
const title = { fontSize: 20, fontFamily: authFont.bold, color: 'white' } as const;
const frameArea = { flex: 1, minHeight: 0, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 30 } as const;
const frame = { maxWidth: 340, aspectRatio: 0.72, borderRadius: 20, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.07)', alignItems: 'center', justifyContent: 'center' } as const;
const corner = { position: 'absolute', width: 42, height: 42, borderColor: 'white', zIndex: 4 } as const;
const hint = { marginTop: 18, textAlign: 'center', fontSize: 14, fontFamily: authFont.semibold, color: 'white' } as const;
const prepareButton = { marginTop: 12, minHeight: 44, paddingHorizontal: 18, borderRadius: 24, backgroundColor: 'rgba(255,255,255,.12)', flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center' } as const;
const prepareText = { fontSize: 14, fontFamily: authFont.semibold, color: 'white' } as const;
const controls = { paddingTop: 14, paddingHorizontal: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' } as const;
const sideButton = { width: 52, height: 52, borderRadius: 26, backgroundColor: 'rgba(255,255,255,0.12)', alignItems: 'center', justifyContent: 'center' } as const;
const capture = { width: 76, height: 76, borderRadius: 38, borderWidth: 5, borderColor: 'rgba(255,255,255,0.45)', backgroundColor: 'white', alignItems: 'center', justifyContent: 'center' } as const;
const emptyState = { paddingHorizontal: 26, alignItems: 'center', gap: 10, zIndex: 2 } as const;
const emptyTitle = { fontSize: 17, fontFamily: authFont.bold, color: 'white', textAlign: 'center' } as const;
const emptyBody = { fontSize: 13, lineHeight: 19, fontFamily: authFont.regular, color: 'rgba(255,255,255,0.72)', textAlign: 'center' } as const;
const permissionButton = { marginTop: 4, borderRadius: 22, paddingHorizontal: 18, paddingVertical: 11, backgroundColor: authColors.primary } as const;
const permissionButtonText = { fontSize: 13, fontFamily: authFont.bold, color: 'white' } as const;
const processingOverlay = { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 3, alignItems: 'center', justifyContent: 'center', gap: 12, backgroundColor: 'rgba(17,17,26,0.78)' } as const;
const processingText = { fontSize: 14, fontFamily: authFont.semibold, color: 'white' } as const;
