import { FileText, Loader2 } from "lucide-react";
import type { HukukbotKaynak } from "@/types/hukukbot";

type KaynakListesiProps = {
  kaynaklar: HukukbotKaynak[];
  /** PDF'i açar — sayfa `hukukbotApi.indir(filename)` çağırır (yetkili indirme, düz link ÇALIŞMAZ). */
  onIndir: (kaynak: HukukbotKaynak) => void;
  /** Şu an inmekte olan dosya adı (düğme kilitlenir). */
  inen?: string | null;
};

/**
 * Yanıtın kaynakları (G205): `/ask` akışının `sources` olayı. Her kaynak adı + önizleme metni;
 * "PDF'i aç" düğmesi `download_url`'i KULLANMAZ (hukbot'a göreli, Authorization ister) — dosya adını
 * sayfaya iletir, sayfa G204 `indir()` ile açar.
 */
export function KaynakListesi({ kaynaklar, onIndir, inen }: KaynakListesiProps) {
  if (kaynaklar.length === 0) return null;
  return (
    <section
      aria-label="Kaynaklar"
      data-testid="hukukbot-kaynaklar"
      className="mt-3 border-t border-[var(--border)] pt-3 grid gap-2"
    >
      <h4 className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
        Kaynaklar · {kaynaklar.length}
      </h4>
      <ul className="grid gap-2">
        {kaynaklar.map((k, i) => {
          const ad = k.file_display_name || k.filename;
          const iniyor = inen === k.filename;
          const pdf = /\.pdf$/i.test(k.filename);
          return (
            <li
              key={`${k.filename}-${i}`}
              className="flex items-start gap-2.5 p-2.5 bg-[var(--bg)] border border-[var(--border)] rounded-[3px] min-w-0"
            >
              <FileText className="w-4 h-4 mt-0.5 shrink-0 text-[var(--brand)]" aria-hidden="true" />
              <div className="flex-1 min-w-0 grid gap-1">
                <span className="text-[12.5px] font-medium text-[var(--fg)] break-words">{ad}</span>
                {k.text_preview && (
                  <p className="text-[11.5px] leading-[1.5] text-[var(--fg-muted)] line-clamp-3 break-words">
                    {k.text_preview}
                  </p>
                )}
              </div>
              {k.filename && (
                <button
                  type="button"
                  disabled={iniyor}
                  onClick={() => onIndir(k)}
                  aria-label={`${pdf ? "PDF'i aç" : "Dosyayı indir"}: ${ad}`}
                  className="shrink-0 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[3px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[11.5px] text-[var(--fg)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors disabled:opacity-50 disabled:cursor-wait"
                >
                  {iniyor && <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />}
                  {pdf ? "PDF'i aç" : "İndir"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
