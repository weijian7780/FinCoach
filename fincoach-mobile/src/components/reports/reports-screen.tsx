import { MaterialIcons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ReportDashboard, ReportFilters, ReportHistory } from '@/components/reports/report-components';
import { AppText as Text } from '@/components/ui/app-text';
import { authColors, authFont } from '@/constants/auth-theme';
import { useAuth } from '@/lib/auth-context';
import { compileFinancialReport, createPresetSelection, validateReportSelection, withReportCategory } from '@/lib/report-domain';
import { createReportRecord, fetchRecentReports, fetchReportSourceData } from '@/lib/reports';
import { fetchTransactionCategories } from '@/lib/transactions';
import type { Category, FinancialReport, Report, ReportPreset, ReportSelection } from '@/lib/types';

function reportErrorMessage(action: 'load' | 'generate' | 'refresh') {
  if (action === 'generate') return 'The report could not be generated. Check your connection and try again.';
  if (action === 'refresh') return 'The report could not be refreshed. Your last successful results are still shown.';
  return 'Financial data could not be loaded. Check your connection and try again.';
}

export default function ReportsScreen() {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const userId = session?.user.id;
  const [selection, setSelection] = useState<ReportSelection>(() => createPresetSelection('current_month'));
  const selectionRef = useRef(selection);
  const [report, setReport] = useState<FinancialReport | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [historyWarning, setHistoryWarning] = useState<string | null>(null);
  const [historyUnavailable, setHistoryUnavailable] = useState(false);

  useEffect(() => {
    selectionRef.current = selection;
  }, [selection]);

  const loadHistory = useCallback(async () => {
    if (!userId) return;
    try {
      setReports(await fetchRecentReports(userId));
      setHistoryUnavailable(false);
    } catch {
      setHistoryUnavailable(true);
    }
  }, [userId]);

  const loadPreview = useCallback(async () => {
    if (!userId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setHistoryWarning(null);
    try {
      const activeSelection = selectionRef.current;
      const [availableCategories, source] = await Promise.all([
        fetchTransactionCategories(userId),
        fetchReportSourceData(userId, activeSelection),
      ]);
      setCategories(availableCategories);
      setReport(compileFinancialReport(source, activeSelection));
    } catch {
      setError(reportErrorMessage('load'));
    } finally {
      setLoading(false);
    }
    await loadHistory();
  }, [loadHistory, userId]);

  useFocusEffect(useCallback(() => { void loadPreview(); }, [loadPreview]));

  const generateReport = useCallback(async () => {
    if (!userId || generating) return;
    const selectionError = validateReportSelection(selection);
    setValidationError(selectionError);
    if (selectionError) return;
    setGenerating(true);
    setError(null);
    setHistoryWarning(null);
    try {
      const source = await fetchReportSourceData(userId, selection);
      setReport(compileFinancialReport(source, selection));
      try {
        await createReportRecord(userId, selection);
        await loadHistory();
      } catch {
        setHistoryWarning('Report generated, but its history record could not be saved.');
        setHistoryUnavailable(true);
      }
    } catch {
      setError(reportErrorMessage('generate'));
    } finally {
      setGenerating(false);
    }
  }, [generating, loadHistory, selection, userId]);

  const refreshReport = useCallback(async () => {
    if (!userId || refreshing) return;
    const selectionError = validateReportSelection(selection);
    setValidationError(selectionError);
    if (selectionError) return;
    setRefreshing(true);
    setError(null);
    try {
      const source = await fetchReportSourceData(userId, selection);
      setReport(compileFinancialReport(source, selection));
      await loadHistory();
    } catch {
      setError(reportErrorMessage('refresh'));
    } finally {
      setRefreshing(false);
    }
  }, [loadHistory, refreshing, selection, userId]);

  const changePreset = useCallback((preset: ReportPreset) => {
    setSelection(withReportCategory(createPresetSelection(preset), selection.categoryId));
    setValidationError(null);
  }, [selection.categoryId]);

  const changeCategory = useCallback((categoryId: number | null) => {
    setSelection((current) => withReportCategory(current, categoryId));
    setValidationError(null);
  }, []);

  const changeCustomDate = useCallback((key: 'startDate' | 'endDate', value: string) => {
    setSelection((current) => ({ ...current, [key]: value }));
    setValidationError(null);
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: authColors.surface }}>
      <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel="Go back" onPress={() => router.back()} hitSlop={8} style={styles.backButton}>
          <MaterialIcons name="arrow-back" size={23} color={authColors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}><Text style={styles.pageTitle}>Reports & Analytics</Text><Text style={styles.pageSubtitle}>Calculated from your real financial records</Text></View>
      </View>

      {loading ? (
        <View style={styles.centerState}><ActivityIndicator size="large" color={authColors.primary} /><Text style={styles.stateTitle}>Compiling your finances…</Text><Text style={styles.stateCopy}>Loading transactions, budgets, and savings goals.</Text></View>
      ) : (
        <ScrollView
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refreshReport()} tintColor={authColors.primary} colors={[authColors.primary]} />}
          contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 32, gap: 16 }}
          keyboardShouldPersistTaps="handled"
        >
          <ReportFilters
            selection={selection}
            categories={categories}
            onPresetChange={changePreset}
            onCategoryChange={changeCategory}
            onStartDateChange={(value) => changeCustomDate('startDate', value)}
            onEndDateChange={(value) => changeCustomDate('endDate', value)}
            onGenerate={() => void generateReport()}
            generating={generating}
            validationError={validationError}
          />
          {error ? (
            <View accessibilityRole="alert" style={styles.errorCard}>
              <MaterialIcons name="cloud-off" size={23} color={authColors.error} />
              <View style={{ flex: 1 }}><Text style={styles.errorTitle}>Report unavailable</Text><Text style={styles.stateCopy}>{error}</Text></View>
              <Pressable accessibilityRole="button" onPress={() => void refreshReport()}><Text style={styles.retryText}>Retry</Text></Pressable>
            </View>
          ) : null}
          {historyWarning ? <View accessibilityRole="alert" style={styles.warningCard}><MaterialIcons name="history-toggle-off" size={20} color="#8A4B00" /><Text style={styles.warningText}>{historyWarning}</Text></View> : null}
          {report ? <ReportDashboard report={report} /> : !error ? <View style={styles.centerCard}><MaterialIcons name="analytics" size={34} color={authColors.primary} /><Text style={styles.stateTitle}>Choose filters to generate a report</Text></View> : null}
          <ReportHistory reports={reports} unavailable={historyUnavailable} />
        </ScrollView>
      )}
    </View>
  );
}

const styles = {
  topBar: { minHeight: 76, paddingHorizontal: 16, paddingBottom: 11, flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: authColors.surface } as const,
  backButton: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: authColors.surfaceContainerLowest } as const,
  pageTitle: { fontSize: 20, lineHeight: 25, fontFamily: authFont.bold, color: authColors.onSurface } as const,
  pageSubtitle: { marginTop: 1, fontSize: 12, lineHeight: 16, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  centerState: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28, gap: 9 } as const,
  centerCard: { minHeight: 150, alignItems: 'center', justifyContent: 'center', gap: 10, borderRadius: 18, padding: 20, backgroundColor: authColors.surfaceContainerLowest } as const,
  stateTitle: { fontSize: 16, fontFamily: authFont.semibold, color: authColors.onSurface, textAlign: 'center' } as const,
  stateCopy: { fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: authColors.onSurfaceVariant } as const,
  errorCard: { borderWidth: 1, borderColor: '#F3B6B6', borderRadius: 16, padding: 14, backgroundColor: '#FFF4F4', flexDirection: 'row', alignItems: 'center', gap: 11 } as const,
  errorTitle: { fontSize: 14, fontFamily: authFont.semibold, color: authColors.error } as const,
  retryText: { fontSize: 13, fontFamily: authFont.bold, color: authColors.primary } as const,
  warningCard: { borderWidth: 1, borderColor: '#F0C68A', borderRadius: 14, padding: 12, backgroundColor: '#FFF8E8', flexDirection: 'row', alignItems: 'center', gap: 9 } as const,
  warningText: { flex: 1, fontSize: 13, lineHeight: 18, fontFamily: authFont.regular, color: '#6B3A00' } as const,
} as const;
