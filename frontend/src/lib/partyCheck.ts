/**
 * partyCheck.ts
 *
 * Tanıdık Sorgu yardımcıları — saf fonksiyonlar (import yan etkisi yok,
 * vitest'te doğrudan test edilir). API çağrıları hooks/usePartyCheck.ts'te.
 */

/** Bu uzunluğun altındaki isimler sorgulanmaz (backend party_check._NAME_MIN_LEN ile aynı). */
export const MIN_CHECK_LENGTH = 4;

/** Tek alana ";" veya "," ile yazılmış çoklu isimleri ayrı kişilere böler. */
export const splitCheckNames = (value: string): string[] =>
    value.split(/[;,]/).map(s => s.trim()).filter(Boolean);

/** TR-upper isim anahtarı (tcByName eşlemeleri için). */
export const partyNameKey = (name: string) => name.trim().toLocaleUpperCase("tr-TR");
