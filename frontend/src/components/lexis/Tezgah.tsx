import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { FolderOpen, PenLine, ScrollText, ShieldCheck, X } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import { DetailSkeleton, LineListSkeleton } from "@/components/skeletons/Skeletons";
import { useConfirm } from "@/hooks/useConfirm";
import { ORNEK_VERI, lexisApi } from "@/lib/lexisApi";
import { ISKELET_BOLUMLERI, SIRKET_ADLARI, type BolumKodu, type Emsal, type KutuphaneKaydi, type LexisDava, type LexisUyari } from "@/types/lexis";
import { BelgeListesi } from "./BelgeListesi";
import { BolumGezgini } from "./BolumGezgini";
import { CiktiCubugu } from "./CiktiCubugu";
import { DavaSecici } from "./DavaSecici";
import { DayanakGoruntuleyici } from "./DayanakGoruntuleyici";
import { DegerlendirmeBolumu } from "./DegerlendirmeBolumu";
import { EmsalEkleDiyalogu } from "./EmsalEkleDiyalogu";
import { EmsalListesi } from "./EmsalListesi";
import { EmsalOkuyucu } from "./EmsalOkuyucu";
import { EtiketliBolum } from "./EtiketliBolum";
import { KunyeKarti, type KunyeSecimi } from "./KunyeKarti";
import { MuallakKarti } from "./MuallakKarti";
import { OzetBolum } from "./OzetBolum";
import { UretimSeridi } from "./UretimSeridi";
import { UyariListesi } from "./UyariListesi";
import { useTezgah } from "./useTezgah";
import { bolumKimligi, bolumUyariSayilari, hataMetni, uyariHedefi } from "./yardimcilar";

type Vurgu = { madde: number | null; alan: string | null; bolum: BolumKodu | null };

const CEKMECE_DUGMESI =
  "inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[3px] border border-[var(--border)] text-[12px] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:border-[var(--brand)] shrink-0";

/**
 * "Rapor yaz" tezgâhı — üç bölge: SOL dosya (dava, künye, belgeler, emsaller) · ORTA taslak (iskeletin bölümleri)
 * · SAĞ denetim (uyarılar, muallak, dayanak, çıktı). Durum `useTezgah`'ta.
 *
 * Dar ekranda sol bölge `lg` (1024 px), sağ bölge `xl` (1280 px) altında çekmeceye döner; orta başlıktaki
 * "Dosya" / "Denetim" düğmeleri açar. Taslağı silen her eylem (dava ya da künye değişimi, yeniden yazım) önce
 * onay ister; yazımdan önce modele ne gideceği gösterilir (K4).
 */
export function Tezgah() {
  const t = useTezgah();
  const confirm = useConfirm();
  const [solAcik, setSolAcik] = useState(false);
  const [sagAcik, setSagAcik] = useState(false);
  const [seciliMadde, setSeciliMadde] = useState<number | null>(null);
  const [vurgu, setVurgu] = useState<Vurgu | null>(null);
  const [okunan, setOkunan] = useState<{ kayit: KutuphaneKaydi; emsal: Emsal | null } | null>(null);
  const [ekleAcik, setEkleAcik] = useState(false);
  const [wordIniyor, setWordIniyor] = useState(false);
  const vurguZamanlayici = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (vurguZamanlayici.current) clearTimeout(vurguZamanlayici.current);
    },
    [],
  );

  const { dosya, taslak } = t;
  const bolumler = useMemo(() => (dosya ? ISKELET_BOLUMLERI[dosya.iskelet] : []), [dosya]);
  const bolumAdlari = useMemo(() => Object.fromEntries(bolumler.map((b) => [b.kod, b.baslik])) as Partial<Record<BolumKodu, string>>, [bolumler]);
  const dayanakBolumleri = useMemo(() => bolumler.filter((b) => b.tur === "OZET").map((b) => ({ kod: b.kod, baslik: b.baslik })), [bolumler]);
  const uyariSayilari = useMemo(() => bolumUyariSayilari(t.uyarilar), [t.uyarilar]);
  const hataSayisi = t.uyarilar.filter((u) => u.seviye === "HATA").length;
  const kilitli = t.yaziliyor;

  const taslakSilinsinMi = useCallback(
    async (neden: string) =>
      !taslak ||
      (await confirm({
        tone: "warning",
        title: "Taslak silinecek",
        body: `${neden} Yazılmış taslak ve yaptığınız düzeltmeler kaybolur.`,
        confirmLabel: "Sil ve devam et",
      })),
    [taslak, confirm],
  );

  const davaSec = async (dava: LexisDava | null) => {
    if (!(await taslakSilinsinMi(dava ? "Başka bir davaya geçiyorsunuz." : "Davayı değiştiriyorsunuz."))) return;
    setSeciliMadde(null);
    t.davaSec(dava);
  };

  const kunyeDegistir = async (secim: KunyeSecimi) => {
    if (!(await taslakSilinsinMi("Şirket, rapor türü ya da iskelet değişince taslak yeniden yazılmalıdır."))) return;
    setSeciliMadde(null);
    t.kunyeDegistir(secim);
  };

  const yaz = async () => {
    if (!dosya) return;
    const secili = dosya.belgeler.filter((b) => t.seciliBelgeler.has(b.id));
    const onay = await confirm({
      tone: taslak ? "warning" : "info",
      title: taslak ? "Taslak yeniden yazılacak" : "Taslak yazılacak",
      body:
        (taslak ? "Mevcut taslak ve düzeltmeleriniz silinir. " : "") +
        "Seçili belgelerin metni ve emsal raporların maskeli metni taslak yazımı için modele gönderilir." +
        (ORNEK_VERI ? " (Önizleme: hiçbir şey gönderilmez, örnek taslak gösterilir.)" : ""),
      details: [
        { label: "Belgeler", value: secili.length > 0 ? `${secili.length} belge — ${secili.map((b) => b.ad).join(", ")}` : "Belge seçilmedi" },
        { label: "Emsal raporlar", value: t.emsaller.length > 0 ? `${t.emsaller.length} rapor (maskeli)` : "Emsal yok" },
        { label: "Rapor", value: [dosya.sirket && SIRKET_ADLARI[dosya.sirket], dosya.rapor_turu === "EK" ? "ek rapor" : "ana rapor", `${bolumler.length} bölüm`].filter(Boolean).join(" · ") },
      ],
      confirmLabel: taslak ? "Yeniden yaz" : "Taslağı yaz",
    });
    if (!onay) return;
    setSeciliMadde(null);
    setSolAcik(false);
    void t.yaz();
  };

  const raporOku = async (sha256: string) => {
    const emsal = t.emsaller.find((e) => e.kayit.okuma.sha256 === sha256);
    if (emsal) {
      setOkunan({ kayit: emsal.kayit, emsal });
      return;
    }
    try {
      setOkunan({ kayit: await lexisApi.raporGetir(sha256), emsal: null });
    } catch (e) {
      toast.error("Rapor açılamadı", { description: hataMetni(e) });
    }
  };

  const wordIndir = async () => {
    if (!taslak || wordIniyor) return;
    setWordIniyor(true);
    try {
      const sonuc = await lexisApi.wordIndir(taslak);
      // Şablon yazımının uyarıları (boş kalan alan, yazılamayan bölüm) dosyayla birlikte gelir; ilk üçü gösterilir.
      const ozet = sonuc.uyarilar.slice(0, 3).join(" · ");
      toast.success("Word indirildi", {
        description: sonuc.uyari_sayisi > 0 ? `${sonuc.uyari_sayisi} uyarı${ozet ? `: ${ozet}` : ""}` : sonuc.dosya_adi,
      });
    } catch (e) {
      toast.error("Word indirilemedi", { description: hataMetni(e) });
    } finally {
      setWordIniyor(false);
    }
  };

  const git = (kimlik: string | null, yeniVurgu: Vurgu) => {
    setSagAcik(false);
    if (kimlik) document.getElementById(kimlik)?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    setVurgu(yeniVurgu);
    if (vurguZamanlayici.current) clearTimeout(vurguZamanlayici.current);
    vurguZamanlayici.current = setTimeout(() => setVurgu(null), 1600);
  };
  const uyariyaGit = (u: LexisUyari) => git(uyariHedefi(u), { madde: u.madde, alan: u.alan, bolum: u.bolum });
  const bolumeGit = (kod: BolumKodu) => git(bolumKimligi(kod), { madde: null, alan: null, bolum: kod });

  const maddeSec = (sira: number) => {
    setSeciliMadde(sira);
    setSagAcik(true);
  };

  return (
    <div data-testid="lexis-tezgah" className="flex w-full min-w-0 h-full min-h-0 overflow-hidden">
      {/* SOL — dosya */}
      {solAcik && <button type="button" aria-label="Kapat" tabIndex={-1} className="lg:hidden fixed inset-0 z-30 bg-black/40" onClick={() => setSolAcik(false)} />}
      <aside
        aria-label="Dosya"
        className={`${solAcik ? "flex" : "hidden"} lg:flex fixed inset-y-0 left-0 z-40 w-[88vw] max-w-sm shadow-xl lg:static lg:z-auto lg:w-80 lg:max-w-none lg:shadow-none shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg)]`}
      >
        <div className="lg:hidden h-11 shrink-0 flex items-center justify-between px-4 border-b border-[var(--border)]">
          <span className="text-[13px] font-medium text-[var(--fg)]">Dosya</span>
          <button type="button" onClick={() => setSolAcik(false)} aria-label="Dosya panelini kapat" className="w-8 h-8 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)]">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 grid content-start gap-5">
          <DavaSecici secili={dosya?.dava ?? null} onSec={(d) => void davaSec(d)} kilitli={kilitli} />
          {t.dosyaYukleniyor && <LineListSkeleton count={4} label="Dosya yükleniyor…" />}
          {t.dosyaHatasi && (
            <p role="alert" className="text-[12.5px] text-tone-danger">
              {t.dosyaHatasi}
            </p>
          )}
          {dosya && (
            <>
              <KunyeKarti
                dosya={dosya}
                onDegistir={(s) => void kunyeDegistir(s)}
                onOncekiRapor={dosya.onceki_rapor ? () => void raporOku(dosya.onceki_rapor!) : undefined}
                kilitli={kilitli}
              />
              <BelgeListesi belgeler={dosya.belgeler} secili={t.seciliBelgeler} onSec={t.belgeSec} kilitli={kilitli} />
              <EmsalListesi
                emsaller={t.emsaller}
                yukleniyor={t.emsalYukleniyor}
                hata={t.emsalHatasi}
                onOku={(e) => setOkunan({ kayit: e.kayit, emsal: e })}
                onCikar={t.emsalCikar}
                onEkle={() => setEkleAcik(true)}
                kilitli={kilitli}
              />
            </>
          )}
        </div>
        {dosya && (
          <div className="shrink-0 p-3 border-t border-[var(--border)]">
            <FlowButton variant={taslak ? "secondary" : "primary"} className="w-full" onClick={() => void yaz()} disabled={kilitli || t.emsalYukleniyor}>
              <PenLine className="w-3.5 h-3.5" aria-hidden="true" />
              {taslak ? "Yeniden yaz" : "Taslağı yaz"}
            </FlowButton>
          </div>
        )}
      </aside>

      {/* ORTA — taslak */}
      <section aria-label="Taslak" className="flex-1 min-w-0 flex flex-col">
        <header className="h-11 shrink-0 flex items-center gap-2 px-3 md:px-5 border-b border-[var(--border)]">
          <button type="button" onClick={() => setSolAcik(true)} className={`lg:hidden ${CEKMECE_DUGMESI}`}>
            <FolderOpen className="w-3.5 h-3.5" aria-hidden="true" />
            Dosya
          </button>
          <h2 className="min-w-0 truncate text-[13px] font-medium text-[var(--fg)]" data-testid="lexis-taslak-basligi">
            {dosya ? <span className="font-mono text-[12px]">{dosya.dava.ofis_no}</span> : "Taslak"}
          </h2>
          <button type="button" onClick={() => setSagAcik(true)} className={`xl:hidden ml-auto ${CEKMECE_DUGMESI}`}>
            <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
            Denetim
            {taslak && t.uyarilar.length > 0 && <span className="font-mono tabular-nums text-tone-caution">{t.uyarilar.length}</span>}
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto">
          {!dosya && !t.dosyaYukleniyor && (
            <div className="h-full grid place-items-center p-6">
              <div className="grid justify-items-center gap-3 text-center max-w-md">
                <div className="w-12 h-12 grid place-items-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]">
                  <ScrollText className="w-5 h-5" strokeWidth={1.8} aria-hidden="true" />
                </div>
                <h3 className="font-display text-[22px] font-medium text-[var(--fg)]">Rapor yazılacak davayı seçin</h3>
                <p className="text-[13px] leading-[1.6] text-[var(--fg-muted)]">
                  Dava seçilince kartın alanları ve belgeleri gelir, en benzer eski raporlar önerilir. Taslak şirketin iskeletinde bölüm bölüm
                  yazılır; her maddeyi dayanağıyla birlikte düzeltirsiniz.
                </p>
                <FlowButton variant="secondary" size="sm" className="lg:hidden" onClick={() => setSolAcik(true)}>
                  Dava seç
                </FlowButton>
              </div>
            </div>
          )}

          {t.dosyaYukleniyor && <DetailSkeleton label="Dosya yükleniyor…" className="p-5" />}

          {dosya && (
            <div className="px-3 md:px-6 pb-10">
              <div className="sticky top-0 z-10 -mx-3 md:-mx-6 px-3 md:px-6 py-2.5 grid gap-2 bg-[var(--bg-elevated)] border-b border-[var(--border)]">
                {t.akis && <UretimSeridi asama={t.akis.asama} mesaj={t.akis.mesaj} onDurdur={t.durdur} />}
                <BolumGezgini bolumler={bolumler} durumlar={t.bolumDurumlari} uyariSayilari={uyariSayilari} onGit={bolumeGit} />
              </div>

              {t.akisHatasi && (
                <p role="alert" data-testid="lexis-akis-hatasi" className="mt-4 border border-tone-danger/40 bg-tone-danger/10 px-3 py-2 text-[12.5px] text-tone-danger">
                  {t.akisHatasi}
                </p>
              )}

              {!taslak && (
                <div data-testid="lexis-hazirlik" className="mt-6 max-w-2xl grid gap-2">
                  <h3 className="font-display text-[19px] font-medium text-[var(--fg)]">Taslak henüz yazılmadı</h3>
                  <p className="text-[13px] leading-[1.6] text-[var(--fg-muted)]">
                    Soldaki künyeyi, taslağa girecek belgeleri ve bakılacak emsal raporları gözden geçirip <span className="font-medium text-[var(--fg)]">Taslağı yaz</span>'a
                    basın. Yukarıdaki {bolumler.length} bölüm sırayla yazılır; etiketli bölümleri kod doldurur, özet bölümler belgelerden, değerlendirme
                    olgulardan ve emsallerden yazılır.
                  </p>
                </div>
              )}

              {taslak &&
                bolumler.map((b, i) => {
                  const durum = t.bolumDurumlari[b.kod] ?? "bos";
                  return (
                    <section
                      key={b.kod}
                      id={bolumKimligi(b.kod)}
                      aria-label={b.baslik}
                      data-testid={`lexis-bolum-${b.kod}`}
                      className={`mt-6 scroll-mt-28 transition-colors ${vurgu?.bolum === b.kod && vurgu.madde === null && vurgu.alan === null ? "bg-[var(--brand-soft)]" : ""}`}
                    >
                      <h3 className="flex items-baseline gap-2 mb-2">
                        <span className="font-mono text-[11px] font-semibold tabular-nums text-brand-solid">{String(i + 1).padStart(2, "0")}</span>
                        <span className="font-display text-[17px] font-medium tracking-[-0.005em] text-[var(--fg)]">{b.baslik}</span>
                      </h3>
                      {durum === "yaziliyor" && <LineListSkeleton count={2} label={`${b.baslik} yazılıyor…`} />}
                      {durum !== "yaziliyor" && b.tur === "ETIKETLI" && (
                        <EtiketliBolum
                          bolum={b.kod}
                          satirlar={taslak.etiketli[b.kod] ?? []}
                          onDegistir={(alan, deger) => t.etiketliDegistir(b.kod, alan, deger)}
                          onBlur={t.alandanCikildi}
                          vurguluAlan={vurgu?.bolum === b.kod ? vurgu.alan : null}
                          kilitli={kilitli}
                        />
                      )}
                      {durum !== "yaziliyor" && b.tur === "OZET" && (
                        <OzetBolum
                          baslik={b.baslik}
                          paragraflar={taslak.ozet[b.kod] ?? []}
                          belgeler={dosya.belgeler}
                          onDegistir={(sira, metin) => t.paragrafDegistir(b.kod, sira, metin)}
                          onEkle={() => t.paragrafEkle(b.kod)}
                          onSil={(sira) => t.paragrafSil(b.kod, sira)}
                          onBlur={t.alandanCikildi}
                          kilitli={kilitli}
                        />
                      )}
                      {durum !== "yaziliyor" && b.tur === "MUHAKEME" && taslak.degerlendirme && (
                        <DegerlendirmeBolumu
                          degerlendirme={taslak.degerlendirme}
                          maddeKimlikleri={t.maddeKimlikleri}
                          degisenMaddeler={t.degisenMaddeler}
                          uyarilar={t.uyarilar.filter((u) => u.bolum === "degerlendirme")}
                          seciliMadde={seciliMadde}
                          vurguluMadde={vurgu?.madde ?? null}
                          dayanakBolumleri={dayanakBolumleri}
                          onGiris={t.girisDegistir}
                          onSulh={t.sulhDegistir}
                          sulhSatiri={taslak.iskelet === "ANADOLU"}
                          onMadde={t.maddeDegistir}
                          onMaddeEkle={t.maddeEkle}
                          onMaddeSil={(sira) => {
                            setSeciliMadde(null);
                            t.maddeSil(sira);
                          }}
                          onMaddeTasi={(sira, yon) => {
                            setSeciliMadde(null);
                            t.maddeTasi(sira, yon);
                          }}
                          onMaddeSec={maddeSec}
                          onBlur={t.alandanCikildi}
                          kilitli={kilitli}
                        />
                      )}
                    </section>
                  );
                })}
            </div>
          )}
        </div>
      </section>

      {/* SAĞ — denetim */}
      {sagAcik && <button type="button" aria-label="Kapat" tabIndex={-1} className="xl:hidden fixed inset-0 z-30 bg-black/40" onClick={() => setSagAcik(false)} />}
      <aside
        aria-label="Denetim"
        className={`${sagAcik ? "flex" : "hidden"} xl:flex fixed inset-y-0 right-0 z-40 w-[88vw] max-w-sm shadow-xl xl:static xl:z-auto xl:w-80 2xl:w-96 xl:max-w-none xl:shadow-none shrink-0 flex-col border-l border-[var(--border)] bg-[var(--bg)]`}
      >
        <div className="xl:hidden h-11 shrink-0 flex items-center justify-between px-4 border-b border-[var(--border)]">
          <span className="text-[13px] font-medium text-[var(--fg)]">Denetim</span>
          <button type="button" onClick={() => setSagAcik(false)} aria-label="Denetim panelini kapat" className="w-8 h-8 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)]">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 grid content-start gap-5">
          <UyariListesi uyarilar={t.uyarilar} bolumAdlari={bolumAdlari} taslakVar={taslak !== null && !t.yaziliyor} bayat={t.bayat} onGit={uyariyaGit} />
          <MuallakKarti
            oneri={taslak?.muallak ?? null}
            maddi={taslak?.muallak_maddi ?? null}
            manevi={taslak?.muallak_manevi ?? null}
            talepMaddi={dosya?.talep_maddi ?? null}
            talepManevi={dosya?.talep_manevi ?? null}
            teminatLimiti={dosya?.teminat_limiti ?? null}
            onDegistir={t.muallakDegistir}
            onRaporOku={(sha) => void raporOku(sha)}
            kilitli={kilitli}
          />
          <DayanakGoruntuleyici taslak={taslak} sira={seciliMadde} bolumAdlari={bolumAdlari} />
        </div>
        {taslak && !t.yaziliyor && (
          <div className="shrink-0 p-3 border-t border-[var(--border)]">
            <CiktiCubugu
              hataSayisi={hataSayisi}
              uyariSayisi={t.uyarilar.length - hataSayisi}
              bayat={t.bayat}
              denetleniyor={t.denetleniyor}
              sonDenetim={t.sonDenetim}
              onDenetle={() => void t.denetle()}
              onWord={() => void wordIndir()}
              kilitli={wordIniyor}
            />
          </div>
        )}
      </aside>

      <EmsalOkuyucu kayit={okunan?.kayit ?? null} emsal={okunan?.emsal} onKapat={() => setOkunan(null)} />
      <EmsalEkleDiyalogu
        acik={ekleAcik}
        haricSha={t.emsaller.map((e) => e.kayit.okuma.sha256)}
        onSec={(kayit) => {
          setEkleAcik(false);
          void t.emsalEkle(kayit);
        }}
        onKapat={() => setEkleAcik(false)}
      />
    </div>
  );
}
