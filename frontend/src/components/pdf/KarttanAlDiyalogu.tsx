// "Karttan al" diyaloğu (G273, plan K5, §3 `karttan-al`): dava ara → kartın belge listesi (`GET /api/cases/{id}`
// `documents`; `sharepoint_url` dolu olanlar seçilebilir, diğerleri soluk "arşivde yok") → çoklu seçim → her belge için
// SIRAYLA `karttanAl(document_id)` (sunucu semaforu 2; bir belgenin hatası diğerlerini durdurmaz) → tezgâh listesine düşer.
// "Al ve birleştir" kısayolu alınan dosyaları seçilen sırayla `birlestir`e verir (çağıran koşar). Diyalog `theme-classic`.
import { useEffect, useId, useState } from "react";
import { AlertCircle, CheckCircle2, Combine, FileDown, Loader2, Search, X } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { useCases } from "@/hooks/useCases";
import { useDebounce } from "@/hooks/useDebounce";
import { hataMesaji, karttanAl } from "@/lib/pdfAraclariApi";
import type { Dosya, KartOzeti } from "@/types/pdfAraclari";

export type KartBelgesi = {
  id: number;
  original_filename?: string;
  stored_filename?: string;
  belge_turu_adi?: string;
  sharepoint_url?: string | null;
  uploaded_at?: string;
  durum?: string;
  yon?: string;
};

type Props = {
  acik: boolean;
  onKapat: () => void;
  /** Alınan dosyalar (sırayla) tezgâh listesine. */
  onDosyalar: (dosyalar: Dosya[]) => void;
  /** "Al ve birleştir": alınan dosyalar seçilen sırayla `birlestir`e. */
  onBirlestir?: (dosyalar: Dosya[]) => void;
};

type SatirDurumu = { id: number; durum: "bekliyor" | "aliniyor" | "tamam" | "hata"; mesaj?: string };

const GIRDI =
  "w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)]";
const ETIKET = "block font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] mb-1";

function belgeAdi(b: KartBelgesi): string {
  return b.original_filename || b.stored_filename || `Belge #${b.id}`;
}

export function KarttanAlDiyalogu({ acik, onKapat, onDosyalar, onBirlestir }: Props) {
  const kimlik = useId();
  const { searchCases, getCase } = useCases();
  const [sorgu, setSorgu] = useState("");
  const gecikmeli = useDebounce(sorgu, 350);
  const [sonuclar, setSonuclar] = useState<KartOzeti[]>([]);
  const [araniyor, setAraniyor] = useState(false);
  const [kart, setKart] = useState<KartOzeti | null>(null);
  const [belgeler, setBelgeler] = useState<KartBelgesi[] | null>(null);
  const [belgeHatasi, setBelgeHatasi] = useState<string | null>(null);
  const [secili, setSecili] = useState<number[]>([]); // seçim sırası = birleştirme sırası
  const [satirlar, setSatirlar] = useState<SatirDurumu[]>([]);
  const [aliniyor, setAliniyor] = useState(false);

  useEffect(() => {
    if (!acik) return;
    setSorgu("");
    setSonuclar([]);
    setKart(null);
    setBelgeler(null);
    setBelgeHatasi(null);
    setSecili([]);
    setSatirlar([]);
    setAliniyor(false);
  }, [acik]);

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
        if (!iptal) setSonuclar((liste as KartOzeti[]).slice(0, 8));
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

  // Kart seçilince belge listesi karttan.
  useEffect(() => {
    if (!acik || !kart) return;
    let iptal = false;
    setBelgeler(null);
    setBelgeHatasi(null);
    (async () => {
      try {
        const detay = (await getCase(kart.id)) as { documents?: KartBelgesi[] } | null;
        if (iptal) return;
        if (!detay) {
          setBelgeHatasi("Dava kartı alınamadı.");
          setBelgeler([]);
          return;
        }
        setBelgeler(Array.isArray(detay.documents) ? detay.documents : []);
      } catch (e) {
        if (!iptal) {
          setBelgeHatasi(hataMesaji(e));
          setBelgeler([]);
        }
      }
    })();
    return () => {
      iptal = true;
    };
  }, [acik, kart, getCase]);

  const secToggle = (id: number) =>
    setSecili((onceki) => (onceki.includes(id) ? onceki.filter((x) => x !== id) : [...onceki, id]));

  /** Seçilenleri SIRAYLA alır; hata satırda kalır, diğerleri sürer. Başarılı dosyalar listeye düşer. */
  const al = async (birlestir: boolean) => {
    if (secili.length === 0 || aliniyor) return;
    setAliniyor(true);
    setSatirlar(secili.map((id) => ({ id, durum: "bekliyor" })));
    const alinanlar: Dosya[] = [];
    for (const id of secili) {
      setSatirlar((o) => o.map((s) => (s.id === id ? { ...s, durum: "aliniyor" } : s)));
      try {
        const dosya = await karttanAl(id);
        alinanlar.push(dosya);
        setSatirlar((o) => o.map((s) => (s.id === id ? { ...s, durum: "tamam" } : s)));
      } catch (e) {
        setSatirlar((o) => o.map((s) => (s.id === id ? { ...s, durum: "hata", mesaj: hataMesaji(e) } : s)));
      }
    }
    setAliniyor(false);
    if (alinanlar.length > 0) onDosyalar(alinanlar);
    if (birlestir && alinanlar.length >= 2) onBirlestir?.(alinanlar);
    const hataVar = secili.length !== alinanlar.length;
    if (!hataVar) onKapat();
  };

  const alinabilir = (b: KartBelgesi) => !!b.sharepoint_url;
  const durumu = (id: number) => satirlar.find((s) => s.id === id);

  return (
    <Dialog open={acik} onOpenChange={(v) => !v && !aliniyor && onKapat()}>
      <DialogContent
        data-testid="karttan-al-diyalogu"
        className="theme-classic max-w-[640px] max-h-[90vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-[18px]">
            <FileDown className="w-4 h-4 text-[var(--brand)]" />
            Karttan al
          </DialogTitle>
          <DialogDescription>Kartın arşivdeki belgeleri tezgâha çalışma dosyası olarak gelir (kopya; kart belgesi değişmez).</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-1">
          <div>
            <span className={ETIKET}>Dava kartı</span>
            {kart ? (
              <div data-testid="secili-kart" className="flex items-start gap-2 rounded-[3px] border border-[var(--brand)] bg-[var(--brand-soft)] px-3 py-2">
                <div className="min-w-0 flex-1 text-[13px] text-[var(--fg)]">
                  <div className="font-medium tabular-nums">{kart.tracking_no || kart.esas_no || `Kart #${kart.id}`}</div>
                  <div className="text-[12px] text-[var(--fg-muted)] truncate">{[kart.esas_no, kart.court].filter(Boolean).join(" · ")}</div>
                </div>
                <button
                  type="button"
                  aria-label="Kart seçimini kaldır"
                  disabled={aliniyor}
                  onClick={() => {
                    setKart(null);
                    setBelgeler(null);
                    setSecili([]);
                    setSatirlar([]);
                  }}
                  className="text-[var(--fg-subtle)] hover:text-[var(--fg)] disabled:opacity-50"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                <input aria-label="Dava ara" className={`${GIRDI} pl-8`} placeholder="Ofis no, esas no ya da taraf adı…" value={sorgu} onChange={(e) => setSorgu(e.target.value)} autoFocus />
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
                            <div className="text-[13px] font-medium tabular-nums text-[var(--fg)]">{c.tracking_no || c.esas_no || `Kart #${c.id}`}</div>
                            <div className="text-[11px] text-[var(--fg-muted)] truncate">{[c.esas_no, c.court, c.status].filter(Boolean).join(" · ")}</div>
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>

          {kart && (
            <div>
              <span className={ETIKET}>Belgeler</span>
              {belgeler === null ? (
                <p className="text-[12px] text-[var(--fg-muted)] flex items-center gap-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Belge listesi alınıyor…
                </p>
              ) : belgeHatasi ? (
                <p role="alert" className="text-[12px] text-[rgb(var(--tone-danger-rgb))]">{belgeHatasi}</p>
              ) : belgeler.length === 0 ? (
                <p className="text-[12px] text-[var(--fg-muted)]">Kartta belge yok.</p>
              ) : (
                <ul data-testid="kart-belgeleri" className="flex flex-col gap-1 max-h-64 overflow-y-auto">
                  {belgeler.map((b) => {
                    const uygun = alinabilir(b);
                    const d = durumu(b.id);
                    return (
                      <li key={b.id} data-belge-id={b.id} className={["flex items-center gap-2 rounded-[3px] border border-[var(--border)] px-2 py-1.5 text-[12px]", uygun ? "" : "opacity-50"].join(" ")}>
                        <input
                          type="checkbox"
                          id={`${kimlik}-b-${b.id}`}
                          aria-label={`Seç: ${belgeAdi(b)}`}
                          checked={secili.includes(b.id)}
                          disabled={!uygun || aliniyor}
                          onChange={() => secToggle(b.id)}
                          className="accent-[var(--brand)]"
                        />
                        <label htmlFor={`${kimlik}-b-${b.id}`} className="min-w-0 flex-1 cursor-pointer">
                          <span className="block truncate text-[var(--fg)]">{belgeAdi(b)}</span>
                          <span className="block text-[11px] text-[var(--fg-muted)] truncate">
                            {[b.belge_turu_adi, b.durum === "TASLAK" ? "taslak" : null, uygun ? null : "arşivde yok"].filter(Boolean).join(" · ")}
                          </span>
                        </label>
                        {secili.includes(b.id) && <span className="font-mono text-[10px] text-[var(--fg-subtle)]">#{secili.indexOf(b.id) + 1}</span>}
                        {d?.durum === "aliniyor" && <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--fg-subtle)]" />}
                        {d?.durum === "tamam" && <CheckCircle2 className="w-3.5 h-3.5 text-[rgb(var(--tone-ok-rgb))]" />}
                        {d?.durum === "hata" && (
                          <span title={d.mesaj} className="flex items-center gap-1 text-[rgb(var(--tone-danger-rgb))]">
                            <AlertCircle className="w-3.5 h-3.5" />
                            <span className="text-[11px]">{d.mesaj}</span>
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <span className="mr-auto font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">{secili.length} seçili</span>
            <FlowButton size="sm" variant="secondary" onClick={onKapat} disabled={aliniyor}>
              Kapat
            </FlowButton>
            <FlowButton size="sm" variant="secondary" disabled={secili.length < 2 || aliniyor || !onBirlestir} onClick={() => void al(true)} title="Seçilen sırayla tek PDF olur">
              <Combine className="w-3.5 h-3.5" />
              Al ve birleştir
            </FlowButton>
            <FlowButton size="sm" disabled={secili.length === 0 || aliniyor} onClick={() => void al(false)}>
              {aliniyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileDown className="w-3.5 h-3.5" />}
              Tezgâha al
            </FlowButton>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
