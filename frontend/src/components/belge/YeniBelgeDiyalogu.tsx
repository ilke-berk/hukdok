// "Yeni belge" diyaloğu (G285, plan K15, §6.3 `belgeler/yeni`): kartta Word taslağı açar. Belge türü mevcut doctype
// listesi (`useConfigList("doctypes")`, kod `_` pad'li gider), ad varsayılanı tür etiketi + tarih (kullanıcı yazınca
// ezilmez), sunucunun yazacağı ad `docxAdiOnizleme` ile ön-izlenir; müvekkil tarafı opsiyonel. "Oluştur ve Word'de aç" →
// `yeniBelge` → `ms-word:` bağlantısı (`useWordAcici`); 1,5 sn'de açılmazsa "Word Online'da aç" (`word_url`) görünür.
//
// Kart verilmezse (tezgâhın "Yaz (Word)" yolu) diyalog dava arar — G273 `KartaBaglaDiyalogu`'nun arama deseniyle aynı:
// `useCases().searchCases` (tuş vuruşu yolu, 350 ms debounce), seçilen kartın tarafları `getCase`'ten. Diyalog
// `theme-classic` (portal kabuğun dışında); native <select>/<input> (jsdom'da Radix seçici yok).
import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router";
import { AlertCircle, CheckCircle2, ExternalLink, FilePlus2, Loader2, Search, X } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { useCases } from "@/hooks/useCases";
import { useConfigList } from "@/hooks/useConfig";
import { useDebounce } from "@/hooks/useDebounce";
import { docxAdiOnizleme, varsayilanBelgeAdi, yeniBelge } from "@/lib/belgeYasamApi";
import { useWordAcici } from "@/components/belge/useWordAcici";
import type { YeniBelgeYaniti } from "@/types/belge";
import type { KartOzeti, KartTarafi } from "@/types/pdfAraclari";

type Props = {
  acik: boolean;
  /** Karttan açılınca kart sabittir; verilmezse (tezgâh) diyalog dava arar. */
  kart?: KartOzeti | null;
  onKapat: () => void;
  onBasari?: (yanit: YeniBelgeYaniti, kart: KartOzeti) => void;
  /** Sonuç ekranında "Karta git" bağlantısı (tezgâh yolu; kartın içinden açılınca gerek yok). */
  kartaGitBaglantisi?: boolean;
};

const GIRDI =
  "w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-60";
const ETIKET = "block font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] mb-1";

type AramaSonucu = KartOzeti & { subject?: string | null };

function kartBasligi(k: KartOzeti): string {
  return k.tracking_no || k.esas_no || `Kart #${k.id}`;
}

function muvekkilAdi(k: KartOzeti): string | null {
  return k.parties?.find((p) => p.party_type === "CLIENT")?.name ?? null;
}

const HATA_METNI = "Belge oluşturulamadı.";

export function YeniBelgeDiyalogu({ acik, kart: sabitKart, onKapat, onBasari, kartaGitBaglantisi = false }: Props) {
  const kimlik = useId();
  const { searchCases, getCase } = useCases();
  const { data: doctypes, error: doctypeHatasi } = useConfigList("doctypes");
  const word = useWordAcici();
  const { sifirla: wordSifirla } = word;

  const [sorgu, setSorgu] = useState("");
  const gecikmeli = useDebounce(sorgu, 350);
  const [sonuclar, setSonuclar] = useState<AramaSonucu[]>([]);
  const [araniyor, setAraniyor] = useState(false);
  const [kart, setKart] = useState<KartOzeti | null>(null);
  const [taraflar, setTaraflar] = useState<KartTarafi[]>([]);
  const [turKodu, setTurKodu] = useState("");
  const [ad, setAd] = useState("");
  const [adElle, setAdElle] = useState(false);
  const [tarafId, setTarafId] = useState("");
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [sonuc, setSonuc] = useState<YeniBelgeYaniti | null>(null);

  // Açılış: formu kur (sabit kart varsa onunla).
  useEffect(() => {
    if (!acik) return;
    setSorgu("");
    setSonuclar([]);
    setKart(sabitKart ?? null);
    setTaraflar(sabitKart?.parties ?? []);
    setTurKodu("");
    setAd("");
    setAdElle(false);
    setTarafId("");
    setHata(null);
    setSonuc(null);
    setGonderiliyor(false);
    wordSifirla();
  }, [acik, sabitKart, wordSifirla]);

  // Arama (tuş vuruşu yolu) — yalnız kart seçilmemişken.
  useEffect(() => {
    if (!acik || kart || gecikmeli.trim().length < 2) {
      // Zaten boşsa aynı referans: yeni dizi her çizimde efekti yeniden tetikleyip döngü kurabilir (kararsız `searchCases`).
      setSonuclar((onceki) => (onceki.length ? [] : onceki));
      return;
    }
    let iptal = false;
    setAraniyor(true);
    (async () => {
      try {
        const r = (await searchCases(gecikmeli.trim())) as unknown;
        const liste = Array.isArray(r) ? r : ((r as { cases?: unknown[] } | null)?.cases ?? []);
        if (!iptal) setSonuclar((liste as AramaSonucu[]).slice(0, 8));
      } catch {
        if (!iptal) setSonuclar([]);
      } finally {
        if (!iptal) setAraniyor(false);
      }
    })();
    return () => {
      iptal = true;
    };
  }, [acik, kart, gecikmeli, searchCases]);

  // Seçilen kartın tarafları (arama yanıtı tarafsız olabilir).
  useEffect(() => {
    if (!acik || !kart) return;
    if (kart.parties && kart.parties.length > 0) {
      setTaraflar(kart.parties);
      return;
    }
    let iptal = false;
    (async () => {
      try {
        const detay = (await getCase(kart.id)) as { parties?: KartTarafi[] } | null;
        if (!iptal && detay) setTaraflar(Array.isArray(detay.parties) ? detay.parties : []);
      } catch {
        /* taraf listesi opsiyonel */
      }
    })();
    return () => {
      iptal = true;
    };
  }, [acik, kart, getCase]);

  const turler = useMemo(() => (doctypes ?? []).filter((d) => d.code), [doctypes]);
  const muvekkiller = useMemo(() => taraflar.filter((p) => p.party_type === "CLIENT"), [taraflar]);
  const onizleme = docxAdiOnizleme(ad);
  const gecerli = !!kart && turKodu.length > 0 && !!onizleme;

  const turSec = (kod: string) => {
    setTurKodu(kod);
    if (!adElle) {
      const etiket = turler.find((d) => d.code === kod)?.name ?? "";
      setAd(etiket ? varsayilanBelgeAdi(etiket) : "");
    }
  };

  const gonder = async () => {
    if (!gecerli || !kart || gonderiliyor) return;
    setGonderiliyor(true);
    setHata(null);
    try {
      const yanit = await yeniBelge(kart.id, {
        belge_turu_kodu: turKodu,
        ad: ad.trim(),
        case_party_id: tarafId ? Number(tarafId) : undefined,
      });
      setSonuc(yanit);
      toast.success("Word taslağı açıldı", { description: `${onizleme} → ${kartBasligi(kart)} · Taslaklar` });
      if (yanit.word_ac && yanit.word_url) word.ac(yanit.word_ac, yanit.word_url);
      onBasari?.(yanit, kart);
    } catch (e) {
      setHata(e instanceof Error && e.message.trim() ? e.message : HATA_METNI);
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <Dialog open={acik} onOpenChange={(v) => !v && !gonderiliyor && onKapat()}>
      <DialogContent
        data-testid="yeni-belge-diyalogu"
        className="theme-classic max-w-[600px] max-h-[90vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-[18px]">
            <FilePlus2 className="w-4 h-4 text-[var(--brand)]" />
            Yeni belge (Word)
          </DialogTitle>
          <DialogDescription>
            Boş Word taslağı kartın Taslaklar bölümüne açılır; Word'de istediğiniz kadar çalışıp sürüm kaydedebilir, bitince
            kesinleştirirsiniz.
          </DialogDescription>
        </DialogHeader>

        {sonuc && kart ? (
          <div data-testid="yeni-belge-sonuc" className="flex flex-col gap-3 py-2">
            <div className="flex items-start gap-2 rounded-[3px] border border-[rgb(var(--tone-ok-rgb))] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-[rgb(var(--tone-ok-rgb))]" />
              <span>
                Taslak açıldı — belge #{sonuc.document_id} · {kartBasligi(kart)}. Word açılıyor…
              </span>
            </div>
            {word.yedekUrl && (
              <p data-testid="word-online-yedek" className="text-[12px] text-[var(--fg-muted)]">
                Masaüstü Word açılmadı mı?{" "}
                <a href={word.yedekUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-[var(--brand)] underline">
                  Word Online'da aç <ExternalLink className="w-3 h-3" />
                </a>
              </p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              {kartaGitBaglantisi && (
                <Link
                  to={`/cases/${kart.id}?belgeler=taslak`}
                  className="inline-flex items-center gap-2 rounded-[3px] border border-[var(--brand)] bg-[var(--brand-soft)] px-3 py-1.5 text-[12px] font-medium text-[var(--brand)]"
                >
                  Kartın taslaklarına git
                </Link>
              )}
              <FlowButton size="sm" variant="secondary" onClick={onKapat}>
                Kapat
              </FlowButton>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 py-1">
            <div>
              <span className={ETIKET}>Dava kartı</span>
              {kart ? (
                <div data-testid="secili-kart" className="flex items-start gap-2 rounded-[3px] border border-[var(--brand)] bg-[var(--brand-soft)] px-3 py-2">
                  <div className="min-w-0 flex-1 text-[13px] text-[var(--fg)]">
                    <div className="font-medium tabular-nums">{kartBasligi(kart)}</div>
                    <div className="text-[12px] text-[var(--fg-muted)] truncate">
                      {[kart.esas_no && kart.esas_no !== kart.tracking_no ? kart.esas_no : null, kart.court, muvekkilAdi({ ...kart, parties: taraflar })]
                        .filter(Boolean)
                        .join(" · ") || "Künye yok"}
                    </div>
                  </div>
                  {!sabitKart && (
                    <button type="button" aria-label="Kart seçimini kaldır" onClick={() => setKart(null)} className="text-[var(--fg-subtle)] hover:text-[var(--fg)]">
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ) : (
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                  <input
                    aria-label="Dava ara"
                    className={`${GIRDI} pl-8`}
                    placeholder="Ofis no, esas no ya da taraf adı…"
                    value={sorgu}
                    onChange={(e) => setSorgu(e.target.value)}
                    autoFocus
                  />
                  {araniyor && <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 animate-spin text-[var(--fg-subtle)]" />}
                  {gecikmeli.trim().length >= 2 && !araniyor && (
                    <ul role="listbox" aria-label="Arama sonuçları" className="mt-1 max-h-48 overflow-y-auto rounded-[3px] border border-[var(--border)] bg-[var(--bg)]">
                      {sonuclar.length === 0 ? (
                        <li className="px-3 py-2 text-[12px] text-[var(--fg-muted)]">Sonuç bulunamadı</li>
                      ) : (
                        sonuclar.map((c) => (
                          <li key={c.id} role="option" aria-selected={false}>
                            <button
                              type="button"
                              onClick={() => {
                                setKart(c);
                                setSorgu("");
                                setSonuclar([]);
                              }}
                              className="w-full text-left px-3 py-2 hover:bg-[var(--bg-elevated)] border-b border-[var(--border)] last:border-b-0"
                            >
                              <div className="text-[13px] font-medium tabular-nums text-[var(--fg)]">{kartBasligi(c)}</div>
                              <div className="text-[11px] text-[var(--fg-muted)] truncate">
                                {[c.esas_no && c.esas_no !== c.tracking_no ? c.esas_no : null, c.court, muvekkilAdi(c), c.status].filter(Boolean).join(" · ")}
                              </div>
                            </button>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2 sm:col-span-1">
                <label className={ETIKET} htmlFor={`${kimlik}-tur`}>Belge türü</label>
                <select id={`${kimlik}-tur`} className={GIRDI} value={turKodu} onChange={(e) => turSec(e.target.value)}>
                  <option value="">Seçin…</option>
                  {turler.map((d) => (
                    <option key={d.code} value={d.code}>
                      {d.name}
                    </option>
                  ))}
                </select>
                {doctypeHatasi && <p className="mt-1 text-[11px] text-[rgb(var(--tone-danger-rgb))]">Belge türü listesi alınamadı.</p>}
              </div>
              <div className="col-span-2 sm:col-span-1">
                <label className={ETIKET} htmlFor={`${kimlik}-taraf`}>Müvekkil (opsiyonel)</label>
                <select id={`${kimlik}-taraf`} className={GIRDI} value={tarafId} onChange={(e) => setTarafId(e.target.value)} disabled={muvekkiller.length === 0}>
                  <option value="">{muvekkiller.length === 0 ? "Kartta müvekkil tarafı yok" : "Tüm dava"}</option>
                  {muvekkiller.map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className={ETIKET} htmlFor={`${kimlik}-ad`}>Belge adı</label>
                <input
                  id={`${kimlik}-ad`}
                  className={GIRDI}
                  value={ad}
                  maxLength={255}
                  placeholder="Önce belge türünü seçin"
                  onChange={(e) => {
                    setAd(e.target.value);
                    setAdElle(true);
                  }}
                />
                <p data-testid="ad-onizleme" className="mt-1 text-[11px] text-[var(--fg-muted)] break-all">
                  {ad.trim() === ""
                    ? "Ad, türü seçince tür adı + bugünün tarihiyle dolar."
                    : onizleme
                      ? <>Kaydedilecek ad: <span className="font-mono text-[var(--fg)]">{onizleme}</span> (aynı ad varsa sonuna -2 eklenir)</>
                      : "Ad geçersiz: harf ya da rakam içermeli."}
                </p>
              </div>
            </div>

            {hata && (
              <div role="alert" className="flex items-start gap-2 rounded-[3px] border border-[rgb(var(--tone-danger-rgb))] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-[rgb(var(--tone-danger-rgb))]" />
                <span>{hata}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-1">
              <FlowButton size="sm" variant="secondary" onClick={onKapat} disabled={gonderiliyor}>
                Vazgeç
              </FlowButton>
              <FlowButton size="sm" disabled={!gecerli || gonderiliyor} onClick={() => void gonder()} title={!kart ? "Önce bir dava kartı seçin" : !turKodu ? "Belge türü seçin" : undefined}>
                {gonderiliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FilePlus2 className="w-3.5 h-3.5" />}
                Oluştur ve Word'de aç
              </FlowButton>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
