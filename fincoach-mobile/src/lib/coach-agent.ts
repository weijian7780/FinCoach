import type {
  CoachActionPayload,
  CoachChoiceOption,
  CoachChoicesPayload,
  CoachClarificationPayload,
  CoachReadClarificationPayload,
  ReportPreset,
  ReportSelection,
  ReportType,
} from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const INPUT_MODES = [
  'single_select', 'multi_select', 'date', 'date_range', 'time', 'amount', 'text',
];

function areValidOptions(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  return value.every(
    (option) =>
      isRecord(option)
      && typeof option.id === 'string'
      && typeof option.label === 'string'
      && typeof option.value === 'string',
  );
}

export function isCoachClarification(value: unknown): value is CoachClarificationPayload {
  if (!isRecord(value)) return false;
  return value.type === 'clarification'
    && (value.action_type === 'create_reminder' || value.action_type === 'generate_report')
    && typeof value.question === 'string'
    && typeof value.input_type === 'string'
    && typeof value.field === 'string'
    && Array.isArray(value.options)
    && typeof value.allow_other === 'boolean';
}

// A read question shares the clarification card but carries no write action.
// Keep it separate from isCoachAction so a read card can never render or submit
// as an executable write card.
export function isCoachReadClarification(
  value: unknown,
): value is CoachReadClarificationPayload {
  if (!isRecord(value)) return false;
  return value.type === 'read_clarification'
    && typeof value.question === 'string'
    && typeof value.input_type === 'string'
    && INPUT_MODES.includes(String(value.input_type))
    && typeof value.field === 'string'
    && areValidOptions(value.options)
    && typeof value.allow_other === 'boolean';
}

// LLM-offered choice cards: tapping one submits its `query` as a new request.
// Validated defensively so a malformed payload renders nothing rather than a
// broken card.
export function isCoachChoices(value: unknown): value is CoachChoicesPayload {
  if (!isRecord(value)) return false;
  return value.type === 'coach_choices'
    && Array.isArray(value.options)
    && value.options.length > 0
    && value.options.every(
      (option) =>
        isRecord(option)
        && typeof option.id === 'string'
        && typeof option.label === 'string'
        && option.label.trim().length > 0
        && typeof option.query === 'string'
        && option.query.trim().length > 0,
    );
}

export function isCoachAction(value: unknown): value is CoachActionPayload {
  if (!isRecord(value)) return false;
  return value.type === 'action'
    && typeof value.action_id === 'string'
    && (value.action_type === 'create_reminder' || value.action_type === 'generate_report')
    && ['pending', 'approved', 'executed', 'cancelled', 'failed'].includes(String(value.status))
    && typeof value.title === 'string'
    && isRecord(value.arguments)
    && Array.isArray(value.fields);
}

export function clarificationReply(
  option: Pick<CoachChoiceOption, 'label' | 'value'> | null,
  otherText = '',
) {
  const flexible = otherText.trim();
  if (flexible) return { content: flexible, value: flexible };
  const label = option?.label.trim();
  const value = option?.value.trim();
  return label && value ? { content: label, value } : null;
}

function presetFromAgentPeriod(period: unknown): ReportPreset {
  if (period === 'last_month') return 'previous_month';
  if (period === 'last_3_months') return 'last_3_months';
  if (period === 'custom') return 'custom';
  return 'current_month';
}

function reportType(preset: ReportPreset, hasCategory: boolean): ReportType {
  const suffix = hasCategory ? '_category' : '';
  if (preset === 'current_month' || preset === 'previous_month') {
    return `monthly${suffix}` as ReportType;
  }
  if (preset === 'last_3_months') return `multi_month${suffix}` as ReportType;
  return `custom${suffix}` as ReportType;
}

export function reportSelectionFromCoachAction(
  argumentsValue: Record<string, unknown>,
  categoryId: number | null = null,
): ReportSelection {
  const preset = presetFromAgentPeriod(argumentsValue.period);
  return {
    preset,
    reportType: reportType(preset, categoryId !== null),
    startDate: String(argumentsValue.start_date ?? ''),
    endDate: String(argumentsValue.end_date ?? ''),
    categoryId,
  };
}
