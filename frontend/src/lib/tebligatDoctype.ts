/**
 * Tebligat (mazbata) belge türü tanıma.
 *
 * Toplu yüklemede (Index.tsx `handleConfirmClick`) e-postası açık tebligat satırında
 * EmailModal ATLANMAZ: avukat mesaj metnini ve ek listesini görsün (kullanıcı kararı,
 * 20.09.2026). `kararDoctype.ts` kardeşidir — o küme TEBLIGAT'ı bilerek dışlar (karar
 * belgelerinden süre türetilir, tebligattan türetilmez); bu dosya yalnız türü tanır.
 *
 * Kod harf/rakam dışı karakterlerden arındırılıp "TEBLIG" ön ekiyle karşılaştırılır:
 * pad'li "TEBLIGAT______" ve olası "TEBLIG…" varyantları yakalanır (backend
 * `constants.HEARING_DOCTYPE_KEYWORDS` "TEBLIG" parçasıyla hizalı).
 */
import { normalizeDoctypeKey } from "./kararDoctype";

export function isTebligatDoctype(code?: string | null): boolean {
    return normalizeDoctypeKey(code).startsWith("TEBLIG");
}
