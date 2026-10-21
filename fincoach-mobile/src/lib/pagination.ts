type PageResult = { data: unknown; error: unknown; count?: number | null };
type PageQuery = { range: (from: number, to: number) => PromiseLike<PageResult> };

/** Never return a silently truncated financial dataset, even with a lower server cap. */
export async function fetchAllRows<T extends { id: string | number }>(query: () => PageQuery): Promise<T[]> {
  const rows: T[] = [];
  const seen = new Set<string | number>();
  let expected: number | undefined;
  for (;;) {
    const { data, error, count } = await query().range(rows.length, rows.length + 499);
    if (error) throw error;
    if (!Number.isSafeInteger(count) || count == null || count < 0) throw new Error('Could not verify the complete record count. Please retry.');
    if (expected !== undefined && expected !== count) throw new Error('Records changed while loading. Please retry.');
    expected = count;
    const page = (data ?? []) as T[];
    for (const row of page) {
      if (row.id == null || seen.has(row.id)) throw new Error('Records changed while loading. Please retry.');
      seen.add(row.id);
      rows.push(row);
    }
    if (rows.length === expected) return rows;
    if (!page.length || rows.length > expected) throw new Error('The record list is incomplete. Please retry.');
  }
}
