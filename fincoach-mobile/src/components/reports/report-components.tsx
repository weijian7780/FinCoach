import { MaterialIcons } from '@expo/vector-icons';
import { Pressable, ScrollView, TextInput, View } from 'react-native';

import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { formatReportMoney, formatReportPeriodLabel } from '@/lib/report-domain';
import type { Category, FinancialReport, Report, ReportPreset, ReportSelection } from '@/lib/types';

type FiltersProps = {
  selection: ReportSelection;
  categories: Category[];
  onPresetChange: (value: ReportPreset) => void;
  onCategoryChange: (value: number | null) => void;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onGenerate: () => void;
  generating: boolean;
  validationError: string | null;
};

const presets: { value: ReportPreset; label: string }[] = [
  { value: 'current_month', label: 'This month' },
  { value: 'previous_month', label: 'Last month' },
  { value: 'last_3_months', label: '3 months' },
  { value: 'custom', label: 'Custom' },
];

export function ReportFilters(props: FiltersProps) {
  const { selection, categories } = props;
  return (
    <Card>
      <Heading title={formatReportPeriodLabel(selection)} icon="date-range" eyebrow="REPORT PERIOD" />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        {presets.map((item) => (
          <Chip key={item.value} label={item.label} selected={selection.preset === item.value} onPress={() => props.onPresetChange(item.value)} />
        ))}
      </ScrollView>
      {selection.preset === 'custom' ? (
        <View style={styles.dateRow}>
          <DateInput label="From" value={selection.startDate} onChangeText={props.onStartDateChange} />
          <DateInput label="To" value={selection.endDate} onChangeText={props.onEndDateChange} />
        </View>
      ) : null}
      <Text style={[styles.eyebrow, { marginTop: 14 }]}>CATEGORY</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        <Chip label="All" selected={selection.categoryId == null} onPress={() => props.onCategoryChange(null)} />
        {categories.map((item) => (
          <Chip key={item.id} label={item.name} selected={selection.categoryId === item.id} onPress={() => props.onCategoryChange(item.id)} />
        ))}
      </ScrollView>
      {props.validationError ? <Text accessibilityRole="alert" style={styles.error}>{props.validationError}</Text> : null}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Generate Report using selected filters"
        disabled={props.generating}
        onPress={props.onGenerate}
        style={({ pressed }) => [styles.primaryButton, pressed && { opacity: 0.84 }, props.generating && { opacity: 0.56 }]}
      >
        <MaterialIcons name="analytics" size={20} color={authColors.onPrimary} />
        <Text style={styles.primaryButtonText}>{props.generating ? 'Generating…' : 'Generate Report'}</Text>
      </Pressable>
    </Card>
  );
}

function DateInput({ label, value, onChangeText }: { label: string; value: string; onChangeText: (value: string) => void }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={`${label} report date in YYYY-MM-DD format`}
        value={value}
        onChangeText={onChangeText}
        placeholder="YYYY-MM-DD"
        placeholderTextColor={authColors.outline}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="numbers-and-punctuation"
        maxLength={10}
        style={styles.input}
      />
    </View>
  );
}

function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={[styles.chip, selected && styles.chipSelected]}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </Pressable>
  );
}

export function ReportDashboard({ report }: { report: FinancialReport }) {
  return (
    <>
      {report.transactionCount === 0 ? (
        <View style={styles.emptyBanner}>
          <MaterialIcons name="receipt-long" size={22} color={authColors.primary} />
          <View style={{ flex: 1 }}><Text style={styles.emptyTitle}>No transactions in this period</Text><Text style={styles.caption}>Budget and savings context still uses your saved records.</Text></View>
        </View>
      ) : null}
      <View style={styles.metricGrid}>
        <Metric label="Income" value={report.totalIncome} icon="arrow-downward" color="#067647" />
        <Metric label="Expenses" value={report.totalExpenses} icon="arrow-upward" color={authColors.error} />
        <Metric label="Net Balance" value={report.netBalance} icon="account-balance-wallet" color={report.netBalance >= 0 ? authColors.primary : authColors.error} wide />
      </View>
      <Budget report={report} />
      <Categories report={report} />
      <Trend report={report} />
      <Savings report={report} />
    </>
  );
}

function Metric({ label, value, icon, color, wide = false }: { label: string; value: number; icon: keyof typeof MaterialIcons.glyphMap; color: string; wide?: boolean }) {
  return (
    <View accessibilityLabel={`${label}: ${formatReportMoney(value)}`} style={[styles.metric, wide && { width: '100%' }]}>
      <View style={[styles.metricIcon, { backgroundColor: `${color}14` }]}><MaterialIcons name={icon} size={18} color={color} /></View>
      <Text style={styles.eyebrow}>{label.toUpperCase()}</Text>
      <Text numberOfLines={1} adjustsFontSizeToFit style={[styles.metricValue, { color }]}>{formatReportMoney(value)}</Text>
    </View>
  );
}

function Budget({ report }: { report: FinancialReport }) {
  const over = report.budget.exceeded > 0;
  return (
    <Card>
      <Heading title="Budget vs Actual" icon="donut-large" />
      {report.budget.limit <= 0 ? <Text style={styles.muted}>No overall budget is saved for this period.</Text> : <>
        <Between left="SPENT" leftValue={formatReportMoney(report.budget.spent)} right="LIMIT" rightValue={formatReportMoney(report.budget.limit)} />
        <Bar label={`Budget used ${report.budget.percentage} percent`} value={report.budget.progressPercentage} color={over ? authColors.error : authColors.primary} />
        <View style={styles.between}>
          <Text style={[styles.muted, over && { color: authColors.error }]}>{over ? `${formatReportMoney(report.budget.exceeded)} over budget` : `${formatReportMoney(report.budget.remaining)} remaining`}</Text>
          <Text style={[styles.percent, over && { color: authColors.error }]}>{report.budget.percentage}%</Text>
        </View>
      </>}
    </Card>
  );
}

function Categories({ report }: { report: FinancialReport }) {
  return (
    <Card>
      <Heading title="Spending by Category" icon="pie-chart-outline" />
      {!report.categoryTotals.length ? <Text style={styles.muted}>No expense categories to show for this selection.</Text> : report.categoryTotals.map((item) => (
        <View key={item.categoryId} accessibilityLabel={`${item.name}: ${formatReportMoney(item.amount)}, ${item.percentage} percent`} style={styles.categoryRow}>
          <View style={styles.between}><View style={styles.legend}><View style={[styles.dot, { backgroundColor: item.color ?? authColors.primary }]} /><Text style={styles.rowLabel}>{item.name}</Text></View><Text style={styles.rowValue}>{formatReportMoney(item.amount)}</Text></View>
          <Bar value={item.percentage} color={item.color ?? authColors.primary} />
          <Text style={styles.caption}>{item.percentage}% · {item.transactionCount} transaction{item.transactionCount === 1 ? '' : 's'}</Text>
        </View>
      ))}
    </Card>
  );
}

function Trend({ report }: { report: FinancialReport }) {
  const maximum = Math.max(1, ...report.trend.flatMap((item) => [item.income, item.expenses]));
  return (
    <Card>
      <Heading title="Monthly Trend" icon="bar-chart" />
      <View style={styles.trendLegend}><Legend color="#067647" label="Income" /><Legend color={authColors.primary} label="Expenses" /></View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.trendRow}>
        {report.trend.map((item) => {
          const label = new Intl.DateTimeFormat('en-MY', { month: 'short', year: '2-digit' }).format(new Date(Number(item.month.slice(0, 4)), Number(item.month.slice(5, 7)) - 1, 1));
          return (
            <View key={item.month} accessibilityLabel={`${label}: income ${formatReportMoney(item.income)}, expenses ${formatReportMoney(item.expenses)}, net ${formatReportMoney(item.net)}`} style={styles.trendColumn}>
              <View style={styles.bars}><View style={[styles.trendBar, { height: Math.max(2, item.income / maximum * 92), backgroundColor: '#067647' }]} /><View style={[styles.trendBar, { height: Math.max(2, item.expenses / maximum * 92), backgroundColor: authColors.primary }]} /></View>
              <Text style={styles.trendLabel}>{label}</Text><Text style={[styles.trendNet, item.net < 0 && { color: authColors.error }]}>{formatReportMoney(item.net)}</Text>
            </View>
          );
        })}
      </ScrollView>
    </Card>
  );
}

function Savings({ report }: { report: FinancialReport }) {
  return (
    <Card>
      <Heading title="Savings Progress" icon="savings" />
      {report.savings.target <= 0 ? <Text style={styles.muted}>No savings goals are available yet.</Text> : <>
        <View style={styles.between}><Text style={styles.amount}>{formatReportMoney(report.savings.current)}</Text><Text style={styles.muted}>of {formatReportMoney(report.savings.target)}</Text></View>
        <Bar label={`Savings progress ${report.savings.percentage} percent`} value={report.savings.progressPercentage} color="#067647" />
        <View style={styles.between}><Text style={styles.muted}>{formatReportMoney(report.savings.remaining)} remaining</Text><Text style={[styles.percent, { color: '#067647' }]}>{report.savings.percentage}%</Text></View>
      </>}
    </Card>
  );
}

export function ReportHistory({ reports, unavailable }: { reports: Report[]; unavailable: boolean }) {
  return (
    <Card>
      <Heading title="Recent Reports" icon="history" />
      {unavailable ? <Text style={styles.muted}>Report history is unavailable. Analytics can still be generated.</Text> : !reports.length ? <Text style={styles.muted}>Generate a report to start your history.</Text> : reports.map((item, index) => (
        <View key={item.id} style={[styles.historyRow, index === reports.length - 1 && { borderBottomWidth: 0 }]}>
          <View style={styles.historyIcon}><MaterialIcons name="description" size={20} color={authColors.primary} /></View>
          <View style={{ flex: 1 }}><Text style={styles.rowLabel}>{humanType(item.type)}</Text><Text style={styles.caption}>{item.period}</Text></View>
          <Text style={styles.historyDate}>{formatDate(item.generated_at)}</Text>
        </View>
      ))}
    </Card>
  );
}

function Heading({ title, icon, eyebrow }: { title: string; icon: keyof typeof MaterialIcons.glyphMap; eyebrow?: string }) {
  return <View style={styles.heading}>{<View>{eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}<Text style={styles.title}>{title}</Text></View>}<MaterialIcons name={icon} size={21} color={authColors.primary} /></View>;
}
function Card({ children }: { children: React.ReactNode }) { return <View style={styles.card}>{children}</View>; }
function Bar({ value, color, label }: { value: number; color: string; label?: string }) { return <View accessibilityLabel={label} style={styles.track}><View style={[styles.fill, { width: `${Math.min(100, Math.max(0, value))}%`, backgroundColor: color }]} /></View>; }
function Legend({ color, label }: { color: string; label: string }) { return <View style={styles.legend}><View style={[styles.dot, { backgroundColor: color }]} /><Text style={styles.caption}>{label}</Text></View>; }
function Between({ left, leftValue, right, rightValue }: { left: string; leftValue: string; right: string; rightValue: string }) { return <View style={styles.between}><View><Text style={styles.eyebrow}>{left}</Text><Text style={styles.amount}>{leftValue}</Text></View><View style={{ alignItems: 'flex-end' }}><Text style={styles.eyebrow}>{right}</Text><Text style={styles.amount}>{rightValue}</Text></View></View>; }
function humanType(type: Report['type']) { const base = type.replace('_category', '').replace('_', ' '); return `${base.replace(/^./, (letter) => letter.toUpperCase())} report${type.endsWith('_category') ? ' · Category' : ''}`; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Saved' : new Intl.DateTimeFormat('en-MY', { day: 'numeric', month: 'short' }).format(date); }

const styles = {
  card: { backgroundColor: authColors.surfaceContainerLowest, borderRadius: 18, padding: 16, shadowColor: authColors.primary, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.05, shadowRadius: 12, elevation: 2 } as const,
  heading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 } as const,
  title: { fontSize: 17, lineHeight: 22, fontFamily: authFont.bold, color: authColors.onSurface } as const,
  eyebrow: { fontSize: 11, fontFamily: authFont.bold, color: authColors.onSurfaceVariant, letterSpacing: 0.6 } as const,
  chips: { gap: 8, paddingVertical: 3, paddingRight: 8 } as const,
  chip: { borderWidth: 1, borderColor: authColors.outlineVariant, borderRadius: 999, paddingHorizontal: 13, paddingVertical: 8, backgroundColor: authColors.surfaceContainerLowest } as const,
  chipSelected: { borderColor: authColors.primary, backgroundColor: authColors.primaryFixed } as const,
  chipText: { fontSize: 13, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const,
  chipTextSelected: { color: authColors.onPrimaryFixed } as const,
  dateRow: { flexDirection: 'row', gap: 10, marginTop: 12 } as const,
  inputLabel: { marginBottom: 5, fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const,
  input: { height: 46, borderWidth: 1, borderColor: authColors.outlineVariant, borderRadius: 12, paddingHorizontal: 12, fontSize: 14, fontFamily: authFont.regular, color: authColors.onSurface, backgroundColor: authColors.surfaceContainerLow } as const,
  error: { marginTop: 10, fontSize: 13, fontFamily: authFont.semibold, color: authColors.error } as const,
  primaryButton: { minHeight: 48, marginTop: 16, borderRadius: 13, backgroundColor: authColors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 } as const,
  primaryButtonText: { fontSize: 15, fontFamily: authFont.bold, color: authColors.onPrimary } as const,
  emptyBanner: { padding: 14, borderRadius: 16, backgroundColor: authColors.primaryFixed, flexDirection: 'row', gap: 12, alignItems: 'center' } as const,
  emptyTitle: { fontSize: 14, fontFamily: authFont.semibold, color: authColors.onPrimaryFixed } as const,
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 } as const,
  metric: { width: '48%', flexGrow: 1, minHeight: 126, borderRadius: 18, padding: 14, backgroundColor: authColors.surfaceContainerLowest, shadowColor: authColors.primary, shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.05, shadowRadius: 10, elevation: 2 } as const,
  metricIcon: { width: 34, height: 34, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginBottom: 10 } as const,
  metricValue: { marginTop: 4, fontSize: 21, lineHeight: 27, fontFamily: authFont.bold } as const,
  between: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 } as const,
  amount: { fontSize: 20, lineHeight: 26, fontFamily: authFont.bold, color: authColors.onSurface } as const,
  muted: { fontSize: 13, lineHeight: 19, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  caption: { marginTop: 2, fontSize: 12, lineHeight: 17, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  percent: { fontSize: 13, fontFamily: authFont.bold, color: authColors.primary } as const,
  track: { height: 9, borderRadius: 999, backgroundColor: authColors.surfaceContainerHigh, overflow: 'hidden', marginVertical: 11 } as const,
  fill: { height: '100%', borderRadius: 999 } as const,
  categoryRow: { paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant } as const,
  legend: { flexDirection: 'row', alignItems: 'center', gap: 7 } as const,
  dot: { width: 9, height: 9, borderRadius: 5 } as const,
  rowLabel: { fontSize: 14, fontFamily: authFont.semibold, color: authColors.onSurface } as const,
  rowValue: { fontSize: 14, fontFamily: authFont.bold, color: authColors.onSurface } as const,
  trendLegend: { flexDirection: 'row', gap: 14, marginBottom: 6 } as const,
  trendRow: { minWidth: '100%', gap: 12, paddingTop: 6 } as const,
  trendColumn: { width: 86, alignItems: 'center' } as const,
  bars: { height: 100, flexDirection: 'row', gap: 5, alignItems: 'flex-end', justifyContent: 'center' } as const,
  trendBar: { width: 18, borderTopLeftRadius: 5, borderTopRightRadius: 5 } as const,
  trendLabel: { marginTop: 7, fontSize: 11, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const,
  trendNet: { marginTop: 2, fontSize: 11, fontFamily: authFont.bold, color: '#067647' } as const,
  historyRow: { minHeight: 60, flexDirection: 'row', alignItems: 'center', gap: 11, borderBottomWidth: 1, borderBottomColor: authColors.outlineVariant, paddingVertical: 9 } as const,
  historyIcon: { width: 38, height: 38, borderRadius: 12, backgroundColor: authColors.primaryFixed, alignItems: 'center', justifyContent: 'center' } as const,
  historyDate: { fontSize: 12, fontFamily: authFont.semibold, color: authColors.onSurfaceVariant } as const,
} as const;
