// Büyük sayfa görünümü (G272): seçili sayfanın `onizlemeBlob(id, no, 1200)` görüntüsü kapsayıcıya sığar (genişlik %100,
// kutu oranı = sayfanın görünür boyutu, böylece overlay görüntü yüklenmeden de hizalıdır); üstünde iki SVG katman:
// `KarartmaKatmani` (alanlar + sürükleme) ve `NotKatmani` (nokta + metin kutusu). Yalnız aktif kipin katmanı pointer
// alır; kip kapalıyken ikisi de tıklamayı geçirir ve `touch-action` serbesttir (kaydırma); kip açıkken kapsayıcıda
// `touch-action: none` (parmakla çizim kaydırmayla çakışmaz). Sayfa değiştirme: önceki/sonraki düğmeleri + ←/→
// (metin alanlarında değil); ızgaraya dönüş düğmesi. Görüntü Bearer istediğinden blob URL (G271 deseni), kalkınca serbest.
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Eraser, LayoutGrid, MessageSquareText } from "lucide-react";
import { onizlemeBlob } from "@/lib/pdfAraclariApi";
import type { Dosya, DosyaSayfasi, KarartmaAlani, NotParametreleri } from "@/types/pdfAraclari";
import { KarartmaKatmani } from "./KarartmaKatmani";
import { NotKatmani } from "./NotKatmani";
import type { CizimKipi } from "./usePdfTezgah";

export const BUYUK_ONIZLEME_GENISLIK = 1200;

type Props = {
  dosya: Dosya;
  sayfaNo: number;
  cizimKipi: CizimKipi;
  karartmaAlanlari: KarartmaAlani[];
  mesgul: boolean;
  onIzgara: () => void;
  onSayfaGit: (adim: number) => void;
  onKip: (kip: CizimKipi) => void;
  onKarartmaEkle: (alan: KarartmaAlani) => boolean;
  onNotEkle: (parametreler: NotParametreleri) => Promise<unknown> | void;
};

type OnizlemeDurumu = "yukleniyor" | "hazir" | "hata";

function metinAlanindaMi(hedef: EventTarget | null): boolean {
  if (!(hedef instanceof HTMLElement)) return false;
  const etiket = hedef.tagName;
  return etiket === "INPUT" || etiket === "TEXTAREA" || etiket === "SELECT" || hedef.isContentEditable;
}

const KIP_DUGMESI =
  "inline-flex items-center gap-1.5 rounded-[3px] border px-2.5 py-1 text-[12px] font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] disabled:opacity-50 disabled:cursor-not-allowed";

export function SayfaGorunumu({ dosya, sayfaNo, cizimKipi, karartmaAlanlari, mesgul, onIzgara, onSayfaGit, onKip, onKarartmaEkle, onNotEkle }: Props) {
  const sayfa: DosyaSayfasi = dosya.sayfalar.find((s) => s.no === sayfaNo) ?? { no: sayfaNo, genislik: 595, yukseklik: 842 };
  const [onizleme, setOnizleme] = useState<OnizlemeDurumu>("yukleniyor");
  const [url, setUrl] = useState<string | null>(null);
  const toplam = Math.max(dosya.sayfa, 1);

  useEffect(() => {
    let iptal = false;
    let blobUrl: string | null = null;
    setOnizleme("yukleniyor");
    setUrl(null);
    onizlemeBlob(dosya.id, sayfaNo, BUYUK_ONIZLEME_GENISLIK)
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
  }, [dosya.id, sayfaNo]);

  useEffect(() => {
    const dinle = (e: KeyboardEvent) => {
      if (metinAlanindaMi(e.target)) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onSayfaGit(-1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onSayfaGit(1);
      }
    };
    window.addEventListener("keydown", dinle);
    return () => window.removeEventListener("keydown", dinle);
  }, [onSayfaGit]);

  const kipAcik = cizimKipi !== "yok";
  const kipDugmesi = (kip: Exclude<CizimKipi, "yok">, Ikon: typeof Eraser, ad: string, ipucu: string) => {
    const aktif = cizimKipi === kip;
    return (
      <button
        type="button"
        aria-pressed={aktif}
        data-testid={`kip-${kip}`}
        title={ipucu}
        onClick={() => onKip(kip)}
        className={[
          KIP_DUGMESI,
          aktif ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand)]" : "border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)]",
        ].join(" ")}
      >
        <Ikon className="w-3.5 h-3.5" />
        {ad}
      </button>
    );
  };

  return (
    <div data-testid="sayfa-gorunumu" className="flex flex-col gap-3 h-full min-h-0">
      <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
        <button
          type="button"
          onClick={onIzgara}
          className={[KIP_DUGMESI, "border-[var(--border-strong)] text-[var(--fg-muted)] hover:text-[var(--fg)]"].join(" ")}
          title="Sayfa ızgarasına dön"
        >
          <LayoutGrid className="w-3.5 h-3.5" />
          Izgara
        </button>
        <span className="mx-1 h-4 w-px bg-[var(--border)]" aria-hidden="true" />
        <button
          type="button"
          aria-label="Önceki sayfa"
          disabled={sayfaNo <= 1}
          onClick={() => onSayfaGit(-1)}
          className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg)] disabled:opacity-30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <span data-testid="sayfa-sayaci" className="font-mono text-[11px] tracking-[0.08em] uppercase text-[var(--fg-muted)]" aria-live="polite">
          Sayfa {sayfaNo} / {toplam}
        </span>
        <button
          type="button"
          aria-label="Sonraki sayfa"
          disabled={sayfaNo >= toplam}
          onClick={() => onSayfaGit(1)}
          className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg)] disabled:opacity-30 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <span className="flex-1" />
        {kipDugmesi("karart", Eraser, "Karart", "Sürükleyerek karartma alanı çizin")}
        {kipDugmesi("not", MessageSquareText, "Not", "Tıklayarak not noktası seçin")}
      </div>
      <p className="px-3 -mt-1 text-[11px] text-[var(--fg-subtle)]">
        {cizimKipi === "karart"
          ? "Sürükleyerek dikdörtgen çizin; alanlar listede birikir, \"Karart\" tek seferde uygular."
          : cizimKipi === "not"
            ? "Not koyacağınız yere tıklayın, metni yazın; her not yeni bir dosya üretir."
            : "←/→ ile sayfa değiştirin; karartma ya da not için kipi açın."}
      </p>
      <div className="px-3 pb-3 overflow-y-auto min-h-0">
        <div
          data-testid="cizim-katmani"
          className="relative w-full max-w-full mx-auto overflow-hidden rounded-[2px] bg-[var(--bg)] border border-[var(--border)] select-none"
          style={{ aspectRatio: `${sayfa.genislik} / ${sayfa.yukseklik}`, touchAction: kipAcik ? "none" : "auto" }}
        >
          {onizleme === "hazir" && url ? (
            <img src={url} alt={`Sayfa ${sayfaNo} büyük önizlemesi`} draggable={false} className="block w-full h-full object-fill" />
          ) : onizleme === "hata" ? (
            <span className="absolute inset-0 grid place-items-center text-[12px] text-[var(--fg-subtle)]">Önizleme yok</span>
          ) : (
            <span aria-hidden="true" className="absolute inset-0 animate-pulse bg-[var(--bg-sunken,var(--bg))]" />
          )}
          <KarartmaKatmani sayfa={sayfa} sayfaNo={sayfaNo} alanlar={karartmaAlanlari} aktif={cizimKipi === "karart" && !mesgul} onEkle={onKarartmaEkle} />
          <NotKatmani sayfa={sayfa} sayfaNo={sayfaNo} aktif={cizimKipi === "not"} mesgul={mesgul} onEkle={onNotEkle} />
        </div>
      </div>
    </div>
  );
}
