// Sayfa kartı (G271): küçük resim + döndür/sil/seç. Önizleme YALNIZ kart görünür olunca çekilir (IntersectionObserver;
// 100+ sayfada ekran dışı kartlar istek atmaz) ve Bearer gerektirdiğinden `<img src>` ile değil `onizlemeBlob` + blob URL
// ile yüklenir; URL kart kalkınca serbest bırakılır. Döndürme CSS ile anında görünür (sunucuya "Uygula" ile gider).
// Sürükleme tutamacı ayrı (kutular/düğmeler çalışsın); klavye: tutamaca odak + boşluk + ok tuşları (dnd-kit).
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, RotateCw, Trash2, Undo2 } from "lucide-react";
import { onizlemeBlob } from "@/lib/pdfAraclariApi";
import type { DosyaSayfasi } from "@/types/pdfAraclari";
import type { SayfaDurumu } from "./usePdfTezgah";

export const ONIZLEME_GENISLIK = 240;

type Props = {
  dosyaId: string;
  sayfa: DosyaSayfasi | undefined;
  durum: SayfaDurumu;
  sira: number;
  secili: boolean;
  onDondur: (no: number) => void;
  onSil: (no: number) => void;
  onSec: (no: number, secili: boolean, aralik: boolean) => void;
};

type OnizlemeDurumu = "bekliyor" | "yukleniyor" | "hazir" | "hata";

/** Görünürlük: `IntersectionObserver` yoksa (eski tarayıcı/test) hemen görünür sayılır. */
function useGorunur(ref: React.RefObject<HTMLElement | null>): boolean {
  const [gorunur, setGorunur] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setGorunur(true);
      return;
    }
    const gozcu = new IntersectionObserver(
      (girdiler) => {
        if (girdiler.some((g) => g.isIntersecting)) {
          setGorunur(true);
          gozcu.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    gozcu.observe(el);
    return () => gozcu.disconnect();
  }, [ref]);
  return gorunur;
}

export function SayfaKarti({ dosyaId, sayfa, durum, sira, secili, onDondur, onSil, onSec }: Props) {
  const { no, dondur, silindi } = durum;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: no });
  const kartRef = useRef<HTMLLIElement | null>(null);
  const gorunur = useGorunur(kartRef);
  const [onizleme, setOnizleme] = useState<OnizlemeDurumu>("bekliyor");
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!gorunur) return;
    let iptal = false;
    let blobUrl: string | null = null;
    setOnizleme("yukleniyor");
    onizlemeBlob(dosyaId, no, ONIZLEME_GENISLIK)
      .then((blob) => {
        if (iptal) return;
        blobUrl = URL.createObjectURL(blob);
        setUrl(blobUrl);
        setOnizleme("hazir");
      })
      .catch(() => {
        if (!iptal) setOnizleme("hata");
      });
    return () => {
      iptal = true;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [gorunur, dosyaId, no]);

  const oran = sayfa && sayfa.genislik > 0 ? sayfa.yukseklik / sayfa.genislik : 1.414;
  const yan = dondur === 90 || dondur === 270;
  const stil: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : undefined,
    position: isDragging ? "relative" : undefined,
  };

  return (
    <li
      ref={(el) => {
        setNodeRef(el);
        kartRef.current = el;
      }}
      style={stil}
      role="listitem"
      data-sayfa-no={no}
      data-silindi={silindi ? "true" : undefined}
      data-onizleme={onizleme}
      aria-label={`Sayfa ${no}, sıra ${sira}${dondur ? `, ${dondur}° döndürülmüş` : ""}${silindi ? ", silinecek" : ""}`}
      className={[
        "group relative flex flex-col gap-1 rounded-[3px] border p-1.5 bg-[var(--bg-elevated)] transition-colors",
        "focus-within:ring-2 focus-within:ring-[var(--ring)]",
        secili ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)] hover:border-[var(--border-strong)]",
        silindi ? "opacity-40" : "",
        isDragging ? "shadow-lg" : "",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-1">
        <label className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.08em] uppercase text-[var(--fg-muted)] cursor-pointer">
          <input
            type="checkbox"
            aria-label={`Sayfa ${no}'i seç`}
            checked={secili}
            disabled={silindi}
            onClick={(e) => onSec(no, !secili, e.shiftKey)}
            onChange={() => undefined}
            className="accent-[var(--brand)]"
          />
          <span>s. {no}</span>
          {sira !== no && <span className="text-[var(--fg-subtle)]">→ {sira}</span>}
        </label>
        <button
          type="button"
          aria-label={`Sayfa ${no}'i sürükle`}
          title="Sürükleyin ya da odaklayıp boşluk + ok tuşlarıyla taşıyın"
          {...attributes}
          {...listeners}
          className="w-6 h-6 grid place-items-center cursor-grab text-[var(--fg-subtle)] hover:text-[var(--fg)] rounded-[3px] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </button>
      </div>

      <div
        className="relative w-full overflow-hidden rounded-[2px] bg-[var(--bg)] border border-[var(--border)] grid place-items-center"
        style={{ aspectRatio: yan ? String(oran) : String(1 / oran) }}
      >
        {onizleme === "hazir" && url ? (
          <img
            src={url}
            alt={`Sayfa ${no} önizlemesi`}
            loading="lazy"
            draggable={false}
            className="max-w-full max-h-full object-contain transition-transform"
            style={{ transform: `rotate(${dondur}deg)`, ...(yan ? { maxWidth: "none", width: "auto", height: "100%" } : {}) }}
          />
        ) : onizleme === "hata" ? (
          <span className="px-2 text-center text-[11px] text-[var(--fg-subtle)]">Önizleme yok</span>
        ) : (
          <span aria-hidden="true" className="absolute inset-0 animate-pulse bg-[var(--bg-sunken,var(--bg))]" />
        )}
      </div>

      <div className="flex items-center justify-between gap-1">
        <button
          type="button"
          aria-label={`Sayfa ${no}'i döndür`}
          title="90° sağa döndür"
          disabled={silindi}
          onClick={() => onDondur(no)}
          className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] disabled:opacity-30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <RotateCw className="w-3.5 h-3.5" />
        </button>
        {dondur !== 0 && <span className="font-mono text-[10px] text-[var(--fg-subtle)]">{dondur}°</span>}
        <button
          type="button"
          aria-label={silindi ? `Sayfa ${no}'i geri al` : `Sayfa ${no}'i sil`}
          title={silindi ? "Geri al" : "Sil (Uygula ile kesinleşir)"}
          onClick={() => onSil(no)}
          className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[rgb(var(--tone-danger-rgb))] hover:bg-[var(--bg)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          {silindi ? <Undo2 className="w-3.5 h-3.5" /> : <Trash2 className="w-3.5 h-3.5" />}
        </button>
      </div>
    </li>
  );
}
