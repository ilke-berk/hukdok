import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Download, Plus, Search, Square } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { LexisApiError, lexisApi } from "@/lib/lexisApi";
import {
  BELGE_TURU_ADLARI,
  EMSAL_ASAMALARI,
  emsalBelgesiMi,
  gosterilecekOneriler,
  type EmsalAkisOlayi,
  type EmsalAsamasi,
  type EmsalBelge,
  type EmsalDurumu,
  type EmsalOnerisi,
  type EmsalSonucu,
  type LexisBelge,
} from "@/types/lexis";
import { EmsalKararListesi } from "./EmsalKararListesi";
import { Rozet } from "./ortak";
import { BAGLANTI_SINIFI, hataMetni, iptalMi } from "./yardimcilar";

type EmsalBulDiyaloguProps = {
  acik: boolean;
  /** Kart belgesi seçilebilen dava; rafta `null` (yalnız dosya yüklenir). */
  caseId: number | null;
  /** Kartın belge listesi (`BelgeListesi` verisi); yalnız pdf / docx / udf olanlar seçilebilir. */
  belgeler: LexisBelge[];
  /** Belge satırındaki düğmeyle açıldıysa o belge seçili gelir. */
  baslangicBelgeId?: number | null;
  /** Taslakta zaten olan emsal kararlar: satır işaretli ve kilitli. */
  mevcutKararlar?: ReadonlySet<number>;
  /** Verilirse seçilenler taslağa biner (`useTezgah.emsalKarariEkle`); rafta yok. */
  onTaslagaEkle?: (kararlar: EmsalOnerisi[]) => void;
  /** "Kararı aç" — çağıran `KararOkuyucu`'yu açar (yalnız kimlik). */
  onKararAc: (id: number) => void;
  onKapat: () => void;
};

type Adim = "kaynak" | "belge" | "arama" | "sonuc";

const KAPALI_NEDENLERI: Record<string, string> = {
  anahtar_yok: "Servisin model anahtarı tanımlı değil (GEMINI_API_KEY).",
  paket_yok: "Servis imajında model paketi yok.",
  kip_gecersiz: "Servisin emsal kipi tanınmıyor (LEXIS_EMSAL_MODEL).",
};

const ADIM_SIRASI: readonly Adim[] = ["kaynak", "belge", "arama", "sonuc"];
const ADIM_ADLARI: Record<Adim, string> = { kaynak: "Kaynak", belge: "Belge", arama: "Arama", sonuc: "Sonuç" };

const boyutYaz = (n: number) => (n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / (1024 * 1024)).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`);

/** `info` olayının mesajı yoksa alanlarından kurulur. */
function asamaMesaji(olay: Extract<EmsalAkisOlayi, { status: "info" }>): string {
  if (olay.mesaj) return olay.mesaj;
  switch (olay.asama) {
    case "kunye":
      return `Künye ${olay.kaynak === "onbellek" ? "önbellekten alındı" : "üretildi"}${olay.sorgu !== undefined ? ` · ${olay.sorgu} sorgu` : ""}`;
    case "aday":
      return `${olay.aday ?? 0} aday toplandı${olay.ayni_kart ? ` (${olay.ayni_kart} aynı kart)` : ""}`;
    case "okuma":
      return olay.kaynak === "onbellek" ? "Okuma önbellekten" : "Adaylar okunuyor";
    case "denetim":
      return `Denetim: ${olay.gecen ?? 0} geçti, ${olay.dusen ?? 0} düştü`;
  }
}

const DIYALOG_SINIFI = "theme-classic max-w-3xl max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none text-[var(--fg)]";

/**
 * "Bu dosyaya emsal bul" (K27): dört adım — 1 kaynak (kart belgesi ya da dosya), 2 belge özeti + maske dökümü +
 * model rozeti (sahte üretici / Gemini — gönderim onayı, K4), 3 ilerleme (NDJSON `info` / `warning`), 4 gerekçeli
 * sonuç listesi → "Taslağa ekle" (K28: yazıma gitmez) ve "İnceleme paketini indir" (G263; uç yoksa 404 → pasif).
 *
 * Portal kabuğun dışında olduğundan `theme-classic` taşır; odak tuzağı ve `role=dialog` Radix'ten (diğer Lexis
 * diyaloglarıyla aynı kalıp). Her açılışta durum sıfırdan kurulur (`acik` kapanınca gövde sökülür).
 */
export function EmsalBulDiyalogu(props: EmsalBulDiyaloguProps) {
  const { acik, onKapat } = props;
  return (
    <Dialog open={acik} onOpenChange={(o) => !o && onKapat()}>
      {acik && (
        <DialogContent className={DIYALOG_SINIFI} data-testid="lexis-emsal-bul">
          <Govde {...props} />
        </DialogContent>
      )}
    </Dialog>
  );
}

function Govde({ caseId, belgeler, baslangicBelgeId = null, mevcutKararlar, onTaslagaEkle, onKararAc, onKapat }: EmsalBulDiyaloguProps) {
  const uygunBelgeler = useMemo(() => (caseId !== null ? belgeler.filter((b) => emsalBelgesiMi(b.ad)) : []), [belgeler, caseId]);
  const [adim, setAdim] = useState<Adim>("kaynak");
  const [secilenBelge, setSecilenBelge] = useState<number | null>(uygunBelgeler.some((b) => b.id === baslangicBelgeId) ? baslangicBelgeId : null);
  const [dosya, setDosya] = useState<File | null>(null);
  const [hazirlaniyor, setHazirlaniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [belge, setBelge] = useState<EmsalBelge | null>(null);
  const [durum, setDurum] = useState<EmsalDurumu | null>(null);
  const [durumHatasi, setDurumHatasi] = useState<string | null>(null);
  const [onay, setOnay] = useState(false);
  const [akis, setAkis] = useState<{ asama: EmsalAsamasi; ilerleme: [number, number] | null; mesaj: string }>({ asama: "kunye", ilerleme: null, mesaj: "Arama başlatılıyor…" });
  const [uyarilar, setUyarilar] = useState<string[]>([]);
  const [sonuc, setSonuc] = useState<EmsalSonucu | null>(null);
  const [secili, setSecili] = useState<ReadonlySet<number>>(new Set());
  const [indiriliyor, setIndiriliyor] = useState(false);
  const [indirmePasif, setIndirmePasif] = useState<string | null>(null);
  const [indirmeMesaji, setIndirmeMesaji] = useState<string | null>(null);
  const istek = useRef<AbortController | null>(null);

  useEffect(() => () => istek.current?.abort(), []);

  const yeniIstek = () => {
    istek.current?.abort();
    const ac = new AbortController();
    istek.current = ac;
    return ac;
  };

  const hazirla = async () => {
    if (secilenBelge === null && !dosya) return;
    const ac = yeniIstek();
    setHazirlaniyor(true);
    setHata(null);
    try {
      const [kayit, hat] = await Promise.all([
        secilenBelge !== null && caseId !== null ? lexisApi.emsalBelgeKarttan(caseId, secilenBelge, ac.signal) : lexisApi.emsalBelgeYukle(dosya!, caseId, ac.signal),
        // Hat durumu alınamazsa belge özeti yine gösterilir; "Ara" pasif kalır, neden yazılır.
        lexisApi
          .emsalDurum(ac.signal)
          .then((d) => ({ durum: d, hata: null as string | null }))
          .catch((e: unknown) => {
            if (iptalMi(e)) throw e;
            return { durum: null, hata: hataMetni(e, "Emsal hattının durumu alınamadı.") };
          }),
      ]);
      if (ac.signal.aborted) return;
      setBelge(kayit);
      setDurum(hat.durum);
      setDurumHatasi(hat.hata);
      setOnay(false);
      setAdim("belge");
    } catch (e) {
      if (!iptalMi(e)) setHata(hataMetni(e, "Belge hazırlanamadı."));
    } finally {
      if (!ac.signal.aborted) setHazirlaniyor(false);
    }
  };

  const ara = async () => {
    if (!belge) return;
    const ac = yeniIstek();
    setAdim("arama");
    setHata(null);
    setUyarilar([]);
    setSonuc(null);
    setSecili(new Set());
    setIndirmePasif(null);
    setIndirmeMesaji(null);
    setAkis({ asama: "kunye", ilerleme: null, mesaj: "Arama başlatılıyor…" });
    try {
      for await (const olay of lexisApi.emsalAra(belge.sha256, { signal: ac.signal })) {
        if (ac.signal.aborted) break;
        if (olay.status === "info") {
          setAkis({ asama: olay.asama, ilerleme: olay.ilerleme ?? null, mesaj: asamaMesaji(olay) });
        } else if (olay.status === "warning") {
          setUyarilar((onceki) => [...onceki, olay.message]);
        } else if (olay.status === "complete") {
          const { status: _durum, ...govde } = olay;
          setSonuc(govde);
          setAdim("sonuc");
        } else {
          // `failed` SON olaydır: belge adımına dönülür, neden orada görünür; "Ara" yeniden denenebilir.
          setHata(olay.error_ozet);
          setAdim("belge");
        }
      }
      if (ac.signal.aborted) setAdim("belge");
    } catch (e) {
      setAdim("belge");
      if (!iptalMi(e)) setHata(hataMetni(e, "Emsal araması tamamlanamadı."));
    }
  };

  const durdur = () => {
    istek.current?.abort();
    setAdim("belge");
  };

  const indir = async () => {
    if (!sonuc || indiriliyor) return;
    setIndiriliyor(true);
    setIndirmeMesaji(null);
    try {
      const ad = await lexisApi.emsalIndir(sonuc.sha256);
      setIndirmeMesaji(`${ad} indirildi.`);
    } catch (e) {
      if (iptalMi(e)) return;
      // 404: sonuç yok ya da indirme ucu bu kurulumda yok — düğme pasifleşir, sebep yazılır.
      if (e instanceof LexisApiError && e.status === 404) setIndirmePasif(e.message);
      else setIndirmeMesaji(hataMetni(e, "İnceleme paketi indirilemedi."));
    } finally {
      setIndiriliyor(false);
    }
  };

  const sec = (id: number, isaretli: boolean) =>
    setSecili((onceki) => {
      const yeni = new Set(onceki);
      if (isaretli) yeni.add(id);
      else yeni.delete(id);
      return yeni;
    });

  const taslagaEkle = () => {
    if (!sonuc || !onTaslagaEkle) return;
    const secilenler = gosterilecekOneriler(sonuc.oneriler).filter((o) => secili.has(o.id) && !(mevcutKararlar?.has(o.id) ?? false));
    if (secilenler.length === 0) return;
    onTaslagaEkle(secilenler);
    onKapat();
  };

  const gemini = durum?.kip === "gemini";
  const hatAcik = durum?.acik === true;
  const arayabilir = hatAcik && (!gemini || onay);
  const adimSirasi = ADIM_SIRASI.indexOf(adim);
  const gorunenOneriler = sonuc ? gosterilecekOneriler(sonuc.oneriler) : [];
  const secilebilir = gorunenOneriler.filter((o) => secili.has(o.id) && !(mevcutKararlar?.has(o.id) ?? false)).length;

  return (
    <>
      <DialogHeader>
        <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">Bu dosyaya emsal bul</DialogTitle>
        <DialogDescription className="text-[12.5px] leading-[1.55] text-[var(--fg-muted)]">
          Belgenin metni Lexis servisinde çıkarılıp kişi adları maskelenir; ajan büro karar arşivinde aday toplar, okuyup puanlar, alıntıyı kaynak kararda
          doğrular. Onayladığınız kararlar taslağın emsal listesine biner; yazıma girmez, Word'de künye satırı olur.
        </DialogDescription>
      </DialogHeader>

      <ol className="flex flex-wrap items-center gap-x-1 gap-y-1" aria-label="Adımlar">
        {ADIM_SIRASI.map((a, i) => {
          const gecti = i < adimSirasi;
          const suren = i === adimSirasi;
          return (
            <li key={a} className="flex items-center gap-1">
              <span
                aria-current={suren ? "step" : undefined}
                className={[
                  "inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] tracking-[0.16em] uppercase",
                  gecti ? "text-[var(--fg-muted)]" : suren ? "text-[var(--fg)] font-semibold border-b-2 border-[var(--brand)]" : "text-[var(--fg-subtle)]",
                ].join(" ")}
              >
                {gecti ? <Check className="w-3 h-3" strokeWidth={2.2} aria-hidden="true" /> : <span className="tabular-nums">0{i + 1}</span>}
                {ADIM_ADLARI[a]}
              </span>
              {i < ADIM_SIRASI.length - 1 && <span className="h-px w-3 bg-[var(--border-strong)]" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>

      {hata && (
        <p role="alert" data-testid="lexis-emsal-hata" className="border border-tone-danger/40 bg-tone-danger/10 px-3 py-2 text-[12.5px] text-tone-danger">
          {hata}
        </p>
      )}

      {adim === "kaynak" && (
        <div data-testid="lexis-emsal-kaynak" className="grid gap-3">
          {caseId !== null && (
            <fieldset className="grid gap-1 min-w-0">
              <legend className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)] mb-1">Kart belgesi</legend>
              {uygunBelgeler.length === 0 && <p className="text-[12.5px] text-[var(--fg-muted)]">Kartta PDF, DOCX ya da UDF belge yok; dosyayı aşağıdan seçin.</p>}
              {uygunBelgeler.map((b) => (
                <label key={b.id} className="flex items-start gap-2.5 px-2 py-1.5 -mx-2 rounded-[3px] hover:bg-[var(--bg-sunken)] cursor-pointer">
                  <input
                    type="radio"
                    name="lexis-emsal-kaynak"
                    className="mt-[3px] accent-[var(--brand)]"
                    checked={secilenBelge === b.id}
                    onChange={() => {
                      setSecilenBelge(b.id);
                      setDosya(null);
                    }}
                  />
                  <span className="min-w-0">
                    <span className="block text-[13px] text-[var(--fg)] leading-[1.4]">{b.ad}</span>
                    <span className="block text-[11.5px] text-[var(--fg-subtle)]">{[BELGE_TURU_ADLARI[b.tur], b.sayfa !== null && `${b.sayfa} sayfa`].filter(Boolean).join(" · ")}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          <label className="grid gap-1">
            <span className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)]">{caseId !== null ? "Ya da dosya seç" : "Dosya seç"}</span>
            <input
              type="file"
              accept=".pdf,.docx,.udf"
              aria-label="Dosya seç"
              className="text-[12.5px] text-[var(--fg)] file:mr-3 file:h-8 file:px-3 file:border file:border-[var(--border)] file:bg-[var(--bg)] file:text-[12.5px] file:text-[var(--fg)] file:rounded-[3px]"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setDosya(f);
                if (f) setSecilenBelge(null);
              }}
            />
            {dosya && (
              <span className="text-[12px] text-[var(--fg-muted)]">
                {dosya.name} · {boyutYaz(dosya.size)}
              </span>
            )}
            <span className="text-[11.5px] leading-[1.5] text-[var(--fg-subtle)]">PDF, DOCX ya da UDF; en çok 20 MB. Dosya adı servise kaydedilmez; metin çıkarılıp maskelenir, bu adımda modele bir şey gitmez.</span>
          </label>
          <div className="flex justify-end gap-2">
            <FlowButton variant="primary" onClick={() => void hazirla()} disabled={hazirlaniyor || (secilenBelge === null && !dosya)}>
              <Search className="w-3.5 h-3.5" aria-hidden="true" />
              {hazirlaniyor ? "Hazırlanıyor…" : "Belgeyi hazırla"}
            </FlowButton>
          </div>
        </div>
      )}

      {adim === "belge" && belge && (
        <div data-testid="lexis-emsal-belge" className="grid gap-3">
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5 border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[12.5px]">
            {(
              [
                ["Kaynak", belge.kaynak === "kart" ? "Kart belgesi" : "Yükleme"],
                ["Biçim", belge.bicim.toUpperCase()],
                ["Boyut", boyutYaz(belge.boyut)],
                ["Sayfa", belge.sayfa !== null ? String(belge.sayfa) : "—"],
                ["Metin", `${belge.metin_uzunluk.toLocaleString("tr-TR")} karakter`],
                ["Bölüm", String(belge.bolumler.length)],
                ["Maske", `bilinen ${belge.maske_dokumu.bilinen} · kalıp ${belge.maske_dokumu.kalip} · öğrenilen ${belge.maske_dokumu.ogrenilen}`],
                ["Arşiv", { tamam: "arşivlendi", bekliyor: "arşivi bekliyor", kapali: "arşiv kapalı", gerekmiyor: "HUKDOK arşivinde" }[belge.arsiv] ?? belge.arsiv],
              ] as const
            ).map(([etiket, deger]) => (
              <div key={etiket} className="min-w-0">
                <dt className="text-[11px] text-[var(--fg-subtle)]">{etiket}</dt>
                <dd className="text-[var(--fg)] break-words">{deger}</dd>
              </div>
            ))}
          </dl>
          {belge.mevcut && <p className="text-[12px] text-[var(--fg-muted)]">Bu belge daha önce hazırlanmış; metin yeniden çıkarılmadı. Önceki okumalar önbellekten gelir.</p>}

          <div data-testid="lexis-emsal-model" className="grid gap-2 border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)]">Model</span>
              {!durum ? (
                <Rozet ton="danger">Durum alınamadı</Rozet>
              ) : !durum.acik ? (
                <Rozet ton="danger">Hat kapalı</Rozet>
              ) : gemini ? (
                <Rozet ton="caution">Gemini — gönderim onayı gerekir</Rozet>
              ) : (
                <Rozet>Sahte üretici</Rozet>
              )}
              {durum?.acik && <span className="text-[12px] text-[var(--fg-muted)]">{gemini ? `${durum.sorgu_modeli} · ${durum.okuyucu_modeli}` : "modele hiçbir şey gitmez; künye, puan ve alıntı belirlenimcidir"}</span>}
            </div>
            {durumHatasi && (
              <p role="alert" className="text-[12.5px] text-tone-danger">
                {durumHatasi}
              </p>
            )}
            {durum && !durum.acik && <p className="text-[12.5px] text-[var(--fg-muted)]">{(durum.neden && KAPALI_NEDENLERI[durum.neden]) ?? "Emsal ajan hattı bu kurulumda kapalı."}</p>}
            {durum?.acik && gemini && (
              <label className="flex items-start gap-2.5 text-[12.5px] leading-[1.5] text-[var(--fg)]">
                <input type="checkbox" className="mt-[3px] accent-[var(--brand)]" aria-label="Gemini'ye gönderimi onaylıyorum" checked={onay} onChange={(e) => setOnay(e.target.checked)} />
                <span>
                  Belgenin maskeli metni ve en çok {durum.aday} aday kararın maskeli metni Gemini'ye gönderilir (künye için 1, aday başına 1 çağrı). Kişi adları servis
                  tarafından maskelenir; dosya adı gitmez.
                  {durum.gunluk_token > 0 && (
                    <span className="block text-[11.5px] text-[var(--fg-subtle)]">
                      Bugün kullanılan token: {(durum.kullanilan_token ?? 0).toLocaleString("tr-TR")} / {durum.gunluk_token.toLocaleString("tr-TR")}
                    </span>
                  )}
                </span>
              </label>
            )}
            {durum?.acik_is && <p className="text-[12px] text-tone-caution">Süren bir emsal aramanız var; bitmeden yenisi başlamaz.</p>}
          </div>

          <div className="flex justify-between gap-2">
            <FlowButton variant="secondary" onClick={() => setAdim("kaynak")}>
              Geri
            </FlowButton>
            <FlowButton variant="primary" onClick={() => void ara()} disabled={!arayabilir}>
              <Search className="w-3.5 h-3.5" aria-hidden="true" />
              Ara
            </FlowButton>
          </div>
        </div>
      )}

      {adim === "arama" && (
        <div data-testid="lexis-emsal-ilerleme" role="status" aria-live="polite" className="grid gap-3 border border-brand/40 bg-[var(--brand-soft)] px-3 py-2.5">
          <ol className="flex flex-wrap items-center gap-x-1 gap-y-1">
            {EMSAL_ASAMALARI.map((a, i) => {
              const etkin = EMSAL_ASAMALARI.findIndex((x) => x.kod === akis.asama);
              const gecti = i < etkin;
              const suren = i === etkin;
              return (
                <li key={a.kod} className="flex items-center gap-1">
                  <span
                    aria-current={suren ? "step" : undefined}
                    className={[
                      "inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] tracking-[0.16em] uppercase",
                      gecti ? "text-[var(--fg-muted)]" : suren ? "text-[var(--fg)] font-semibold border-b-2 border-[var(--brand)]" : "text-[var(--fg-subtle)]",
                    ].join(" ")}
                  >
                    {gecti ? <Check className="w-3 h-3" strokeWidth={2.2} aria-hidden="true" /> : <span className="tabular-nums">0{i + 1}</span>}
                    {a.ad}
                    {suren && akis.ilerleme && (
                      <span className="tabular-nums normal-case tracking-normal">
                        {akis.ilerleme[0]}/{akis.ilerleme[1]}
                      </span>
                    )}
                  </span>
                  {i < EMSAL_ASAMALARI.length - 1 && <span className="h-px w-3 bg-[var(--border-strong)]" aria-hidden="true" />}
                </li>
              );
            })}
          </ol>
          <span className="text-[12.5px] text-[var(--fg-muted)]">{akis.mesaj}</span>
          {uyarilar.length > 0 && (
            <ul data-testid="lexis-emsal-uyarilar" className="grid gap-0.5 text-[12px] leading-[1.45] text-tone-caution" aria-label="Uyarılar">
              {uyarilar.map((u, i) => (
                <li key={i}>⚠ {u}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end">
            <FlowButton variant="secondary" size="sm" onClick={durdur}>
              <Square className="w-3 h-3" aria-hidden="true" />
              Durdur
            </FlowButton>
          </div>
        </div>
      )}

      {adim === "sonuc" && sonuc && (
        <div data-testid="lexis-emsal-sonuc" className="grid gap-3">
          <div className="grid gap-1 text-[12px] text-[var(--fg-muted)]">
            <p data-testid="lexis-emsal-sayilar" className="font-mono text-[11.5px] tabular-nums">
              {[
                `${sonuc.sayilar.aday} aday`,
                `${sonuc.sayilar.okunan} okundu`,
                `${sonuc.sayilar.dusen} düştü`,
                sonuc.sayilar.onbellek > 0 && `${sonuc.sayilar.onbellek} önbellekten`,
                `${sonuc.sayilar.model_cagrisi} model çağrısı`,
                `${sonuc.sayilar.saniye.toLocaleString("tr-TR", { maximumFractionDigits: 1 })} sn`,
                `model: ${sonuc.model}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <p data-testid="lexis-emsal-kunye" className="leading-[1.5]">
              <span className="text-[var(--fg-subtle)]">Künye: </span>
              {[sonuc.kunye.uzmanlik, sonuc.kunye.tibbi_islem, sonuc.kunye.yargi_yolu, sonuc.kunye.taraf_turu].filter(Boolean).join(" · ") || "—"}
              {sonuc.kunye.iddia && <span className="block text-[var(--fg)]">{sonuc.kunye.iddia}</span>}
              {sonuc.kunye.sorgular.length > 0 && (
                <span className="flex flex-wrap gap-1 mt-1">
                  {sonuc.kunye.sorgular.map((s, i) => (
                    <span key={i} className="font-mono text-[11px] px-1.5 py-0.5 border border-[var(--border)] bg-[var(--bg)]" title={s.tur}>
                      {s.metin}
                    </span>
                  ))}
                </span>
              )}
            </p>
            {uyarilar.length > 0 && (
              <details>
                <summary className={`cursor-pointer ${BAGLANTI_SINIFI}`}>{uyarilar.length} uyarı (düşen adaylar, olgu uyarıları)</summary>
                <ul data-testid="lexis-emsal-uyarilar" className="grid gap-0.5 mt-1 text-[12px] leading-[1.45] text-tone-caution">
                  {uyarilar.map((u, i) => (
                    <li key={i}>⚠ {u}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <EmsalKararListesi oneriler={sonuc.oneriler} secili={secili} onSec={sec} mevcut={mevcutKararlar} onKararAc={onKararAc} />

          {(indirmePasif || indirmeMesaji) && (
            <p data-testid="lexis-emsal-indirme-notu" role={indirmePasif ? undefined : "status"} className="text-[12px] leading-[1.5] text-[var(--fg-muted)]">
              {indirmePasif ?? indirmeMesaji}
            </p>
          )}
          <div className="flex flex-wrap justify-between gap-2">
            <FlowButton variant="secondary" onClick={() => setAdim("belge")}>
              Belgeye dön
            </FlowButton>
            <span className="flex flex-wrap gap-2">
              <FlowButton variant="secondary" onClick={() => void indir()} disabled={indiriliyor || indirmePasif !== null}>
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                {indiriliyor ? "İndiriliyor…" : "İnceleme paketini indir"}
              </FlowButton>
              {onTaslagaEkle && (
                <FlowButton variant="primary" onClick={taslagaEkle} disabled={secilebilir === 0}>
                  <Plus className="w-3.5 h-3.5" aria-hidden="true" />
                  Taslağa ekle{secilebilir > 0 ? ` (${secilebilir})` : ""}
                </FlowButton>
              )}
            </span>
          </div>
        </div>
      )}
    </>
  );
}
