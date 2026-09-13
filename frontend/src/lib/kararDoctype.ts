/**
 * Karar belgesi türleri — tebliğ tarihi aşama kararına yazılan küme.
 *
 * Backend `routes/processing.KARAR_DOCTYPE_TO_DECISION_STAGE` ile birebir aynı
 * anahtarlar; kod harf/rakam dışı karakterlerden arındırılarak karşılaştırılır
 * ("GEREKCELI-KRR_" / "GEREKCELIKRR" aynı tür). TEBLIGAT (mazbata) bu kümede
 * DEĞİLDİR: her şeyin tebliği olabilir, ondan süre türetilmez.
 */
export const KARAR_DOCTYPE_KEYS = ["GEREKCELIKRR", "ISTINAFKRR", "YARGITAYKRR", "KRRDZLTMKRR"] as const;

export function normalizeDoctypeKey(code?: string | null): string {
    return (code ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function isKararDoctype(code?: string | null): boolean {
    const key = normalizeDoctypeKey(code);
    return key !== "" && (KARAR_DOCTYPE_KEYS as readonly string[]).includes(key);
}
