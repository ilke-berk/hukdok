// Belge tezgâhı durumu (G270 + G271, plan K2/K8): çalışma dosyaları YALNIZ bu oturumun belleğindedir — sayfa yenilenince
// liste gider (sunucu cache'i 1 saat TTL ile kendisi siler; kullanıcıya bilgi satırı sayfada). Çoklu yükleme dosyaları
// SIRAYLA, ayrı ayrı gönderir (K8: her yükleme tek dosya; sunucu semaforu 2); bir dosyanın hatası diğerlerini durdurmaz.
//
// G271 — sayfa düzeni: dosya başına YEREL düzen (`duzenler[dosyaId]`: sıra, döndürme, silinmiş, seçili). Sunucuya yalnız
// "Uygula" ile tek `sayfa_duzenle` isteği gider; çıktı yeni dosya olur, girdi dosyası listede kalır (K2 zincir) ve onun
// yerel düzeni sıfırlanır. Seçili sayfalar "böl" için ardışık bloklara çevrilir (`seciliSayfalardanAraliklar`).
import { useCallback, useMemo, useState } from "react";
import { hataMesaji, indir, islem, yukle } from "@/lib/pdfAraclariApi";
import type { DondurmeAcisi, Dosya, Islem, IslemIstegi, SayfaDuzenleParametreleri, SayfaKaydi } from "@/types/pdfAraclari";

export type YuklemeDurumu = {
  anahtar: string;
  ad: string;
  durum: "yukleniyor" | "tamam" | "hata";
  mesaj?: string;
};

export type TasimaYonu = "yukari" | "asagi";

/** Bir sayfanın yerel durumu: `no` orijinal sayfa numarası (sunucu sözleşmesi), `dondur` yerel toplam (mod 360). */
export type SayfaDurumu = {
  no: number;
  dondur: DondurmeAcisi;
  silindi: boolean;
};

export type SayfaDuzeni = {
  /** Sıra = yeni sıra. */
  sayfalar: SayfaDurumu[];
  /** Seçili sayfa numaraları (orijinal `no`). */
  secili: number[];
  /** Shift ile aralık seçiminin çapası (son tek tıklanan sayfa). */
  capa: number | null;
};

let yuklemeSayaci = 0;

export function varsayilanSayfaDuzeni(dosya: Dosya): SayfaDuzeni {
  const nolar = dosya.sayfalar.length > 0 ? dosya.sayfalar.map((s) => s.no) : Array.from({ length: dosya.sayfa }, (_, i) => i + 1);
  return { sayfalar: nolar.map((no) => ({ no, dondur: 0, silindi: false })), secili: [], capa: null };
}

/** Yerel düzen sunucuya gidecek bir fark taşıyor mu (sıra, döndürme ya da silme)? */
export function sayfaDegisikligiVar(duzen: SayfaDuzeni): boolean {
  return duzen.sayfalar.some((s, i) => s.no !== i + 1 || s.dondur !== 0 || s.silindi);
}

/** `sayfa_duzenle` gövdesi: silinenler listede YOK, sıra listedeki, `dondur` yalnız 0 dışında yazılır. */
export function sayfaDuzenleParametreleri(duzen: SayfaDuzeni): SayfaDuzenleParametreleri {
  const sayfalar: SayfaKaydi[] = duzen.sayfalar
    .filter((s) => !s.silindi)
    .map((s) => (s.dondur === 0 ? { no: s.no } : { no: s.no, dondur: s.dondur }));
  return { sayfalar };
}

/** Seçili sayfa numaraları → ardışık bloklar: `[1,2,3,7] → [[1,3],[7,7]]` (sıra bağımsız, tekrarlar atılır). */
export function seciliSayfalardanAraliklar(secili: number[]): [number, number][] {
  const sirali = Array.from(new Set(secili)).sort((a, b) => a - b);
  const bloklar: [number, number][] = [];
  for (const no of sirali) {
    const son = bloklar[bloklar.length - 1];
    if (son && no === son[1] + 1) son[1] = no;
    else bloklar.push([no, no]);
  }
  return bloklar;
}

function dondurmeEkle(aci: DondurmeAcisi, ek: 90 | 180 | 270 = 90): DondurmeAcisi {
  return (((aci + ek) % 360) as DondurmeAcisi);
}

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
  // G271: dosya başına yerel sayfa düzeni; kaydı olmayan dosya varsayılan düzende sayılır.
  const [duzenler, setDuzenler] = useState<Record<string, SayfaDuzeni>>({});

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
    setDuzenler((onceki) => {
      if (!(id in onceki)) return onceki;
      const kopya = { ...onceki };
      delete kopya[id];
      return kopya;
    });
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
        if (istek.islem === "sayfa_duzenle") {
          // Uygulanan düzen sunucuda çıktı oldu; girdi dosyası listede kalır, yerel düzeni sıfırlanır.
          const girdiId = istek.girdiler[0];
          setDuzenler((onceki) => {
            if (!(girdiId in onceki)) return onceki;
            const kopya = { ...onceki };
            delete kopya[girdiId];
            return kopya;
          });
        }
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

  // ── G271: sayfa düzeni ────────────────────────────────────────────────────
  const sayfaDuzeni = useMemo<SayfaDuzeni | null>(() => {
    if (!secili) return null;
    return duzenler[secili.id] ?? varsayilanSayfaDuzeni(secili);
  }, [secili, duzenler]);

  const duzeniGuncelle = useCallback(
    (dosyaId: string, dosya: Dosya, guncelle: (d: SayfaDuzeni) => SayfaDuzeni) => {
      setDuzenler((onceki) => ({ ...onceki, [dosyaId]: guncelle(onceki[dosyaId] ?? varsayilanSayfaDuzeni(dosya)) }));
    },
    [],
  );

  /** Sürükle-sırala: `aktifNo` sayfasını `hedefNo` sayfasının yerine taşır (dnd-kit `arrayMove` semantiği). */
  const sayfaTasi = useCallback(
    (aktifNo: number, hedefNo: number) => {
      if (!secili || aktifNo === hedefNo) return;
      duzeniGuncelle(secili.id, secili, (d) => {
        const i = d.sayfalar.findIndex((s) => s.no === aktifNo);
        const j = d.sayfalar.findIndex((s) => s.no === hedefNo);
        if (i < 0 || j < 0) return d;
        const kopya = [...d.sayfalar];
        const [tasinan] = kopya.splice(i, 1);
        kopya.splice(j, 0, tasinan);
        return { ...d, sayfalar: kopya };
      });
    },
    [secili, duzeniGuncelle],
  );

  const sayfaDondur = useCallback(
    (no: number, ek: 90 | 180 | 270 = 90) => {
      if (!secili) return;
      duzeniGuncelle(secili.id, secili, (d) => ({
        ...d,
        sayfalar: d.sayfalar.map((s) => (s.no === no ? { ...s, dondur: dondurmeEkle(s.dondur, ek) } : s)),
      }));
    },
    [secili, duzeniGuncelle],
  );

  /** Sil / geri al (kart soluk kalır; sunucuya gidince listeden düşer). Silinen sayfa seçimden de çıkar. */
  const sayfaSilToggle = useCallback(
    (no: number) => {
      if (!secili) return;
      duzeniGuncelle(secili.id, secili, (d) => {
        const sayfalar = d.sayfalar.map((s) => (s.no === no ? { ...s, silindi: !s.silindi } : s));
        const silindi = sayfalar.find((s) => s.no === no)?.silindi;
        return { ...d, sayfalar, secili: silindi ? d.secili.filter((x) => x !== no) : d.secili };
      });
    },
    [secili, duzeniGuncelle],
  );

  /** Seç/bırak; `aralik=true` (shift) çapadan bu sayfaya kadar LİSTE sırasındaki silinmemiş sayfaları seçer. */
  const sayfaSec = useCallback(
    (no: number, secili_: boolean, aralik = false) => {
      if (!secili) return;
      duzeniGuncelle(secili.id, secili, (d) => {
        if (aralik && d.capa !== null) {
          const sira = d.sayfalar.map((s) => s.no);
          const a = sira.indexOf(d.capa);
          const b = sira.indexOf(no);
          if (a >= 0 && b >= 0) {
            const [bas, bit] = a < b ? [a, b] : [b, a];
            const blok = d.sayfalar.slice(bas, bit + 1).filter((s) => !s.silindi).map((s) => s.no);
            const kume = new Set(d.secili);
            for (const x of blok) kume.add(x);
            return { ...d, secili: Array.from(kume), capa: no };
          }
        }
        const kume = new Set(d.secili);
        if (secili_) kume.add(no);
        else kume.delete(no);
        return { ...d, secili: Array.from(kume), capa: no };
      });
    },
    [secili, duzeniGuncelle],
  );

  const sayfalariSec = useCallback(
    (hepsi: boolean) => {
      if (!secili) return;
      duzeniGuncelle(secili.id, secili, (d) => ({
        ...d,
        secili: hepsi ? d.sayfalar.filter((s) => !s.silindi).map((s) => s.no) : [],
        capa: null,
      }));
    },
    [secili, duzeniGuncelle],
  );

  const sayfaDuzeniniSifirla = useCallback(() => {
    if (!secili) return;
    const id = secili.id;
    setDuzenler((onceki) => {
      if (!(id in onceki)) return onceki;
      const kopya = { ...onceki };
      delete kopya[id];
      return kopya;
    });
  }, [secili]);

  const sayfaDegisikligi = sayfaDuzeni ? sayfaDegisikligiVar(sayfaDuzeni) : false;

  /** "Uygula": tek `sayfa_duzenle` isteği; hiç değişiklik yoksa no-op. */
  const sayfaDuzeniniUygula = useCallback(async () => {
    if (!secili || !sayfaDuzeni || !sayfaDegisikligiVar(sayfaDuzeni)) return null;
    const parametreler = sayfaDuzenleParametreleri(sayfaDuzeni);
    if (parametreler.sayfalar.length === 0) {
      setHata("Tüm sayfalar silinemez; en az bir sayfa kalmalı.");
      return null;
    }
    return islemKos({ islem: "sayfa_duzenle", girdiler: [secili.id], parametreler });
  }, [secili, sayfaDuzeni, islemKos]);

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
    // G271
    sayfaDuzeni,
    sayfaDegisikligi,
    sayfaTasi,
    sayfaDondur,
    sayfaSilToggle,
    sayfaSec,
    sayfalariSec,
    sayfaDuzeniniSifirla,
    sayfaDuzeniniUygula,
  };
}

export type PdfTezgah = ReturnType<typeof usePdfTezgah>;
