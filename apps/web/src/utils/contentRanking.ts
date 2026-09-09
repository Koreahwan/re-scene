export interface RankingFields {
  registeredAt?: string | null;
  viewCount?: number;
  views7d?: number;
}
export function compareRanking(a: RankingFields, b: RankingFields, sort: string): number {
  const metric = sort === 'popular' ? (b.views7d || 0) - (a.views7d || 0)
    : sort === 'views' ? (b.viewCount || 0) - (a.viewCount || 0) : 0;
  return metric || (Date.parse(b.registeredAt || '') || 0) - (Date.parse(a.registeredAt || '') || 0);
}
export function rankingFields(raw: Record<string, unknown>): RankingFields {
  const count = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 ? v : 0;
  return { registeredAt: typeof raw.registered_at === 'string' ? raw.registered_at : null,
    viewCount: count(raw.view_count), views7d: count(raw.views_7d) };
}
