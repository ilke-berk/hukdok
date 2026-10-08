import { useCallback, useEffect, useRef, useState } from "react";
import { lexisApi } from "@/lib/lexisApi";
import type { KunyeHatDurumu, KunyeOneriDurumu, KunyeOnerisi } from "@/types/lexis";
import { hataMetni, iptalMi } from "./yardimcilar";

export type KunyeOnerileriDurumu = {
  oneriler: KunyeOnerisi[];
  /** Hat durumu; yüklenemediyse `null` (düğme çizilmez). */
  hat: KunyeHatDurumu | null;
  calisiyor: boolean;
  /** "Belge 1/2 okunuyor" gibi ilerleme satırı. */
  ilerleme: string | null;
  /** Akışın uyarıları (okunamayan belge, düşen öneri) — değer içermez. */
  uyarilar: string[];
  hata: string | null;
  /** "Belgelerden doldur": `onay` gerçek kipte ekrandaki kutudur (K4). */
  doldur: (onay: boolean) => Promise<void>;
  karar: (oneri: KunyeOnerisi, durum: KunyeOneriDurumu) => Promise<void>;
};

/**
 * Belgeden künye önerileri (`lexis-rapor` Aşama 13): dava seçilince kayıtlı öneriler ve hat durumu okunur; "Belgelerden
 * doldur" NDJSON akışını koşar; kabul / ret servisin veritabanına yazılır (karta DEĞİL, K34). Kabul edilen değeri
 * taslağın künyesine servis kendisi koyar (`/iskelet`, `/yaz` onaylı künyeyi okur).
 */
export function useKunyeOnerileri(caseId: number | null): KunyeOnerileriDurumu {
  const [oneriler, setOneriler] = useState<KunyeOnerisi[]>([]);
  const [hat, setHat] = useState<KunyeHatDurumu | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);
  const [ilerleme, setIlerleme] = useState<string | null>(null);
  const [uyarilar, setUyarilar] = useState<string[]>([]);
  const [hata, setHata] = useState<string | null>(null);
  const akis = useRef<AbortController | null>(null);

  useEffect(() => {
    setOneriler([]);
    setHat(null);
    setUyarilar([]);
    setHata(null);
    setIlerleme(null);
    akis.current?.abort();
    if (caseId === null) return;
    const ac = new AbortController();
    lexisApi
      .kunyeOnerileri(caseId, ac.signal)
      .then((y) => {
        setOneriler(y.oneriler);
        setHat(y.durum);
      })
      .catch((e) => {
        // Servisin veritabanı yoksa öneri özelliği görünmez; künye karttan gelmeye devam eder.
        if (!iptalMi(e)) setHat(null);
      });
    return () => ac.abort();
  }, [caseId]);

  useEffect(() => () => akis.current?.abort(), []);

  const doldur = useCallback(
    async (onay: boolean) => {
      if (caseId === null) return;
      akis.current?.abort();
      const ac = new AbortController();
      akis.current = ac;
      setCalisiyor(true);
      setHata(null);
      setUyarilar([]);
      setIlerleme("Belgeler okunuyor…");
      try {
        for await (const olay of lexisApi.kunyeOner(caseId, { onay, signal: ac.signal })) {
          if (olay.status === "info") {
            setIlerleme(olay.asama === "capraz" ? "Öneriler birlikte denetleniyor…" : `Belge ${olay.sira ?? "?"}/${olay.toplam ?? "?"} okunuyor…`);
          } else if (olay.status === "warning") {
            setUyarilar((u) => [...u, olay.message]);
          } else if (olay.status === "complete") {
            setOneriler(olay.oneriler);
          } else if (olay.status === "failed") {
            setHata(olay.error_ozet);
          }
        }
      } catch (e) {
        if (!iptalMi(e)) setHata(hataMetni(e, "Künye çıkarımı tamamlanamadı."));
      } finally {
        if (akis.current === ac) {
          setCalisiyor(false);
          setIlerleme(null);
        }
      }
    },
    [caseId],
  );

  const karar = useCallback(
    async (oneri: KunyeOnerisi, durum: KunyeOneriDurumu) => {
      setHata(null);
      try {
        const yeni = await lexisApi.kunyeKarar(oneri.id, oneri.case_id, durum);
        setOneriler((liste) => liste.map((o) => (o.id === yeni.id ? yeni : o)));
      } catch (e) {
        setHata(hataMetni(e, "Karar kaydedilemedi."));
      }
    },
    [],
  );

  return { oneriler, hat, calisiyor, ilerleme, uyarilar, hata, doldur, karar };
}
