/** Financial dates follow Malaysia time, independently of the phone's timezone. */
export function malaysiaToday(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kuala_Lumpur', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)!.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function isTransactionDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

/** Material's Android calendar represents calendar days at UTC midnight. */
export function transactionDateForPicker(value: string, today: string, android: boolean): Date {
  const day = isTransactionDate(value) && value <= today ? value : today;
  return new Date(`${day}T00:00:00${android ? '.000Z' : ''}`);
}

export function transactionDateFromPicker(date: Date, android: boolean): string {
  if (android) return date.toISOString().slice(0, 10);
  return `${String(date.getFullYear()).padStart(4, '0')}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
