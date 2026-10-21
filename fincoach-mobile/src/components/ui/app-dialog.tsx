import { MaterialIcons } from '@expo/vector-icons';
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AnimatedPressable } from '@/components/ui/animated-pressable';
import { authColors, authFont } from '@/constants/auth-theme';
import {
  appDialogReducer,
  canDismissAppDialog,
  initialAppDialogState,
  type AppDialogButton,
  type AppDialogOptions,
  type AppDialogRequest,
  type AppDialogTone,
} from '@/lib/app-dialog-state';

type AlertOptions = Pick<AppDialogOptions, 'title' | 'message' | 'tone' | 'actionLabel'>;
type ConfirmOptions = Pick<AppDialogOptions, 'title' | 'message' | 'tone' | 'confirmLabel' | 'cancelLabel'>;
type AppDialogApi = {
  alert: (options: AlertOptions) => Promise<void>;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
};

type NativeAlertButton = { text?: string; style?: 'default' | 'cancel' | 'destructive'; onPress?: () => void };
type NativeAlertOptions = { cancelable?: boolean; onDismiss?: () => void };
type OpenDialog = (kind: AppDialogRequest['kind'], options: AppDialogOptions) => Promise<boolean>;

const AppDialogContext = createContext<AppDialogApi | null>(null);
let globalOpenDialog: OpenDialog | null = null;

function inferTone(title: string, buttons: AppDialogButton[]): AppDialogTone {
  if (buttons.some((button) => button.role === 'destructive')) return 'destructive';
  if (/completed|saved|ready|success/i.test(title)) return 'success';
  if (/permission|check |retry|rescan|too large|synchron/i.test(title)) return 'warning';
  if (/failed|could not|blocked|unavailable|cannot|error/i.test(title)) return 'error';
  return 'info';
}

export const appDialog = {
  open(
    title: string,
    message?: string,
    nativeButtons: NativeAlertButton[] = [{ text: 'OK' }],
    nativeOptions: NativeAlertOptions = {},
  ) {
    const buttons: AppDialogButton[] = nativeButtons.map((button) => ({
      label: button.text ?? 'OK',
      role: button.style ?? 'default',
      onPress: button.onPress,
    }));
    return globalOpenDialog?.('custom', {
      title,
      message,
      buttons,
      tone: inferTone(title, buttons),
      cancelable: nativeOptions.cancelable,
      onDismiss: nativeOptions.onDismiss,
    }) ?? Promise.resolve(false);
  },
};

const toneStyle = {
  info: { color: authColors.primary, background: authColors.primaryFixed, icon: 'info-outline' },
  success: { color: '#067647', background: '#D1FADF', icon: 'check-circle-outline' },
  warning: { color: '#8A4B00', background: '#FFF1D6', icon: 'warning-amber' },
  error: { color: authColors.error, background: '#FFDAD6', icon: 'error-outline' },
  destructive: { color: authColors.error, background: '#FFDAD6', icon: 'delete-outline' },
} as const;

export function AppDialogProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(appDialogReducer, initialAppDialogState);
  const nextId = useRef(1);

  const openDialog = useCallback<OpenDialog>((kind, options) => new Promise((resolve) => {
    dispatch({ type: 'enqueue', request: { id: nextId.current++, kind, options, resolve } });
  }), []);

  useEffect(() => {
    globalOpenDialog = openDialog;
    return () => { if (globalOpenDialog === openDialog) globalOpenDialog = null; };
  }, [openDialog]);

  const showAlert = useCallback(async (options: AlertOptions) => {
    await openDialog('alert', options);
  }, [openDialog]);
  const showConfirm = useCallback((options: ConfirmOptions) => openDialog('confirm', options), [openDialog]);
  const api = useMemo(() => ({ alert: showAlert, confirm: showConfirm }), [showAlert, showConfirm]);

  const request = state.active;
  const finish = useCallback((value: boolean, button?: AppDialogButton) => {
    if (!request) return;
    request.resolve(value);
    dispatch({ type: 'advance' });
    void button?.onPress?.();
  }, [request]);

  const dismiss = useCallback(() => {
    if (!request) return;
    const cancel = request.options.buttons?.find((button) => button.role === 'cancel');
    if (!canDismissAppDialog(request)) return;
    request.options.onDismiss?.();
    finish(false, cancel);
  }, [finish, request]);

  const buttons = request
    ? request.options.buttons ?? (request.kind === 'confirm'
      ? [
          { label: request.options.cancelLabel ?? 'Cancel', role: 'cancel' as const },
          {
            label: request.options.confirmLabel ?? 'Continue',
            role: request.options.tone === 'destructive' ? 'destructive' as const : 'default' as const,
          },
        ]
      : [{ label: request.options.actionLabel ?? 'OK', role: 'default' as const }])
    : [];
  const tone = request?.options.tone ?? 'info';
  const appearance = toneStyle[tone];

  return (
    <AppDialogContext.Provider value={api}>
      {children}
      <Modal
        animationType="fade"
        transparent
        statusBarTranslucent
        visible={Boolean(request)}
        onRequestClose={dismiss}
      >
        <View style={styles.overlay} accessibilityViewIsModal>
          <Pressable accessibilityLabel="Dismiss dialog" onPress={dismiss} style={StyleSheet.absoluteFill} />
          {request ? (
            <View accessibilityRole="alert" style={styles.card}>
              <View style={[styles.iconBadge, { backgroundColor: appearance.background }]}>
                <MaterialIcons name={appearance.icon} size={29} color={appearance.color} />
              </View>
              <Text selectable style={styles.title}>{request.options.title}</Text>
              {request.options.message ? (
                <ScrollView style={styles.messageScroll} contentContainerStyle={styles.messageContent}>
                  <Text selectable style={styles.message}>{request.options.message}</Text>
                </ScrollView>
              ) : null}
              <View style={styles.actions}>
                {buttons.map((button, index) => {
                  const destructive = button.role === 'destructive';
                  const secondary = button.role === 'cancel' || (buttons.length > 1 && index === 0);
                  return (
                    <AnimatedPressable
                      key={`${button.label}-${index}`}
                      accessibilityRole="button"
                      onPress={() => finish(button.role !== 'cancel', button)}
                      style={[
                        styles.button,
                        secondary ? styles.secondaryButton : styles.primaryButton,
                        destructive && styles.destructiveButton,
                      ]}
                    >
                      <Text style={[styles.buttonLabel, secondary ? styles.secondaryLabel : styles.primaryLabel]}>
                        {button.label}
                      </Text>
                    </AnimatedPressable>
                  );
                })}
              </View>
            </View>
          ) : null}
        </View>
      </Modal>
    </AppDialogContext.Provider>
  );
}

export function useAppDialog(): AppDialogApi {
  const value = useContext(AppDialogContext);
  if (!value) throw new Error('useAppDialog must be used within AppDialogProvider.');
  return value;
}

const styles = StyleSheet.create({
  overlay: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 20, backgroundColor: 'rgba(15, 15, 30, 0.48)' },
  card: { width: '100%', maxWidth: 380, maxHeight: '82%', alignItems: 'center', padding: 24, borderRadius: 32, backgroundColor: authColors.surfaceContainerLowest, boxShadow: '0 16px 48px rgba(15, 15, 30, 0.24)' },
  iconBadge: { width: 58, height: 58, borderRadius: 29, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  title: { fontFamily: authFont.bold, fontSize: 22, lineHeight: 28, textAlign: 'center', color: authColors.onSurface },
  messageScroll: { flexShrink: 1, marginTop: 10 },
  messageContent: { paddingHorizontal: 2 },
  message: { fontFamily: authFont.regular, fontSize: 15, lineHeight: 22, textAlign: 'center', color: authColors.onSurfaceVariant },
  actions: { width: '100%', gap: 10, marginTop: 22 },
  button: { minHeight: 52, alignItems: 'center', justifyContent: 'center', borderRadius: 16, paddingHorizontal: 18 },
  primaryButton: { backgroundColor: authColors.primary },
  destructiveButton: { backgroundColor: authColors.error },
  secondaryButton: { backgroundColor: authColors.surfaceContainerHigh },
  buttonLabel: { fontFamily: authFont.semibold, fontSize: 16 },
  primaryLabel: { color: authColors.onPrimary },
  secondaryLabel: { color: authColors.onSurface },
});
