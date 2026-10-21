export type AppDialogTone = 'info' | 'success' | 'warning' | 'error' | 'destructive';

export type AppDialogButton = {
  label: string;
  role?: 'default' | 'cancel' | 'destructive';
  onPress?: () => void | Promise<void>;
};

export type AppDialogOptions = {
  title: string;
  message?: string;
  tone?: AppDialogTone;
  actionLabel?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  buttons?: AppDialogButton[];
  cancelable?: boolean;
  onDismiss?: () => void;
};

export type AppDialogRequest = {
  id: number;
  kind: 'alert' | 'confirm' | 'custom';
  options: AppDialogOptions;
  resolve: (value: boolean) => void;
};

export type AppDialogState = {
  active: AppDialogRequest | null;
  pending: AppDialogRequest[];
};

export const initialAppDialogState: AppDialogState = { active: null, pending: [] };

export type AppDialogAction =
  | { type: 'enqueue'; request: AppDialogRequest }
  | { type: 'advance' };

export function appDialogReducer(state: AppDialogState, action: AppDialogAction): AppDialogState {
  if (action.type === 'enqueue') {
    if (!state.active) return { active: action.request, pending: [] };
    return { ...state, pending: [...state.pending, action.request] };
  }
  const [active = null, ...pending] = state.pending;
  return { active, pending };
}

export function canDismissAppDialog(request: AppDialogRequest): boolean {
  if (request.kind === 'alert' || request.kind === 'confirm') return true;
  const buttons = request.options.buttons ?? [];
  return request.options.cancelable === true
    || buttons.length <= 1
    || buttons.some((button) => button.role === 'cancel');
}
