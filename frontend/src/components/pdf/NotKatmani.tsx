// Not katmanı (G272, plan §3 `not`, K7): büyük sayfa görünümünde tıkla → nokta + metin kutusu → "Notu ekle" anında
// `not` isteği (sayfa başına tek seferde bir not; her not yeni çıktı dosyası — zincir, sonraki not çıktıya eklenir).
// Koordinat görünür düzlem PDF puanı (`overlayNoktasi`); nokta işareti SVG'de puan koordinatıyla, metin kutusu noktanın
// yanında yüzde konumla (sağ/alt yarıda ters yöne açılır). Metin ≤ `NOT_MAX_KARAKTER`; boş ya da sınır üstü → düğme kapalı.
import { useEffect, useId, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Loader2, MessageSquareText, X } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import type { DosyaSayfasi, NotParametreleri } from "@/types/pdfAraclari";
import { NOT_MAX_KARAKTER, overlayNoktasi } from "./pdfKoordinat";
import { notMetniGecerli } from "./usePdfTezgah";

type Props = {
  sayfa: DosyaSayfasi;
  sayfaNo: number;
  aktif: boolean;
  mesgul: boolean;
  onEkle: (parametreler: NotParametreleri) => Promise<unknown> | void;
};

export function NotKatmani({ sayfa, sayfaNo, aktif, mesgul, onEkle }: Props) {
  const [nokta, setNokta] = useState<{ x: number; y: number } | null>(null);
  const [metin, setMetin] = useState("");
  const kutuRef = useRef<HTMLTextAreaElement | null>(null);
  const kimlik = useId();

  // Sayfa değişince ya da kip kapanınca bekleyen nokta düşer (sayfa başına tek nokta).
  useEffect(() => {
    setNokta(null);
    setMetin("");
  }, [sayfaNo, aktif]);

  useEffect(() => {
    if (nokta) kutuRef.current?.focus();
  }, [nokta]);

  const tikla = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!aktif || mesgul) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const p = overlayNoktasi(e, sayfa);
    if (!p) return;
    setNokta(p);
    e.preventDefault();
  };

  const gonder = () => {
    if (!nokta || !notMetniGecerli(metin) || mesgul) return;
    void onEkle({ sayfa: sayfaNo, x: nokta.x, y: nokta.y, metin: metin.trim() });
    setNokta(null);
    setMetin("");
  };

  const vazgec = () => {
    setNokta(null);
    setMetin("");
  };

  const gecerli = notMetniGecerli(metin);
  const sagda = nokta ? nokta.x > sayfa.genislik * 0.55 : false;
  const altta = nokta ? nokta.y > sayfa.yukseklik * 0.6 : false;
  const yuzdeX = nokta ? (nokta.x / sayfa.genislik) * 100 : 0;
  const yuzdeY = nokta ? (nokta.y / sayfa.yukseklik) * 100 : 0;

  return (
    <>
      <svg
        data-testid="not-katmani"
        data-aktif={aktif ? "true" : undefined}
        viewBox={`0 0 ${sayfa.genislik} ${sayfa.yukseklik}`}
        preserveAspectRatio="none"
        aria-label={aktif ? "Not noktası seçmek için tıklayın" : undefined}
        role={aktif ? "img" : undefined}
        className={["absolute inset-0 w-full h-full", aktif ? "cursor-cell" : "pointer-events-none"].join(" ")}
        onPointerDown={tikla}
      >
        {nokta && (
          <g data-testid="not-noktasi" transform={`translate(${nokta.x} ${nokta.y})`}>
            <circle r={6} fill="rgb(var(--tone-caution-rgb))" stroke="#fff" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </g>
        )}
      </svg>
      {nokta && (
        <div
          data-testid="not-kutusu"
          role="dialog"
          aria-label={`Sayfa ${sayfaNo} notu`}
          className="absolute z-10 w-[min(280px,80%)] flex flex-col gap-1.5 rounded-[3px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-2 shadow-lg"
          style={{
            left: sagda ? undefined : `calc(${yuzdeX}% + 10px)`,
            right: sagda ? `calc(${100 - yuzdeX}% + 10px)` : undefined,
            top: altta ? undefined : `${yuzdeY}%`,
            bottom: altta ? `${100 - yuzdeY}%` : undefined,
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-1.5">
            <MessageSquareText className="w-3.5 h-3.5 text-[var(--brand)]" />
            <label htmlFor={`${kimlik}-not`} className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">
              Not · s. {sayfaNo} ({Math.round(nokta.x)}, {Math.round(nokta.y)})
            </label>
            <span className="flex-1" />
            <button type="button" aria-label="Notu iptal et" onClick={vazgec} className="text-[var(--fg-subtle)] hover:text-[var(--fg)]">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <textarea
            id={`${kimlik}-not`}
            ref={kutuRef}
            value={metin}
            rows={3}
            maxLength={NOT_MAX_KARAKTER + 1}
            placeholder="Not metni"
            onChange={(e) => setMetin(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") vazgec();
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) gonder();
            }}
            className="w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)] resize-y"
          />
          <div className="flex items-center gap-2">
            <span
              data-testid="not-sayac"
              className={["font-mono text-[10px]", metin.length > NOT_MAX_KARAKTER ? "text-[rgb(var(--tone-danger-rgb))]" : "text-[var(--fg-subtle)]"].join(" ")}
            >
              {metin.length} / {NOT_MAX_KARAKTER}
            </span>
            <span className="flex-1" />
            <FlowButton size="sm" variant="secondary" onClick={vazgec}>
              Vazgeç
            </FlowButton>
            <FlowButton size="sm" disabled={!gecerli || mesgul} onClick={gonder} title="Ctrl+Enter">
              {mesgul ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <MessageSquareText className="w-3.5 h-3.5" />}
              Notu ekle
            </FlowButton>
          </div>
        </div>
      )}
    </>
  );
}
