// "Karta bağla" diyaloğu (G273, plan K4/K5/K17, §3 `karta-bagla`): tezgâhtaki çalışma dosyası tek diyalogla kartın
// belgesi olur. Dava arama mevcut `/api/cases/search` (tuş vuruşu yolu, `useCases().searchCases`, 350 ms debounce);
// seçilen kartın tarafları `getCase` ile tazelenir (arama yanıtı tarafsız olabilir). Belge türü mevcut doctype listesi
// (`useConfigList("doctypes")` — kod `_` pad'li gider, etiket gösterilir); taraf seçici kartın CLIENT tarafları (opsiyonel);
// yön Gelen/Giden; kayıt biçimi Kesinleştir (varsayılan) / Taslak (K12: PDF/A yok, Hukukbot yok, bildirim yok).
// `istek_kimligi` diyalog AÇILIŞINDA üretilir ve kapanana dek sabit kalır — tekrar tıklama aynı kimlikle gider, sunucu
// `reused: true` döner ("zaten bağlı"). Diyalog `theme-classic` taşır (portal kabuğun dışında). Native <select>/<input>
// (jsdom'da Radix seçici yok; IslemPaneli ile aynı karar).
import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router";
import { AlertCircle, CheckCircle2, Link2, Loader2, Search, X } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { useCases } from "@/hooks/useCases";
import { useConfigList } from "@/hooks/useConfig";
import { useDebounce } from "@/hooks/useDebounce";
import { hataMesaji, istekKimligiUret, kartaBagla } from "@/lib/pdfAraclariApi";
import type { BelgeDurumu, BelgeYonu, Dosya, KartOzeti, KartTarafi, KartaBaglaYaniti } from "@/types/pdfAraclari";

type Props = {
  acik: boolean;
  dosya: Dosya | null;
  /** `CaseDetails`'ten `location.state.case` ile gelen ön-seçili kart. */
  onSecilenKart?: KartOzeti | null;
  onKapat: () => void;
  onBasari?: (yanit: KartaBaglaYaniti, kart: KartOzeti) => void;
};

const GIRDI =
  "w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-60";
const ETIKET = "block font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] mb-1";

export const TASLAK_ACIKLAMASI = "Taslak: PDF/A yapılmaz, Hukukbot'a gitmez, bildirim üretmez; kartın Taslaklar bölümüne düşer.";

type AramaSonucu = KartOzeti & { subject?: string | null; file_type?: string | null };

function kartBasligi(k: KartOzeti): string {
  return k.tracking_no || k.esas_no || `Kart #${k.id}`;
}

function muvekkilAdi(k: KartOzeti): string | null {
  return k.parties?.find((p) => p.party_type === "CLIENT")?.name ?? null;
}

export function KartaBaglaDiyalogu({ acik, dosya, onSecilenKart, onKapat, onBasari }: Props) {
  const kimlik = useId();
  const { searchCases, getCase } = useCases();
  const { data: doctypes, error: doctypeHatasi } = useConfigList("doctypes");

  const [sorgu, setSorgu] = useState("");
  const gecikmeli = useDebounce(sorgu, 350);
  const [sonuclar, setSonuclar] = useState<AramaSonucu[]>([]);
  const [araniyor, setAraniyor] = useState(false);
  const [kart, setKart] = useState<KartOzeti | null>(null);
  const [taraflar, setTaraflar] = useState<KartTarafi[]>([]);
  const [turKodu, setTurKodu] = useState("");
  const [tarafId, setTarafId] = useState("");
  const [dosyaAdi, setDosyaAdi] = useState("");
  const [yon, setYon] = useState<BelgeYonu>("GELEN");
  const [durum, setDurum] = useState<BelgeDurumu>("KESIN");
  const [istekKimligi, setIstekKimligi] = useState("");
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [sonuc, setSonuc] = useState<KartaBaglaYaniti | null>(null);

  // Açılış: kimlik üret, formu kur (ön-seçili kart varsa onunla).
  useEffect(() => {
    if (!acik) return;
    setIstekKimligi(istekKimligiUret());
    setSorgu("");
    setSonuclar([]);
    setKart(onSecilenKart ?? null);
    setTaraflar(onSecilenKart?.parties ?? []);
    setTurKodu("");
    setTarafId("");
    setDosyaAdi(dosya?.ad ?? "");
    setYon("GELEN");
    setDurum("KESIN");
    setHata(null);
    setSonuc(null);
    setGonderiliyor(false);
  }, [acik, dosya, onSecilenKart]);

  // Arama (tuş vuruşu yolu).
  useEffect(() => {
    if (!acik || kart || gecikmeli.trim().length < 2) {
      setSonuclar([]);
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

  // Kart seçilince tarafları kartın kendisinden taze oku (arama yanıtı tarafsız olabilir).
  useEffect(() => {
    if (!acik || !kart) return;
    if (kart.parties && kart.parties.length > 0) {
      setTaraflar(kart.parties);
      return;
    }
    let iptal = false;
    (async () => {
      try {
        const detay = (await getCase(kart.id)) as { parties?: KartTarafi[]; tracking_no?: string; esas_no?: string } | null;
        if (iptal || !detay) return;
        setTaraflar(Array.isArray(detay.parties) ? detay.parties : []);
      } catch {
        /* taraf listesi opsiyonel */
      }
    })();
    return () => {
      iptal = true;
    };
  }, [acik, kart, getCase]);

  const muvekkiller = useMemo(() => taraflar.filter((p) => p.party_type === "CLIENT"), [taraflar]);
  const turler = useMemo(() => (doctypes ?? []).filter((d) => d.code), [doctypes]);
  const gecerli = !!dosya && !!kart && turKodu.trim().length > 0 && dosyaAdi.trim().length > 0 && !!istekKimligi;

  const gonder = async () => {
    if (!gecerli || !dosya || !kart || gonderiliyor) return;
    setGonderiliyor(true);
    setHata(null);
    try {
      const yanit = await kartaBagla({
        id: dosya.id,
        case_id: kart.id,
        belge_turu_kodu: turKodu,
        dosya_adi: dosyaAdi.trim(),
        case_party_id: tarafId ? Number(tarafId) : undefined,
        istek_kimligi: istekKimligi,
        yon,
        durum,
      });
      setSonuc(yanit);
      if (yanit.reused) {
        toast.info("Zaten bağlı", { description: `Bu dosya aynı istekle ${kartBasligi(kart)} kartına daha önce bağlanmış.` });
      } else {
        toast.success(durum === "TASLAK" ? "Taslak olarak kaydedildi" : "Karta bağlandı", {
          description: `${dosyaAdi.trim()} → ${kartBasligi(kart)}`,
        });
      }
      onBasari?.(yanit, kart);
    } catch (e) {
      setHata(hataMesaji(e));
    } finally {
      setGonderiliyor(false);
    }
  };

  return (
    <Dialog open={acik} onOpenChange={(v) => !v && !gonderiliyor && onKapat()}>
      <DialogContent
        data-testid="karta-bagla-diyalogu"
        className="theme-classic max-w-[640px] max-h-[90vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-[18px]">
            <Link2 className="w-4 h-4 text-[var(--brand)]" />
            Karta bağla
          </DialogTitle>
          <DialogDescription>
            {dosya ? (
              <>
                <span className="font-medium text-[var(--fg)] break-all">{dosya.ad}</span> · {dosya.sayfa} sayfa — kartın belgesi olur; analiz koşmaz, e-posta gitmez.
              </>
            ) : (
              "Önce soldan bir dosya seçin."
            )}
          </DialogDescription>
        </DialogHeader>

        {sonuc ? (
          <div data-testid="karta-bagla-sonuc" className="flex flex-col gap-3 py-2">
            <div className="flex items-start gap-2 rounded-[3px] border border-[rgb(var(--tone-ok-rgb))] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]">
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-[rgb(var(--tone-ok-rgb))]" />
              <span>
                {sonuc.reused ? "Bu dosya bu istekle zaten bağlıydı" : durum === "TASLAK" ? "Taslak olarak kaydedildi" : "Karta bağlandı"} — belge #{sonuc.document_id}
                {kart ? ` · ${kartBasligi(kart)}` : ""}.
              </span>
            </div>
            <div className="flex items-center gap-2">
              {kart && (
                <Link
                  to={`/cases/${kart.id}`}
                  className="inline-flex items-center gap-2 rounded-[3px] border border-[var(--brand)] bg-[var(--brand-soft)] px-3 py-1.5 text-[12px] font-medium text-[var(--brand)]"
                >
                  Karta git
                </Link>
              )}
              <FlowButton size="sm" variant="secondary" onClick={onKapat}>
                Kapat
              </FlowButton>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4 py-1">
            {/* Dava */}
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
                  {!onSecilenKart && (
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
                <select id={`${kimlik}-tur`} className={GIRDI} value={turKodu} onChange={(e) => setTurKodu(e.target.value)}>
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
                <label className={ETIKET} htmlFor={`${kimlik}-ad`}>Dosya adı</label>
                <input id={`${kimlik}-ad`} className={GIRDI} value={dosyaAdi} maxLength={255} onChange={(e) => setDosyaAdi(e.target.value)} />
              </div>
            </div>

            <fieldset className="flex flex-wrap gap-4">
              <legend className={ETIKET}>Yön</legend>
              {(["GELEN", "GIDEN"] as BelgeYonu[]).map((y) => (
                <label key={y} className="flex items-center gap-2 text-[13px] text-[var(--fg)]">
                  <input type="radio" name={`${kimlik}-yon`} value={y} checked={yon === y} onChange={() => setYon(y)} className="accent-[var(--brand)]" />
                  {y === "GELEN" ? "Gelen" : "Giden"}
                </label>
              ))}
            </fieldset>

            <fieldset className="flex flex-col gap-1.5">
              <legend className={ETIKET}>Kayıt biçimi</legend>
              <label className="flex items-center gap-2 text-[13px] text-[var(--fg)]">
                <input type="radio" name={`${kimlik}-durum`} value="KESIN" checked={durum === "KESIN"} onChange={() => setDurum("KESIN")} className="accent-[var(--brand)]" />
                Kesinleştir
                <span className="text-[11px] text-[var(--fg-subtle)]">— PDF/A, arşiv, bildirim; türe göre Hukukbot</span>
              </label>
              <label className="flex items-center gap-2 text-[13px] text-[var(--fg)]">
                <input type="radio" name={`${kimlik}-durum`} value="TASLAK" checked={durum === "TASLAK"} onChange={() => setDurum("TASLAK")} className="accent-[var(--brand)]" />
                Taslak olarak kaydet
              </label>
              {durum === "TASLAK" && <p className="text-[11px] text-[var(--fg-muted)]">{TASLAK_ACIKLAMASI}</p>}
            </fieldset>

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
                {gonderiliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Link2 className="w-3.5 h-3.5" />}
                {durum === "TASLAK" ? "Taslak kaydet" : "Karta bağla"}
              </FlowButton>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
