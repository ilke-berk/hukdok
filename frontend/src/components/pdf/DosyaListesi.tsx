// Belge tezgâhı sol bölgesi (G270): yüklenen + çıktı dosyaları. Tıklama = seçim (sağ panel ve indirme ona bakar);
// onay kutusu = birleştirme girdisi (sıra = liste sırası, ↑/↓ listeyi taşır — sürükle-sırala G271); "Kaldır" yalnız
// istemci listesinden düşürür (sunucu TTL'i siler).
import { ArrowDown, ArrowUp, FileText, X } from "lucide-react";
import type { Dosya } from "@/types/pdfAraclari";
import type { TasimaYonu } from "./usePdfTezgah";

type Props = {
  dosyalar: Dosya[];
  seciliId: string | null;
  isaretliler: string[];
  onSec: (id: string) => void;
  onIsaretle: (id: string, isaretli: boolean) => void;
  onKaldir: (id: string) => void;
  onTasi: (id: string, yon: TasimaYonu) => void;
};

// Dışa açılmaz (react-refresh/only-export-components: bileşen dosyası yalnız bileşen export eder).
function boyutMetni(bayt: number): string {
  if (bayt >= 1024 * 1024) return `${(bayt / 1024 / 1024).toFixed(1)} MB`;
  if (bayt >= 1024) return `${Math.round(bayt / 1024)} KB`;
  return `${bayt} B`;
}

export function DosyaListesi({ dosyalar, seciliId, isaretliler, onSec, onIsaretle, onKaldir, onTasi }: Props) {
  if (dosyalar.length === 0) {
    return (
      <p data-testid="dosya-listesi-bos" className="text-[12px] text-[var(--fg-subtle)] px-1">
        Henüz dosya yok. Yükleyin ya da bir kartın belgesini alın.
      </p>
    );
  }
  return (
    <ul aria-label="Çalışma dosyaları" data-testid="dosya-listesi" className="flex flex-col gap-1">
      {dosyalar.map((d, i) => {
        const secili = d.id === seciliId;
        const isaretli = isaretliler.includes(d.id);
        return (
          <li
            key={d.id}
            data-dosya-id={d.id}
            aria-current={secili ? "true" : undefined}
            className={[
              "group flex items-center gap-2 rounded-[3px] border px-2 py-1.5 transition-colors",
              secili
                ? "border-[var(--brand)] bg-[var(--brand-soft)]"
                : "border-[var(--border)] bg-[var(--bg-elevated)] hover:border-[var(--border-strong)]",
            ].join(" ")}
          >
            <input
              type="checkbox"
              aria-label={`Birleştirmeye ekle: ${d.ad}`}
              checked={isaretli}
              onChange={(e) => onIsaretle(d.id, e.target.checked)}
              className="accent-[var(--brand)] shrink-0"
            />
            <button
              type="button"
              onClick={() => onSec(d.id)}
              className="flex items-center gap-2 min-w-0 flex-1 text-left"
              title={d.ad}
            >
              <FileText className={`w-4 h-4 shrink-0 ${secili ? "text-[var(--brand)]" : "text-[var(--fg-subtle)]"}`} strokeWidth={1.5} />
              <span className="min-w-0">
                <span className={`block truncate text-[13px] ${secili ? "font-semibold text-[var(--fg)]" : "text-[var(--fg)]"}`}>{d.ad}</span>
                <span className="block font-mono text-[10px] tracking-[0.08em] uppercase text-[var(--fg-subtle)]">
                  {d.sayfa} sayfa · {boyutMetni(d.boyut)}
                  {typeof d.kucultme === "number" && d.kucultme > 0 ? ` · %${Math.round(d.kucultme * 100)} küçüldü` : ""}
                </span>
              </span>
            </button>
            <span className="flex items-center gap-0.5 shrink-0 opacity-70 group-hover:opacity-100">
              <button
                type="button"
                aria-label={`Yukarı taşı: ${d.ad}`}
                disabled={i === 0}
                onClick={() => onTasi(d.id, "yukari")}
                className="w-6 h-6 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--fg)] disabled:opacity-30"
              >
                <ArrowUp className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                aria-label={`Aşağı taşı: ${d.ad}`}
                disabled={i === dosyalar.length - 1}
                onClick={() => onTasi(d.id, "asagi")}
                className="w-6 h-6 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--fg)] disabled:opacity-30"
              >
                <ArrowDown className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                aria-label={`Listeden kaldır: ${d.ad}`}
                onClick={() => onKaldir(d.id)}
                className="w-6 h-6 grid place-items-center text-[var(--fg-subtle)] hover:text-[rgb(var(--tone-danger-rgb))]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
