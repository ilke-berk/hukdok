import { useCallback, useEffect, useRef, useState } from "react";
import { LexisApiError, lexisApi } from "@/lib/lexisApi";
import { tarihSaatYaz } from "@/lib/lexisMetin";
import {
  ISKELET_BOLUMLERI,
  type BolumKodu,
  type DosyaGirdisi,
  type Emsal,
  type KayitliTaslak,
  type KutuphaneKaydi,
  type LexisDava,
  type LexisTaslak,
  type LexisUyari,
  type Madde,
  type MuallakOnerisi,
  type OzetParagraf,
  type RafKarari,
  type TaslakIstegi,
  type TaslakKaydi,
  type UretimAsamasi,
  type YazimDurumu,
} from "@/types/lexis";
import type { BolumDurumu } from "./BolumGezgini";
import type { KunyeSecimi } from "./KunyeKarti";
import { hataMetni, iptalMi } from "./yardimcilar";

type BolumDurumlari = Partial<Record<BolumKodu, BolumDurumu>>;
export type MuallakSiniflari = Partial<Pick<MuallakOnerisi, "kusur_tespiti" | "risk_duzeyi" | "teminat">>;

/** Taslağın sunucudaki kaydının durumu (yalnız `lexisApi.kalici` iken `yok` dışına çıkar). */
export type KayitDurumu =
  | { tur: "yok" }
  | { tur: "kaydediliyor" }
  | { tur: "kaydedildi"; zaman: string }
  | { tur: "hata"; mesaj: string }
  /** Taslak başka oturumda değişmiş: bu oturum artık YAZMAZ (davayı yeniden seçince kayıtlı hâli açılır). */
  | { tur: "cakisma"; mesaj: string };

/** Son değişiklikten bu kadar sonra kaydedilir (ms); dava değişiminde ve sayfadan çıkışta beklenmez. */
export const KAYIT_GECIKMESI = 1200;
let kayitGecikmesi = KAYIT_GECIKMESI;

/** Test yardımcısı: otomatik kaydın gecikmesi (ms). */
export function kayitGecikmesiAyarla(ms: number): void {
  kayitGecikmesi = ms;
}

type KayitGovdesi = Omit<TaslakKaydi, "kosu_id" | "surum">;
/** Dava başına kayıt bağlamı: okunan sürüm, son kaydedilen gövdenin izi, yazma kilidi (çakışmadan sonra). */
interface KayitBaglami {
  surum: number | null;
  son: string | null;
  kilitli: boolean;
}

const saat = () => new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });

const sirali = (idler: Iterable<number>) => [...idler].sort((a, b) => a - b);

function kayitGovdesi(taslak: LexisTaslak, durumlar: BolumDurumlari, secili: Iterable<number>, seciliKararlar: Iterable<number>, uyariSayisi: number): KayitGovdesi {
  return { taslak, ekran: { bolum_durumlari: durumlar, secili_belgeler: sirali(secili), secili_kararlar: sirali(seciliKararlar) }, uyari_sayisi: uyariSayisi };
}

/** Henüz hiçbir bölümü gelmemiş taslak (yarıda kesilen yazım) kaydedilmez: kayıtlı hâlin üzerine boş kabuk yazılmasın. */
const bosKabuk = (t: LexisTaslak) => t.degerlendirme === null && Object.keys(t.etiketli).length === 0 && Object.keys(t.ozet).length === 0;

/**
 * "Rapor yaz" tezgâhının durumu ve eylemleri. Sıra: dava seç → dosya (künye + belgeler) ve emsaller gelir →
 * `yaz` akışı bölümleri doldurur → insan düzenler → `denetle` uyarıları yeniler.
 *
 * - Taslağın güncel hâli `taslakRef`'te de tutulur: olay işleyicileri art arda geldiğinde (yaz → çık) state'in
 *   bir önceki render'ına bakmasınlar diye. Her yazma `koy` üzerinden geçer.
 * - Metin düzenlemesi denetimi BAYATLATIR (madde "denetlenmedi" görünür); alandan çıkınca ya da yapısal
 *   değişiklikte (madde ekle/sil/taşı) yeniden denetlenir. Geç gelen eski denetim cevabı yok sayılır.
 * - KARARLAR: dava seçilince karta bağlı kararlar karar rafından gelir (`lexisApi.kartKararlari`). Servis kararlardan
 *   yazımı açmışsa seçili kararlar `yaz` isteğiyle gider (özet + değerlendirme modelden); kapalıysa liste yalnız
 *   okunur, taslak iskelettir. Taslak yazıldığı kararları taşır (`kararlar`): denetim alıntıyı onlarda arar.
 * - KALICILIK (`lexisApi.kalici`, gerçek dava kipi): dava seçilince kayıtlı taslak varsa künyesi, bölüm durumları,
 *   belge seçimi ve emsalleriyle geri açılır. Taslak her değişiklikten `KAYIT_GECIKMESI` sonra okunan sürümle
 *   kaydedilir; dava değişiminde ve sayfadan çıkışta bekleyen kayıt hemen gönderilir. Kayıtlar sıraya girer (aynı
 *   davanın iki yazması yarışmaz). Sunucu 409 dönerse (başka oturum yazmış) bu oturum o davaya artık yazmaz.
 *   Örnek kipte hiçbiri çalışmaz.
 */
export function useTezgah() {
  const [dosya, setDosya] = useState<DosyaGirdisi | null>(null);
  const [dosyaYukleniyor, setDosyaYukleniyor] = useState(false);
  const [dosyaHatasi, setDosyaHatasi] = useState<string | null>(null);
  const [seciliBelgeler, setSeciliBelgeler] = useState<ReadonlySet<number>>(new Set());
  const [emsaller, setEmsaller] = useState<Emsal[]>([]);
  const [emsalYukleniyor, setEmsalYukleniyor] = useState(false);
  const [emsalHatasi, setEmsalHatasi] = useState<string | null>(null);
  // Dava kartına bağlı kararlar (karar rafından) ve kararlardan yazımın bu kurulumda açık olup olmadığı.
  const [kararlar, setKararlar] = useState<RafKarari[]>([]);
  const [kararYukleniyor, setKararYukleniyor] = useState(false);
  const [kararHatasi, setKararHatasi] = useState<string | null>(null);
  const [seciliKararlar, setSeciliKararlar] = useState<ReadonlySet<number>>(new Set());
  const [yazimDurumu, setYazimDurumu] = useState<YazimDurumu | null>(null);

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

  const [kayit, setKayit] = useState<KayitDurumu>({ tur: "yok" });
  const [geriYukleniyor, setGeriYukleniyor] = useState(false);
  const [acilanKayit, setAcilanKayit] = useState<Pick<KayitliTaslak, "guncelleyen" | "guncelleme"> | null>(null);

  const taslakRef = useRef<LexisTaslak | null>(null);
  const kimliklerRef = useRef<string[]>([]);
  const dosyaIstegi = useRef<AbortController | null>(null);
  const emsalIstegi = useRef<AbortController | null>(null);
  const kararIstegi = useRef<AbortController | null>(null);
  const akisIstegi = useRef<AbortController | null>(null);
  const denetimSayaci = useRef(0);
  const kimlikSayaci = useRef(0);

  const baglamlar = useRef(new Map<number, KayitBaglami>());
  const etkinDava = useRef<number | null>(null);
  const bekleyenKayit = useRef<{ caseId: number; govde: KayitGovdesi; iz: string } | null>(null);
  const sonGovde = useRef<{ caseId: number; govde: KayitGovdesi; iz: string } | null>(null);
  const kayitZamanlayici = useRef<ReturnType<typeof setTimeout> | null>(null);
  const kayitKuyrugu = useRef<Promise<void>>(Promise.resolve());

  /** Kaydı sıraya koyar. Geç gelen cevap yalnız ekran hâlâ o davayı gösteriyorsa durumu değiştirir. */
  const gonder = useCallback((b: { caseId: number; govde: KayitGovdesi; iz: string }) => {
    sonGovde.current = b;
    kayitKuyrugu.current = kayitKuyrugu.current.then(async () => {
      const baglam = baglamlar.current.get(b.caseId);
      if (!baglam || baglam.kilitli || baglam.son === b.iz) return;
      const ekranda = () => etkinDava.current === b.caseId;
      if (ekranda()) setKayit({ tur: "kaydediliyor" });
      try {
        const sonuc = await lexisApi.taslakKaydet(b.caseId, { ...b.govde, surum: baglam.surum });
        if (!sonuc) return;
        baglam.surum = sonuc.surum;
        baglam.son = b.iz;
        if (ekranda()) setKayit({ tur: "kaydedildi", zaman: saat() });
      } catch (e) {
        const cakisma = e instanceof LexisApiError && e.status === 409;
        if (cakisma) baglam.kilitli = true;
        if (ekranda()) setKayit(cakisma ? { tur: "cakisma", mesaj: hataMetni(e) } : { tur: "hata", mesaj: hataMetni(e, "Taslak kaydedilemedi.") });
      }
    });
  }, []);

  /** Bekleyen (gecikmeli) kaydı hemen gönderir. */
  const kaydiBosalt = useCallback(() => {
    if (kayitZamanlayici.current) clearTimeout(kayitZamanlayici.current);
    kayitZamanlayici.current = null;
    const bekleyen = bekleyenKayit.current;
    bekleyenKayit.current = null;
    if (bekleyen) gonder(bekleyen);
  }, [gonder]);

  const bekleyeniIptalEt = useCallback(() => {
    if (kayitZamanlayici.current) clearTimeout(kayitZamanlayici.current);
    kayitZamanlayici.current = null;
    bekleyenKayit.current = null;
  }, []);

  /** Kayıt hatasından sonra son gövdeyi yeniden gönderir. */
  const yenidenKaydet = useCallback(() => {
    if (sonGovde.current && etkinDava.current === sonGovde.current.caseId) gonder(sonGovde.current);
  }, [gonder]);

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

  // Sayfadan çıkışta süren istekler kesilir; bekleyen kayıt beklemeden gönderilir.
  useEffect(
    () => () => {
      dosyaIstegi.current?.abort();
      emsalIstegi.current?.abort();
      kararIstegi.current?.abort();
      akisIstegi.current?.abort();
      kaydiBosalt();
    },
    [kaydiBosalt],
  );

  // Otomatik kayıt: taslak, bölüm durumu, belge seçimi ya da uyarı sayısı değişince, yazım akışı ve geri yükleme
  // bittikten sonra. Son kaydedilenle aynı gövde yeniden gönderilmez.
  useEffect(() => {
    if (!lexisApi.kalici || !taslak || akis !== null || geriYukleniyor || bosKabuk(taslak)) return;
    const baglam = baglamlar.current.get(taslak.case_id);
    if (!baglam || baglam.kilitli) return;
    const govde = kayitGovdesi(taslak, bolumDurumlari, seciliBelgeler, seciliKararlar, uyarilar.length);
    const iz = JSON.stringify(govde);
    if (kayitZamanlayici.current) clearTimeout(kayitZamanlayici.current);
    kayitZamanlayici.current = null;
    if (iz === baglam.son) {
      bekleyenKayit.current = null;
      return;
    }
    bekleyenKayit.current = { caseId: taslak.case_id, govde, iz };
    kayitZamanlayici.current = setTimeout(kaydiBosalt, kayitGecikmesi);
  }, [taslak, bolumDurumlari, seciliBelgeler, seciliKararlar, uyarilar, akis, geriYukleniyor, kaydiBosalt]);

  /**
   * Davanın kararlarını ve yazım durumunu yükler. `varsayilanSec`: yazım açıksa mahkeme kararlarının hepsi seçili
   * gelir (kayıtlı taslak açılırken seçim kayıttan gelir, dokunulmaz). Hata dosyayı engellemez: liste boş kalır.
   */
  const kararlariYukle = useCallback((caseId: number, varsayilanSec: boolean) => {
    kararIstegi.current?.abort();
    const ac = new AbortController();
    kararIstegi.current = ac;
    setKararYukleniyor(true);
    setKararHatasi(null);
    lexisApi
      .kartKararlari(caseId, ac.signal)
      .then((sonuc) => {
        setKararlar(sonuc.kararlar);
        setYazimDurumu(sonuc.yazim);
        if (varsayilanSec) setSeciliKararlar(new Set(sonuc.yazim.acik ? sonuc.kararlar.filter((k) => k.belge_turu === "karar").map((k) => k.id) : []));
      })
      .catch((e: unknown) => {
        if (!iptalMi(e)) setKararHatasi(hataMetni(e, "Kararlar alınamadı."));
      })
      .finally(() => {
        if (!ac.signal.aborted) setKararYukleniyor(false);
      });
  }, []);

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

  /** Denetimi koşar; sonucu (geç kalmış ya da başarısızsa `null`) döner. */
  const denetle = useCallback(async (): Promise<LexisUyari[] | null> => {
    const hedef = taslakRef.current;
    if (!hedef) return null;
    denetimSayaci.current += 1;
    const sira = denetimSayaci.current;
    setDenetleniyor(true);
    try {
      const sonuc = await lexisApi.denetle(hedef);
      if (sira !== denetimSayaci.current) return null;
      setUyarilar(sonuc);
      setBayat(false);
      setDegisenMaddeler(new Set());
      setSonDenetim(saat());
      return sonuc;
    } catch (e) {
      if (sira === denetimSayaci.current && !iptalMi(e)) setAkisHatasi(hataMetni(e, "Denetim yapılamadı."));
      return null;
    } finally {
      if (sira === denetimSayaci.current) setDenetleniyor(false);
    }
  }, []);

  /**
   * Kayıtlı taslağı ekrana geri kurar: künye seçimi (şirket, tür, iskelet) taslaktaki hâliyle, bölüm durumları ve
   * belge seçimi kayıttan, emsaller taslağın baktığı raporlardan (kütüphaneden yeniden puanlanarak). Denetim
   * yeniden koşar; geri kurulan hâl "son kaydedilen" sayılır (açmak tek başına yeni sürüm yazmaz).
   */
  const geriYukle = useCallback(
    async (d: DosyaGirdisi, kayitli: KayitliTaslak, signal: AbortSignal) => {
      const t = kayitli.taslak;
      const caseId = d.dava.case_id;
      const mevcut = new Set(d.belgeler.map((b) => b.id));
      const secili = new Set((kayitli.ekran.secili_belgeler ?? [...mevcut]).filter((id) => mevcut.has(id)));
      // Karar seçimi kayıttan: yazımda seçili bırakılanlar, yoksa taslağın yazıldığı kararlar.
      const seciliKarar = new Set(kayitli.ekran.secili_kararlar ?? t.kararlar ?? []);
      const durumlar = Object.fromEntries(
        ISKELET_BOLUMLERI[t.iskelet].map((b) => {
          const kayitliDurum = kayitli.ekran.bolum_durumlari?.[b.kod];
          return [b.kod, kayitliDurum === "bos" || kayitliDurum === "duzenlendi" ? kayitliDurum : "yazildi"];
        }),
      ) as BolumDurumlari;

      setGeriYukleniyor(true);
      baglamlar.current.set(caseId, { surum: kayitli.surum, son: null, kilitli: false });
      setDosya({ ...d, sirket: t.sirket, rapor_turu: t.rapor_turu, iskelet: t.iskelet });
      setSeciliBelgeler(secili);
      setSeciliKararlar(seciliKarar);
      kararlariYukle(caseId, false);
      setBolumDurumlari(durumlar);
      koy(t);
      kimlikleriKoy((t.degerlendirme?.maddeler ?? []).map(yeniKimlik));
      setEmsalYukleniyor(true);
      try {
        const sonuclar = await Promise.allSettled(t.emsaller.map((sha) => lexisApi.emsalPuanla(caseId, sha, signal)));
        if (signal.aborted) return;
        const bulunan = sonuclar.flatMap((s) => (s.status === "fulfilled" ? [s.value] : []));
        setEmsaller(bulunan);
        if (bulunan.length < sonuclar.length) setEmsalHatasi(`Taslağın baktığı ${sonuclar.length - bulunan.length} emsal rapor kütüphaneden alınamadı.`);
        setEmsalYukleniyor(false);
        const uyarilar = await denetle();
        if (signal.aborted) return;
        const baglam = baglamlar.current.get(caseId);
        if (baglam) baglam.son = JSON.stringify(kayitGovdesi(t, durumlar, secili, seciliKarar, uyarilar?.length ?? 0));
        setKayit({ tur: "kaydedildi", zaman: tarihSaatYaz(kayitli.guncelleme) });
        setAcilanKayit({ guncelleyen: kayitli.guncelleyen, guncelleme: kayitli.guncelleme });
      } finally {
        if (!signal.aborted) setGeriYukleniyor(false);
      }
    },
    [denetle, kararlariYukle, koy, kimlikleriKoy, yeniKimlik],
  );

  const davaSec = useCallback(
    (dava: LexisDava | null) => {
      dosyaIstegi.current?.abort();
      emsalIstegi.current?.abort();
      kararIstegi.current?.abort();
      kaydiBosalt(); // önceki davanın bekleyen kaydı beklemeden gider
      etkinDava.current = dava?.case_id ?? null;
      taslagiSifirla();
      setDosya(null);
      setDosyaHatasi(null);
      setEmsaller([]);
      setEmsalHatasi(null);
      setEmsalYukleniyor(false);
      setSeciliBelgeler(new Set());
      setKararlar([]);
      setKararHatasi(null);
      setKararYukleniyor(false);
      setSeciliKararlar(new Set());
      setYazimDurumu(null);
      setKayit({ tur: "yok" });
      setAcilanKayit(null);
      setGeriYukleniyor(false);
      if (!dava) {
        setDosyaYukleniyor(false);
        return;
      }
      const ac = new AbortController();
      dosyaIstegi.current = ac;
      setDosyaYukleniyor(true);
      lexisApi
        .dosyaGetir(dava.case_id, ac.signal)
        .then(async (d) => {
          let kayitli: KayitliTaslak | null = null;
          let okumaHatasi: string | null = null;
          if (lexisApi.kalici) {
            try {
              kayitli = await lexisApi.taslakGetir(dava.case_id, ac.signal);
            } catch (e) {
              if (iptalMi(e)) throw e;
              okumaHatasi = hataMetni(e, "Kayıtlı taslak okunamadı.");
            }
            if (ac.signal.aborted) return;
          }
          if (kayitli) {
            setDosyaYukleniyor(false);
            await geriYukle(d, kayitli, ac.signal);
            return;
          }
          // Kayıt yok (ya da okunamadı): sürümsüz bağlam. Sunucuda kayıt varsa ilk yazma 409 alır, üzerine yazılmaz.
          if (lexisApi.kalici) baglamlar.current.set(dava.case_id, { surum: null, son: null, kilitli: false });
          if (okumaHatasi) setKayit({ tur: "hata", mesaj: `Kayıtlı taslak okunamadı: ${okumaHatasi}` });
          setDosya(d);
          setSeciliBelgeler(new Set(d.belgeler.map((b) => b.id)));
          emsalleriYukle(d);
          kararlariYukle(dava.case_id, true);
        })
        .catch((e: unknown) => {
          if (!iptalMi(e)) setDosyaHatasi(hataMetni(e, "Dosya alınamadı."));
        })
        .finally(() => {
          if (!ac.signal.aborted) setDosyaYukleniyor(false);
        });
    },
    [emsalleriYukle, geriYukle, kararlariYukle, kaydiBosalt, taslagiSifirla],
  );

  /** Şirket / tür / iskelet seçimi. Yazılmış taslağı siler (çağıran önce onay alır); şirket ya da tür değişince emsaller yeniden aranır. */
  const kunyeDegistir = useCallback(
    (secim: KunyeSecimi) => {
      if (!dosya) return;
      const yeni: DosyaGirdisi = { ...dosya, ...secim };
      // Ek rapor yalnız EK iskeletiyle yazılır; ana rapora dönülünce EK iskeleti bırakılır.
      if (secim.rapor_turu === "EK" && !secim.iskelet) yeni.iskelet = "EK";
      if (secim.rapor_turu === "ANA" && !secim.iskelet && dosya.iskelet === "EK") yeni.iskelet = "KISA";
      // Kayıtlı taslak da silinir (kullanıcı onayladı): yoksa sayfa yenilenince eski künyeyle geri gelirdi.
      const caseId = dosya.dava.case_id;
      // Henüz gönderilmemiş kayıt iptal edilir; silme, sıradaki (süren) kaydın ARKASINA girer.
      if (lexisApi.kalici && (taslakRef.current || baglamlar.current.get(caseId)?.surum != null)) {
        bekleyeniIptalEt();
        kayitKuyrugu.current = kayitKuyrugu.current.then(async () => {
          try {
            await lexisApi.taslakSil(caseId);
            baglamlar.current.set(caseId, { surum: null, son: null, kilitli: false });
            if (etkinDava.current === caseId) setKayit({ tur: "yok" });
          } catch (e) {
            if (etkinDava.current === caseId) setKayit({ tur: "hata", mesaj: hataMetni(e, "Kayıtlı taslak silinemedi.") });
          }
        });
      }
      setDosya(yeni);
      taslagiSifirla();
      if (yeni.sirket !== dosya.sirket || yeni.rapor_turu !== dosya.rapor_turu) emsalleriYukle(yeni);
    },
    [bekleyeniIptalEt, dosya, emsalleriYukle, taslagiSifirla],
  );

  const belgeSec = useCallback((id: number, secili: boolean) => {
    setSeciliBelgeler((onceki) => {
      const yeni = new Set(onceki);
      if (secili) yeni.add(id);
      else yeni.delete(id);
      return yeni;
    });
  }, []);

  const kararSec = useCallback((id: number, secili: boolean) => {
    setSeciliKararlar((onceki) => {
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
      // Kararlardan yazım yalnız servis açmışsa: kapalıyken seçim gönderilmez, taslak iskelet gelir.
      karar_idleri: yazimDurumu?.acik ? kararlar.filter((k) => seciliKararlar.has(k.id)).map((k) => k.id) : [],
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
      kararlar: istek.karar_idleri ?? [],
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
        } else if (olay.status === "warning") {
          setAkisHatasi(olay.mesaj); // akış sürer: kararlardan yazım yapılamadı, iskelet geliyor
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
  }, [dosya, emsaller, kararlar, seciliBelgeler, seciliKararlar, yazimDurumu, koy, kimlikleriKoy, taslagiSifirla, yeniKimlik]);

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

  /** Sınıf değişince öneri yeniden hesaplatılır (tutarı kod belirler, K11); kesin tutarlara dokunulmaz. */
  const muallakSinifDegistir = useCallback(
    async (yama: MuallakSiniflari) => {
      const mevcut = taslakRef.current;
      if (!mevcut?.muallak) return;
      const { kusur_tespiti, risk_duzeyi, teminat } = { ...mevcut.muallak, ...yama };
      try {
        const oneri = await lexisApi.muallakOner({ case_id: mevcut.case_id, sirket: mevcut.sirket, kusur_tespiti, risk_duzeyi, teminat });
        const guncel = taslakRef.current;
        if (!guncel || guncel.case_id !== mevcut.case_id) return;
        koy({ ...guncel, muallak: oneri });
        void denetle();
      } catch (e) {
        if (!iptalMi(e)) setAkisHatasi(hataMetni(e, "Muallak önerisi alınamadı."));
      }
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
    kararlar,
    kararYukleniyor,
    kararHatasi,
    seciliKararlar,
    yazimDurumu,
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
    kayit,
    geriYukleniyor,
    acilanKayit,
    yenidenKaydet,
    davaSec,
    kunyeDegistir,
    belgeSec,
    kararSec,
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
    muallakSinifDegistir,
  };
}

export type Tezgah = ReturnType<typeof useTezgah>;
