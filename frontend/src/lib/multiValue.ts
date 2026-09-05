/**
 * Çok değerli hücre sözleşmesi (G124) — backend `services/multi_value.py` ikizi.
 *
 * Tıbbi beşli (tıbbi süreç / olay / iddia edilen kusur / hastada oluşan zarar /
 * uygulanan yöntem) tek metin kolonunda " ; " ile birleşik saklanır. Ayraç
 * noktalı virgüldür; virgül ayraç DEĞİLDİR (değerler virgül içerebilir).
 */
export const MULTI_SEPARATOR = " ; ";

const normalizeKey = (s: string): string => s.trim().toLocaleLowerCase("tr-TR");

/** Hücreyi parçalara ayırır: kırpar, boş ve mükerrer parçayı düşürür (ilk sıra korunur). */
export function splitValues(value: unknown): string[] {
    if (value === null || value === undefined) return [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const raw of String(value).split(/[;\r\n]+/)) {
        const part = raw.replace(/\s+/g, " ").trim();
        const key = normalizeKey(part);
        if (!part || seen.has(key)) continue;
        seen.add(key);
        out.push(part);
    }
    return out;
}

/** Parçaları kanonik ayraçla birleştirir; boş → "" (panel "" → null → alan silinir). */
export function joinValues(values: string[]): string {
    return values.map(v => v.replace(/\s+/g, " ").trim()).filter(Boolean).join(MULTI_SEPARATOR);
}
