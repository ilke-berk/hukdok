/**
 * Föy (case_foys) etiket yardımcıları — G123.
 *
 * Bileşen dosyasından ayrı: CaseFoyPanel yalnız bileşen export etsin ki
 * fast-refresh çalışsın (react-refresh/only-export-components).
 */

/** Kart status havuzu → ekran etiketi; eşlenemeyen teslim yazımı olduğu gibi. */
const DURUM_ETIKETI: Record<string, string> = { DERDEST: "Aktif", MAHZEN: "Arşiv" };

/** Kapsam işareti (G113): NULL = kapsamda; SILINDI | KAPSAM_DISI = veri ekibi çıkardı, föy silinmedi. */
const KAPSAM_ETIKETI: Record<string, string> = { SILINDI: "Silinen föy", KAPSAM_DISI: "Kapsam dışı" };

export const foyDurumEtiketi = (durum?: string | null): string =>
    durum ? (DURUM_ETIKETI[durum] ?? durum) : "—";

export const foyKapsamEtiketi = (kapsam?: string | null): string | null =>
    kapsam ? (KAPSAM_ETIKETI[kapsam] ?? kapsam) : null;
