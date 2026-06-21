/**
 * nameSimilarity.ts
 *
 * Basit Levenshtein tabanlı isim benzerliği.
 * Danışma (DANIŞ) kaydında girilen müvekkil adı listede yoksa, olası yazım
 * hatasını yakalayıp en yakın mevcut müvekkili önermek için kullanılır.
 */

const normalize = (s: string) =>
    s.trim().toLocaleLowerCase("tr-TR").replace(/\s+/g, " ");

/** İki string arasındaki Levenshtein (düzenleme) mesafesi. */
export function levenshtein(a: string, b: string): number {
    const m = a.length;
    const n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;

    let prev = Array.from({ length: n + 1 }, (_, j) => j);
    for (let i = 1; i <= m; i++) {
        const curr = [i];
        for (let j = 1; j <= n; j++) {
            const cost = a[i - 1] === b[j - 1] ? 0 : 1;
            curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
        }
        prev = curr;
    }
    return prev[n];
}

/**
 * `target` için aday listesinden olası yazım hatası eşleşmesini döndürür.
 * Eşik: kısa adlarda 1, orta 2, uzun adlarda 3 karakter farkı. Tam eşleşme (0)
 * veya eşiğin üstündeki farklar `null` döndürür. Dönen değer, eşleşen adayın
 * orijinal (girildiği) hâlidir.
 */
export function closestName(target: string, candidates: string[]): string | null {
    const t = normalize(target);
    if (!t) return null;

    const maxDist = t.length <= 4 ? 1 : t.length <= 8 ? 2 : 3;
    let best: string | null = null;
    let bestDist = Infinity;

    for (const c of candidates) {
        const nc = normalize(c);
        if (!nc) continue;
        const d = levenshtein(t, nc);
        if (d > 0 && d < bestDist) {
            bestDist = d;
            best = c;
        }
    }

    return bestDist <= maxDist ? best : null;
}
