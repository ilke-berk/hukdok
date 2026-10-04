import { useCallback, useEffect, useRef, useState } from "react";
import { lexisApi } from "@/lib/lexisApi";
import {
  ISKELET_BOLUMLERI,
  type BolumKodu,
  type DosyaGirdisi,
  type Emsal,
  type KutuphaneKaydi,
  type LexisDava,
  type LexisTaslak,
  type LexisUyari,
  type Madde,
  type OzetParagraf,
  type TaslakIstegi,
  type UretimAsamasi,
} from "@/types/lexis";
import type { BolumDurumu } from "./BolumGezgini";
import type { KunyeSecimi } from "./KunyeKarti";
import { hataMetni, iptalMi } from "./yardimcilar";

type BolumDurumlari = Partial<Record<BolumKodu, BolumDurumu>>;

const saat = () => new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });

/**
 * "Rapor yaz" tezgâhının durumu ve eylemleri. Sıra: dava seç → dosya (künye + belgeler) ve emsaller gelir →
 * `yaz` akışı bölümleri doldurur → insan düzenler → `denetle` uyarıları yeniler.
 *
 * - Taslağın güncel hâli `taslakRef`'te de tutulur: olay işleyicileri art arda geldiğinde (yaz → çık) state'in
 *   bir önceki render'ına bakmasınlar diye. Her yazma `koy` üzerinden geçer.
 * - Metin düzenlemesi denetimi BAYATLATIR (madde "denetlenmedi" görünür); alandan çıkınca ya da yapısal
 *   değişiklikte (madde ekle/sil/taşı) yeniden denetlenir. Geç gelen eski denetim cevabı yok sayılır.
 */
export function useTezgah() {
  const [dosya, setDosya] = useState<DosyaGirdisi | null>(null);
  const [dosyaYukleniyor, setDosyaYukleniyor] = useState(false);
  const [dosyaHatasi, setDosyaHatasi] = useState<string | null>(null);
  const [seciliBelgeler, setSeciliBelgeler] = useState<ReadonlySet<number>>(new Set());
  const [emsaller, setEmsaller] = useState<Emsal[]>([]);
  const [emsalYukleniyor, setEmsalYukleniyor] = useState(false);
  const [emsalHatasi, setEmsalHatasi] = useState<string | null>(null);

  const [taslak, setTaslak] = useState<LexisTaslak | null>(null);
  const [bolumDurumlari, setBolumDurumlari] = useState<BolumDurumlari>({});
  const [akis, setAkis] = useState<{ asama: UretimAsamasi; mesaj: string | null } | null>(null);
  const [akisHatasi, setAkisHatasi] = useState<string | null>(null);

  const [uyarilar, setUyarilar] = useState<LexisUyari[]>([]);
  const [bayat, setBayat] = useState(false);
  const [denetleniyor, setDenetleniyor] = useState(false);
  const [sonDenetim, setSonDenetim] = useState<string | null>(null);
  const [maddeKimlikleri, setMaddeKimlikleri] = useState<string[]>([]);
  const [degisenMaddeler, setDegisenMaddeler] = useState<ReadonlySet<string>>(new Set());

  const taslakRef = useRef<LexisTaslak | null>(null);
  const kimliklerRef = useRef<string[]>([]);
  const dosyaIstegi = useRef<AbortController | null>(null);
  const emsalIstegi = useRef<AbortController | null>(null);
  const akisIstegi = useRef<AbortController | null>(null);
  const denetimSayaci = useRef(0);
  const kimlikSayaci = useRef(0);

  const yeniKimlik = useCallback(() => {
    kimlikSayaci.current += 1;
    return `m${kimlikSayaci.current}`;
  }, []);

  const koy = useCallback((yeni: LexisTaslak | null) => {
    taslakRef.current = yeni;
    setTaslak(yeni);
  }, []);

  const kimlikleriKoy = useCallback((yeni: string[]) => {
    kimliklerRef.current = yeni;
    setMaddeKimlikleri(yeni);
  }, []);

  const taslagiSifirla = useCallback(() => {
    akisIstegi.current?.abort();
    denetimSayaci.current += 1;
    koy(null);
    kimlikleriKoy([]);
    setBolumDurumlari({});
    setAkis(null);
    setAkisHatasi(null);
    setUyarilar([]);
    setBayat(false);
    setDenetleniyor(false);
    setSonDenetim(null);
    setDegisenMaddeler(new Set());
  }, [koy, kimlikleriKoy]);

  // Sayfadan çıkışta süren istekler kesilir.
  useEffect(
    () => () => {
      dosyaIstegi.current?.abort();
      emsalIstegi.current?.abort();
      akisIstegi.current?.abort();
    },
    [],
  );

  const emsalleriYukle = useCallback((d: DosyaGirdisi) => {
    emsalIstegi.current?.abort();
    const ac = new AbortController();
    emsalIstegi.current = ac;
    setEmsalYukleniyor(true);
    setEmsalHatasi(null);
    lexisApi
      .emsalOner({ case_id: d.dava.case_id, sirket: d.sirket, rapor_turu: d.rapor_turu }, ac.signal)
      .then((liste) => setEmsaller(liste))
      .catch((e: unknown) => {
        if (!iptalMi(e)) setEmsalHatasi(hataMetni(e, "Emsaller alınamadı."));
      })
      .finally(() => {
        if (!ac.signal.aborted) setEmsalYukleniyor(false);
      });
  }, []);

  const davaSec = useCallback(
    (dava: LexisDava | null) => {
      dosyaIstegi.current?.abort();
      emsalIstegi.current?.abort();
      taslagiSifirla();
      setDosya(null);
      setDosyaHatasi(null);
      setEmsaller([]);
      setEmsalHatasi(null);
      setEmsalYukleniyor(false);
      setSeciliBelgeler(new Set());
      if (!dava) {
        setDosyaYukleniyor(false);
        return;
      }
      const ac = new AbortController();
      dosyaIstegi.current = ac;
      setDosyaYukleniyor(true);
      lexisApi
        .dosyaGetir(dava.case_id, ac.signal)
        .then((d) => {
          setDosya(d);
          setSeciliBelgeler(new Set(d.belgeler.map((b) => b.id)));
          emsalleriYukle(d);
        })
        .catch((e: unknown) => {
          if (!iptalMi(e)) setDosyaHatasi(hataMetni(e, "Dosya alınamadı."));
        })
        .finally(() => {
          if (!ac.signal.aborted) setDosyaYukleniyor(false);
        });
    },
    [emsalleriYukle, taslagiSifirla],
  );

  /** Şirket / tür / iskelet seçimi. Yazılmış taslağı siler (çağıran önce onay alır); şirket ya da tür değişince emsaller yeniden aranır. */
  const kunyeDegistir = useCallback(
    (secim: KunyeSecimi) => {
      if (!dosya) return;
      const yeni: DosyaGirdisi = { ...dosya, ...secim };
      // Ek rapor yalnız EK iskeletiyle yazılır; ana rapora dönülünce EK iskeleti bırakılır.
      if (secim.rapor_turu === "EK" && !secim.iskelet) yeni.iskelet = "EK";
      if (secim.rapor_turu === "ANA" && !secim.iskelet && dosya.iskelet === "EK") yeni.iskelet = "KISA";
      setDosya(yeni);
      taslagiSifirla();
      if (yeni.sirket !== dosya.sirket || yeni.rapor_turu !== dosya.rapor_turu) emsalleriYukle(yeni);
    },
    [dosya, emsalleriYukle, taslagiSifirla],
  );

  const belgeSec = useCallback((id: number, secili: boolean) => {
    setSeciliBelgeler((onceki) => {
      const yeni = new Set(onceki);
      if (secili) yeni.add(id);
      else yeni.delete(id);
      return yeni;
    });
  }, []);

  const emsalCikar = useCallback((sha256: string) => {
    setEmsaller((onceki) => onceki.filter((e) => e.kayit.okuma.sha256 !== sha256));
  }, []);

  const emsalEkle = useCallback(
    async (kayit: KutuphaneKaydi) => {
      if (!dosya) return;
      try {
        const emsal = await lexisApi.emsalPuanla(dosya.dava.case_id, kayit.okuma.sha256);
        setEmsaller((onceki) => (onceki.some((e) => e.kayit.okuma.sha256 === kayit.okuma.sha256) ? onceki : [...onceki, emsal]));
      } catch (e) {
        setEmsalHatasi(hataMetni(e, "Emsal eklenemedi."));
      }
    },
    [dosya],
  );

  const denetle = useCallback(async () => {
    const hedef = taslakRef.current;
    if (!hedef) return;
    denetimSayaci.current += 1;
    const sira = denetimSayaci.current;
    setDenetleniyor(true);
    try {
      const sonuc = await lexisApi.denetle(hedef);
      if (sira !== denetimSayaci.current) return;
      setUyarilar(sonuc);
      setBayat(false);
      setDegisenMaddeler(new Set());
      setSonDenetim(saat());
    } catch (e) {
      if (sira === denetimSayaci.current && !iptalMi(e)) setAkisHatasi(hataMetni(e, "Denetim yapılamadı."));
    } finally {
      if (sira === denetimSayaci.current) setDenetleniyor(false);
    }
  }, []);

  const yaz = useCallback(async () => {
    if (!dosya) return;
    const bolumler = ISKELET_BOLUMLERI[dosya.iskelet];
    const istek: TaslakIstegi = {
      case_id: dosya.dava.case_id,
      sirket: dosya.sirket,
      rapor_turu: dosya.rapor_turu,
      iskelet: dosya.iskelet,
      belge_idleri: dosya.belgeler.filter((b) => seciliBelgeler.has(b.id)).map((b) => b.id),
      emsal_sha: emsaller.map((e) => e.kayit.okuma.sha256),
    };
    // Önce eski akış kesilir ve taslak sıfırlanır; yeni akışın denetçisi SONRA kurulur (sıfırlama onu kesmesin).
    taslagiSifirla();
    const ac = new AbortController();
    akisIstegi.current = ac;
    koy({
      case_id: istek.case_id,
      sirket: istek.sirket,
      rapor_turu: istek.rapor_turu,
      iskelet: istek.iskelet,
      etiketli: {},
      ozet: {},
      degerlendirme: null,
      muallak: null,
      muallak_maddi: null,
      muallak_manevi: null,
      emsaller: istek.emsal_sha,
    });
    setBolumDurumlari(Object.fromEntries(bolumler.map((b) => [b.kod, "yaziliyor"])) as BolumDurumlari);
    setAkis({ asama: "olgular", mesaj: null });

    const yazilmayanlariBosalt = () =>
      setBolumDurumlari((onceki) => Object.fromEntries(Object.entries(onceki).map(([k, d]) => [k, d === "yaziliyor" ? "bos" : d])) as BolumDurumlari);

    try {
      for await (const olay of lexisApi.taslakYaz(istek, ac.signal)) {
        if (ac.signal.aborted) break;
        const mevcut = taslakRef.current;
        if (!mevcut) break;
        if (olay.status === "info") {
          setAkis({ asama: olay.asama, mesaj: olay.mesaj });
        } else if (olay.status === "bolum") {
          koy({
            ...mevcut,
            etiketli: olay.etiketli ? { ...mevcut.etiketli, [olay.bolum]: olay.etiketli } : mevcut.etiketli,
            ozet: olay.ozet ? { ...mevcut.ozet, [olay.bolum]: olay.ozet } : mevcut.ozet,
            degerlendirme: olay.degerlendirme ?? mevcut.degerlendirme,
          });
          if (olay.degerlendirme) kimlikleriKoy(olay.degerlendirme.maddeler.map(yeniKimlik));
          setBolumDurumlari((onceki) => ({ ...onceki, [olay.bolum]: "yazildi" }));
        } else if (olay.status === "muallak") {
          koy({ ...mevcut, muallak: olay.oneri });
        } else if (olay.status === "complete") {
          setUyarilar(olay.uyarilar);
          setSonDenetim(saat());
        } else {
          setAkisHatasi(olay.error_ozet);
          yazilmayanlariBosalt();
        }
      }
    } catch (e) {
      yazilmayanlariBosalt();
      if (!iptalMi(e)) setAkisHatasi(hataMetni(e, "Taslak yazılamadı."));
    } finally {
      if (akisIstegi.current === ac) {
        akisIstegi.current = null;
        setAkis(null);
      }
    }
  }, [dosya, emsaller, seciliBelgeler, koy, kimlikleriKoy, taslagiSifirla, yeniKimlik]);

  const durdur = useCallback(() => akisIstegi.current?.abort(), []);

  /** Taslağı değiştirir, bölümü "düzenlendi" yapar ve denetimi bayatlatır. */
  const duzenle = useCallback(
    (bolum: BolumKodu, degistir: (t: LexisTaslak) => LexisTaslak) => {
      const mevcut = taslakRef.current;
      if (!mevcut) return;
      koy(degistir(mevcut));
      setBolumDurumlari((onceki) => ({ ...onceki, [bolum]: "duzenlendi" }));
      setBayat(true);
    },
    [koy],
  );

  const etiketliDegistir = useCallback(
    (bolum: BolumKodu, alan: string, deger: string) =>
      duzenle(bolum, (t) => ({
        ...t,
        etiketli: {
          ...t.etiketli,
          [bolum]: (t.etiketli[bolum] ?? []).map((s) => (s.alan === alan ? { ...s, deger: deger === "" ? null : deger, kaynak: deger === "" ? null : "ELLE" } : s)),
        },
      })),
    [duzenle],
  );

  const ozetDegistir = useCallback(
    (bolum: BolumKodu, degistir: (paragraflar: OzetParagraf[]) => OzetParagraf[]) =>
      duzenle(bolum, (t) => ({ ...t, ozet: { ...t.ozet, [bolum]: degistir(t.ozet[bolum] ?? []) } })),
    [duzenle],
  );

  const paragrafDegistir = useCallback(
    (bolum: BolumKodu, sira: number, metin: string) => ozetDegistir(bolum, (ps) => ps.map((p, i) => (i === sira ? { ...p, metin } : p))),
    [ozetDegistir],
  );

  const paragrafEkle = useCallback(
    (bolum: BolumKodu) => ozetDegistir(bolum, (ps) => [...ps, { metin: "", kaynak_belge_id: null }]),
    [ozetDegistir],
  );

  const paragrafSil = useCallback(
    (bolum: BolumKodu, sira: number) => {
      ozetDegistir(bolum, (ps) => ps.filter((_, i) => i !== sira));
      void denetle();
    },
    [ozetDegistir, denetle],
  );

  const degerlendirmeDegistir = useCallback(
    (degistir: (maddeler: Madde[]) => Madde[]) =>
      duzenle("degerlendirme", (t) => (t.degerlendirme ? { ...t, degerlendirme: { ...t.degerlendirme, maddeler: degistir(t.degerlendirme.maddeler) } } : t)),
    [duzenle],
  );

  const girisDegistir = useCallback(
    (giris: string) => duzenle("degerlendirme", (t) => (t.degerlendirme ? { ...t, degerlendirme: { ...t.degerlendirme, giris } } : t)),
    [duzenle],
  );

  const sulhDegistir = useCallback(
    (sulh_uygunluk: string) => duzenle("degerlendirme", (t) => (t.degerlendirme ? { ...t, degerlendirme: { ...t.degerlendirme, sulh_uygunluk } } : t)),
    [duzenle],
  );

  /** `sira` 1'den başlar. Tür değişikliği yapısaldır (hemen denetlenir); metin/dayanak düzenlemesi alandan çıkınca. */
  const maddeDegistir = useCallback(
    (sira: number, yama: Partial<Madde>) => {
      degerlendirmeDegistir((ms) => ms.map((m, i) => (i === sira - 1 ? { ...m, ...yama } : m)));
      const kimlik = kimliklerRef.current[sira - 1];
      if (kimlik) setDegisenMaddeler((onceki) => new Set(onceki).add(kimlik));
      if (yama.tur) void denetle();
    },
    [degerlendirmeDegistir, denetle],
  );

  /** Yeni madde sondaki muallak (KALIP) maddesinin önüne girer. */
  const maddeEkle = useCallback(() => {
    const maddeler = taslakRef.current?.degerlendirme?.maddeler;
    if (!maddeler) return;
    const sonKalip = maddeler.length > 0 && maddeler[maddeler.length - 1].tur === "KALIP";
    const yer = sonKalip ? maddeler.length - 1 : maddeler.length;
    const yeni: Madde = { metin: "", tur: "TESPIT", dayanak_bolum: null, dayanak_alinti: null };
    degerlendirmeDegistir((ms) => [...ms.slice(0, yer), yeni, ...ms.slice(yer)]);
    const kimlikler = [...kimliklerRef.current];
    kimlikler.splice(yer, 0, yeniKimlik());
    kimlikleriKoy(kimlikler);
    void denetle();
  }, [degerlendirmeDegistir, kimlikleriKoy, denetle, yeniKimlik]);

  const maddeSil = useCallback(
    (sira: number) => {
      degerlendirmeDegistir((ms) => ms.filter((_, i) => i !== sira - 1));
      kimlikleriKoy(kimliklerRef.current.filter((_, i) => i !== sira - 1));
      void denetle();
    },
    [degerlendirmeDegistir, kimlikleriKoy, denetle],
  );

  const maddeTasi = useCallback(
    (sira: number, yon: -1 | 1) => {
      const a = sira - 1;
      const b = a + yon;
      const takas = <T,>(dizi: T[]): T[] => {
        if (b < 0 || b >= dizi.length) return dizi;
        const kopya = [...dizi];
        [kopya[a], kopya[b]] = [kopya[b], kopya[a]];
        return kopya;
      };
      degerlendirmeDegistir(takas);
      kimlikleriKoy(takas(kimliklerRef.current));
      void denetle();
    },
    [degerlendirmeDegistir, kimlikleriKoy, denetle],
  );

  const muallakDegistir = useCallback(
    (yama: { maddi?: number | null; manevi?: number | null }) => {
      const mevcut = taslakRef.current;
      if (!mevcut) return;
      koy({
        ...mevcut,
        muallak_maddi: yama.maddi === undefined ? mevcut.muallak_maddi : yama.maddi,
        muallak_manevi: yama.manevi === undefined ? mevcut.muallak_manevi : yama.manevi,
      });
      void denetle();
    },
    [koy, denetle],
  );

  /** Alandan çıkınca: taslak değiştiyse yeniden denetle. */
  const alandanCikildi = useCallback(() => {
    if (bayat) void denetle();
  }, [bayat, denetle]);

  return {
    dosya,
    dosyaYukleniyor,
    dosyaHatasi,
    seciliBelgeler,
    emsaller,
    emsalYukleniyor,
    emsalHatasi,
    taslak,
    bolumDurumlari,
    akis,
    akisHatasi,
    uyarilar,
    bayat,
    denetleniyor,
    sonDenetim,
    maddeKimlikleri,
    degisenMaddeler,
    yaziliyor: akis !== null,
    davaSec,
    kunyeDegistir,
    belgeSec,
    emsalCikar,
    emsalEkle,
    yaz,
    durdur,
    denetle,
    alandanCikildi,
    etiketliDegistir,
    paragrafDegistir,
    paragrafEkle,
    paragrafSil,
    girisDegistir,
    sulhDegistir,
    maddeDegistir,
    maddeEkle,
    maddeSil,
    maddeTasi,
    muallakDegistir,
  };
}

export type Tezgah = ReturnType<typeof useTezgah>;
