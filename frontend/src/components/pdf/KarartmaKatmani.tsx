// Karartma katmanı (G272, plan K6): büyük sayfa görünümünün üstünde SVG overlay — sürükle → dikdörtgen. Overlay'in
// `viewBox`'ı sayfanın PDF puanı boyutudur (`preserveAspectRatio="none"`), bu yüzden alanlar doğrudan puan
// koordinatıyla çizilir; yalnız fare/kalem/parmak konumu piksel → puan çevrilir (`pdfKoordinat.pikseldenPuana`,
// ölçek = sayfa.genislik / overlay genişliği). Pointer events: fare + kalem + parmak tek yol; `touch-action: none` yalnız
// kip açıkken (SayfaGorunumu kapsayıcıda verir) — kapalıyken kaydırma serbest, overlay tıklamayı geçirir.
// `KARARTMA_MIN_PT` altındaki sürükleme yok sayılır (hook `karartmaEkle` da reddeder). Alanlar `KarartmaListesi`'nde
// (sayfa, boyut, sil); "Karart" düğmesi onay kutusu işaretlenmeden AÇILMAZ — karartma geri alınamaz.
import { useId, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Eraser, Loader2, Trash2 } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import type { DosyaSayfasi, KarartmaAlani } from "@/types/pdfAraclari";
import { alanBoyutMetni, dikdortgenNormalize, karartmaAlaniGecerli, overlayNoktasi, type Dikdortgen } from "./pdfKoordinat";

type KatmanProps = {
  sayfa: DosyaSayfasi;
  sayfaNo: number;
  /** Dosyanın TÜM alanları; bu sayfadakiler çizilir. */
  alanlar: KarartmaAlani[];
  /** Çizim kipi "karart" mı (pointer olayları yalnız o zaman). */
  aktif: boolean;
  onEkle: (alan: KarartmaAlani) => boolean;
};

export const KARARTMA_ONAY_METNI = "Karartma geri alınamaz; metin ve görüntü kalıcı silinir.";

export function KarartmaKatmani({ sayfa, sayfaNo, alanlar, aktif, onEkle }: KatmanProps) {
  const [taslak, setTaslak] = useState<Dikdortgen | null>(null);
  const pointerId = useRef<number | null>(null);
  const buSayfa = alanlar.filter((a) => a.sayfa === sayfaNo);

  const yakala = (e: ReactPointerEvent<SVGSVGElement>) => {
    const el = e.currentTarget;
    if (typeof el.setPointerCapture === "function") {
      try {
        el.setPointerCapture(e.pointerId);
      } catch {
        /* jsdom / eski tarayıcı */
      }
    }
  };

  const basla = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!aktif || pointerId.current !== null) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const p = overlayNoktasi(e, sayfa);
    if (!p) return;
    pointerId.current = e.pointerId ?? 0;
    yakala(e);
    setTaslak({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
    e.preventDefault();
  };

  const surukle = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!aktif || pointerId.current === null || !taslak) return;
    if ((e.pointerId ?? 0) !== pointerId.current) return;
    const p = overlayNoktasi(e, sayfa);
    if (!p) return;
    setTaslak({ ...taslak, x1: p.x, y1: p.y });
  };

  const bitir = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (pointerId.current === null) return;
    if ((e.pointerId ?? 0) !== pointerId.current) return;
    pointerId.current = null;
    const son = taslak;
    setTaslak(null);
    if (!son || !aktif) return;
    const p = overlayNoktasi(e, sayfa);
    const alan = dikdortgenNormalize(p ? { ...son, x1: p.x, y1: p.y } : son);
    if (!karartmaAlaniGecerli(alan)) return; // sürükleme hatası / tıklama: yok say
    onEkle({ sayfa: sayfaNo, ...alan });
  };

  const iptal = () => {
    pointerId.current = null;
    setTaslak(null);
  };

  const taslakN = taslak ? dikdortgenNormalize(taslak) : null;

  return (
    <svg
      data-testid="karartma-katmani"
      data-aktif={aktif ? "true" : undefined}
      viewBox={`0 0 ${sayfa.genislik} ${sayfa.yukseklik}`}
      preserveAspectRatio="none"
      aria-label={aktif ? "Karartma alanı çizmek için sürükleyin" : undefined}
      role={aktif ? "img" : undefined}
      className={["absolute inset-0 w-full h-full", aktif ? "cursor-crosshair" : "pointer-events-none"].join(" ")}
      onPointerDown={basla}
      onPointerMove={surukle}
      onPointerUp={bitir}
      onPointerCancel={iptal}
    >
      {buSayfa.map((a, i) => {
        const n = dikdortgenNormalize(a);
        return (
          <rect
            key={`${i}-${n.x0}-${n.y0}`}
            data-testid="karartma-alani"
            x={n.x0}
            y={n.y0}
            width={n.x1 - n.x0}
            height={n.y1 - n.y0}
            fill="rgba(0,0,0,0.55)"
            stroke="rgb(var(--tone-danger-rgb))"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
      {taslakN && (
        <rect
          data-testid="karartma-taslagi"
          x={taslakN.x0}
          y={taslakN.y0}
          width={taslakN.x1 - taslakN.x0}
          height={taslakN.y1 - taslakN.y0}
          fill="rgba(0,0,0,0.35)"
          stroke="rgb(var(--tone-danger-rgb))"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />
      )}
    </svg>
  );
}

type ListeProps = {
  alanlar: KarartmaAlani[];
  mesgul: boolean;
  onSil: (indeks: number) => void;
  onTemizle: () => void;
  onKarart: () => void;
};

/** Biriken alanlar (birden çok sayfa) + geri alınamazlık onayı + "Karart" (tek istek). */
export function KarartmaListesi({ alanlar, mesgul, onSil, onTemizle, onKarart }: ListeProps) {
  const [onayli, setOnayli] = useState(false);
  const kimlik = useId();
  const bos = alanlar.length === 0;

  return (
    <section
      data-testid="karartma-listesi"
      aria-label="Karartma alanları"
      className="flex flex-col gap-2 rounded-[3px] border border-[var(--border)] bg-[var(--bg-elevated)] p-3"
    >
      <div className="flex items-center gap-2">
        <Eraser className="w-4 h-4 text-[var(--brand)]" />
        <span className="font-display text-[14px] font-medium text-[var(--fg)]">Karartma</span>
        <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">{alanlar.length} alan</span>
        <span className="flex-1" />
        {!bos && (
          <button type="button" onClick={onTemizle} disabled={mesgul} className="text-[12px] text-[var(--fg-muted)] hover:text-[var(--fg)] underline-offset-2 hover:underline disabled:opacity-50">
            Tümünü kaldır
          </button>
        )}
      </div>
      {bos ? (
        <p className="text-[12px] text-[var(--fg-muted)]">Büyük görünümde fareyle (ya da parmakla) sürükleyerek alan çizin; alanlar birden çok sayfada birikir.</p>
      ) : (
        <ul className="flex flex-col gap-1 max-h-40 overflow-y-auto" aria-label="Alan listesi">
          {alanlar.map((a, i) => (
            <li key={`${a.sayfa}-${i}`} data-testid="karartma-satiri" className="flex items-center gap-2 text-[12px] text-[var(--fg)]">
              <span className="font-mono text-[11px]">
                <span className="text-[var(--fg-muted)]">s. {a.sayfa}</span> · {alanBoyutMetni(a)}
              </span>
              <span className="flex-1" />
              <button
                type="button"
                aria-label={`Alan ${i + 1}'i sil`}
                disabled={mesgul}
                onClick={() => onSil(i)}
                className="w-6 h-6 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[rgb(var(--tone-danger-rgb))] disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <label htmlFor={`${kimlik}-onay`} className="flex items-start gap-2 text-[12px] text-[var(--fg)] cursor-pointer">
        <input
          id={`${kimlik}-onay`}
          type="checkbox"
          data-testid="karartma-onayi"
          checked={onayli}
          disabled={mesgul}
          onChange={(e) => setOnayli(e.target.checked)}
          className="mt-0.5 accent-[var(--brand)]"
        />
        <span>{KARARTMA_ONAY_METNI}</span>
      </label>
      <FlowButton size="sm" disabled={bos || !onayli || mesgul} onClick={onKarart} title={!onayli ? "Önce geri alınamazlık onayını işaretleyin" : undefined}>
        {mesgul ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eraser className="w-3.5 h-3.5" />}
        Karart
      </FlowButton>
    </section>
  );
}
