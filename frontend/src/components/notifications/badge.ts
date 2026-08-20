/**
 * Zil rozetinin metni. Ayrı dosyada: bileşen dosyasından fonksiyon ihraç etmek
 * `react-refresh/only-export-components` uyarısı üretiyor (eslint.config.js).
 */

/** Rozet tavanı: bunun üstü "9+" yazılır — köşe rozeti dar, sayı taşmasın. */
export const NOTIFICATION_BADGE_CAP = 9;

export function formatBadge(count: number): string {
  return count > NOTIFICATION_BADGE_CAP ? `${NOTIFICATION_BADGE_CAP}+` : String(count);
}
