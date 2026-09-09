import englishPosters from './englishPosters.json';

export interface PublicFilmIntroduction {
  pageId: number;
  title: string;
  description: string;
  extract: string;
  sourceUrl: string;
  posterUrl?: string;
}

const normalizedTitle = (title: string) => title.normalize('NFKC').replace(/\s*\([^)]*\)\s*$/, '').replace(/[’‘]/g, "'").replace(/\s+/g, ' ').trim().toLowerCase();

// Editorial identity resolution, not a ranking or poster override. These releases
// were verified against the source weekend table; do not reuse for another week.
// https://www.boxofficemojo.com/weekend/2026W36/
// Odyssey: /release/rl170295297/ (Jul 17, 2026)
// By Any Means: /release/rl564363265/ (Sep 4, 2026)
export function selectChartFilm(title: string, period: string, matches: PublicFilmIntroduction[], now = new Date()) {
  if (matches.length === 1) return matches[0];
  if (now.getUTCFullYear() !== 2026 || period.replace(/\s/g, '').replace(/[–—\u0096]/g, '-') !== 'WeekendBoxOffice,Sep4-6') return undefined;
  const verifiedRelease: Record<string, string> = {
    'The Odyssey': 'The Odyssey (2026 film)', 'By Any Means': 'By Any Means (2026 film)',
  };
  return matches.find(film => film.title === verifiedRelease[title]);
}

// The chart has no stable film IDs. Keep multiple title matches explicit instead
// of silently pairing a current release with an older film of the same name.
export async function findPublicFilmIntroductions(title: string, signal: AbortSignal): Promise<PublicFilmIntroduction[]> {
  const params = new URLSearchParams({ action: 'query', format: 'json', formatversion: '2', origin: '*',
    generator: 'search', gsrsearch: `intitle:"${title.replace(/"/g, '')}" film`, gsrnamespace: '0', gsrlimit: '10',
    prop: 'description|extracts|pageprops|pageimages', piprop: 'thumbnail', pithumbsize: '700', pilicense: 'any', exintro: '1', explaintext: '1', exlimit: '10', exchars: '2400',
    ppprop: 'disambiguation', redirects: '1' });
  // Public, anonymous request: do not use the authenticated application client.
  const response = await fetch(`https://en.wikipedia.org/w/api.php?${params}`, {
    signal, credentials: 'omit', referrerPolicy: 'no-referrer',
  });
  if (!response.ok) throw new Error('Film information is temporarily unavailable.');
  const payload = await response.json();
  if (payload.error) throw new Error('Film information is temporarily unavailable.');
  const pages = payload.query?.pages;
  if (pages === undefined) return [];
  if (!Array.isArray(pages)) throw new Error('Film information could not be verified.');
  return pages.filter(page => Number.isSafeInteger(page.pageid) && page.pageid > 0 &&
    typeof page.title === 'string' && normalizedTitle(page.title) === normalizedTitle(title) &&
    !page.missing && page.pageprops?.disambiguation === undefined &&
    /\bfilm\b/i.test(`${page.description || ''} ${page.title}`) &&
    !/\b(film series|film score|franchise|soundtrack|television series|TV series)\b/i.test(`${page.title} ${page.description || ''}`))
    .map(page => ({ pageId: page.pageid, title: page.title,
      description: typeof page.description === 'string' ? page.description.slice(0, 500) : '',
      extract: typeof page.extract === 'string' ? page.extract.slice(0, 5000) : '',
      sourceUrl: `https://en.wikipedia.org/?curid=${page.pageid}`,
      // An English article can contain a foreign-language poster. Only show reviewed assets.
      posterUrl: (englishPosters as Record<string, string>)[String(page.pageid)],
    })).sort((a, b) => a.title.localeCompare(b.title));
}
