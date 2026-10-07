// Belge tezgâhı durumu (G270, plan K2/K8): çalışma dosyaları YALNIZ bu oturumun belleğindedir — sayfa yenilenince
// liste gider (sunucu cache'i 1 saat TTL ile kendisi siler; kullanıcıya bilgi satırı sayfada). Çoklu yükleme dosyaları
// SIRAYLA, ayrı ayrı gönderir (K8: her yükleme tek dosya; sunucu semaforu 2); bir dosyanın hatası diğerlerini durdurmaz.
import { useCallback, useMemo, useState } from "react";
import { hataMesaji, indir, islem, yukle } from "@/lib/pdfAraclariApi";
import type { Dosya, Islem, IslemIstegi } from "@/types/pdfAraclari";

export type YuklemeDurumu = {
  anahtar: string;
  ad: string;
  durum: "yukleniyor" | "tamam" | "hata";
  mesaj?: string;
};

export type TasimaYonu = "yukari" | "asagi";

let yuklemeSayaci = 0;

export function usePdfTezgah() {
  const [dosyalar, setDosyalar] = useState<Dosya[]>([]);
  const [seciliId, setSeciliId] = useState<string | null>(null);
  // İşaretliler = birleştirme girdileri; sıra `dosyalar` listesinin sırasıdır (yukarı/aşağı düğmeleri listeyi taşır).
  const [isaretliler, setIsaretliler] = useState<string[]>([]);
  const [surenIslem, setSurenIslem] = useState<Islem | null>(null);
  const [yuklemeler, setYuklemeler] = useState<YuklemeDurumu[]>([]);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [indiriliyor, setIndiriliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const dosyaEkle = useCallback((yeniler: Dosya[]) => {
    if (yeniler.length === 0) return;
    setDosyalar((onceki) => {
      const mevcut = new Set(onceki.map((d) => d.id));
      return [...onceki, ...yeniler.filter((d) => !mevcut.has(d.id))];
    });
    setSeciliId(yeniler[0].id);
  }, []);

  const yuklemeGuncelle = useCallback((anahtar: string, degisim: Partial<YuklemeDurumu>) => {
    setYuklemeler((onceki) => onceki.map((y) => (y.anahtar === anahtar ? { ...y, ...degisim } : y)));
  }, []);

  /** Dosyaları sırayla yükler; her satırın sonucu `yuklemeler`de. Yeni parti önceki satırları temizler. */
  const yukleHepsini = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      setHata(null);
      setYukleniyor(true);
      const satirlar: YuklemeDurumu[] = files.map((f) => ({
        anahtar: `y${++yuklemeSayaci}`,
        ad: f.name,
        durum: "yukleniyor",
      }));
      setYuklemeler(satirlar);
      try {
        for (let i = 0; i < files.length; i++) {
          const satir = satirlar[i];
          try {
            const dosya = await yukle(files[i]);
            dosyaEkle([dosya]);
            yuklemeGuncelle(satir.anahtar, { durum: "tamam", ad: dosya.ad });
          } catch (e) {
            yuklemeGuncelle(satir.anahtar, { durum: "hata", mesaj: hataMesaji(e) });
          }
        }
      } finally {
        setYukleniyor(false);
      }
    },
    [dosyaEkle, yuklemeGuncelle],
  );

  const yuklemeleriTemizle = useCallback(() => setYuklemeler([]), []);

  /** Yalnız istemci listesinden düşürür; sunucudaki dosyaya dokunmaz (TTL siler). */
  const listedenKaldir = useCallback((id: string) => {
    setDosyalar((onceki) => {
      const kalan = onceki.filter((d) => d.id !== id);
      setSeciliId((secili) => (secili === id ? (kalan[0]?.id ?? null) : secili));
      return kalan;
    });
    setIsaretliler((onceki) => onceki.filter((x) => x !== id));
  }, []);

  const sec = useCallback((id: string) => setSeciliId(id), []);

  const isaretle = useCallback((id: string, isaretli: boolean) => {
    setIsaretliler((onceki) => {
      const var_ = onceki.includes(id);
      if (isaretli && !var_) return [...onceki, id];
      if (!isaretli && var_) return onceki.filter((x) => x !== id);
      return onceki;
    });
  }, []);

  const tasi = useCallback((id: string, yon: TasimaYonu) => {
    setDosyalar((onceki) => {
      const i = onceki.findIndex((d) => d.id === id);
      const j = yon === "yukari" ? i - 1 : i + 1;
      if (i < 0 || j < 0 || j >= onceki.length) return onceki;
      const kopya = [...onceki];
      [kopya[i], kopya[j]] = [kopya[j], kopya[i]];
      return kopya;
    });
  }, []);

  /** İşlemi koşar; çıktılar listeye düşer ve ilki seçilir. Hata `hata`ya yazılır, `null` döner. */
  const islemKos = useCallback(
    async (istek: IslemIstegi): Promise<Dosya[] | null> => {
      setHata(null);
      setSurenIslem(istek.islem);
      try {
        const ciktilar = await islem(istek);
        dosyaEkle(ciktilar);
        return ciktilar;
      } catch (e) {
        setHata(hataMesaji(e));
        return null;
      } finally {
        setSurenIslem(null);
      }
    },
    [dosyaEkle],
  );

  const indirSecili = useCallback(async () => {
    const secili = dosyalar.find((d) => d.id === seciliId);
    if (!secili) return;
    setHata(null);
    setIndiriliyor(true);
    try {
      await indir(secili.id, secili.ad);
    } catch (e) {
      setHata(hataMesaji(e));
    } finally {
      setIndiriliyor(false);
    }
  }, [dosyalar, seciliId]);

  const hatayiKapat = useCallback(() => setHata(null), []);

  const secili = useMemo(() => dosyalar.find((d) => d.id === seciliId) ?? null, [dosyalar, seciliId]);
  const isaretliDosyalar = useMemo(() => dosyalar.filter((d) => isaretliler.includes(d.id)), [dosyalar, isaretliler]);

  return {
    dosyalar,
    secili,
    seciliId,
    isaretliler,
    isaretliDosyalar,
    surenIslem,
    yuklemeler,
    yukleniyor,
    indiriliyor,
    hata,
    yukleHepsini,
    yuklemeleriTemizle,
    dosyaEkle,
    listedenKaldir,
    sec,
    isaretle,
    tasi,
    islemKos,
    indirSecili,
    hatayiKapat,
  };
}

export type PdfTezgah = ReturnType<typeof usePdfTezgah>;
