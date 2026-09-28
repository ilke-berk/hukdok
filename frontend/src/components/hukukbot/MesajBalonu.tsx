import { AlertTriangle, Loader2 } from "lucide-react";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { HukukbotMarkdown } from "./HukukbotMarkdown";
import { KaynakListesi } from "./KaynakListesi";
import type { EkranMesaji } from "./yardimcilar";

type MesajBalonuProps = {
  mesaj: EkranMesaji;
  onIndir: (kaynak: HukukbotKaynak) => void;
  inen?: string | null;
};

/**
 * Tek mesaj (G205): kullanıcı sağda açık zeminli balonda düz metin (markdown DEĞİL — yazdığı gibi); model
 * balonsuz, okuma sütununda düz metin gibi akar (markdown + kaynaklar). Akış sürerken parça parça büyür; ilk
 * parça gelene dek "yazıyor" göstergesi.
 */
export function MesajBalonu({ mesaj, onIndir, inen }: MesajBalonuProps) {
  if (mesaj.role === "user") {
    return (
      <div className="flex justify-end" data-testid="hukukbot-mesaj-kullanici">
        <div className="max-w-[85%] px-4 py-2.5 rounded-[16px] rounded-br-[4px] bg-[var(--brand-soft)] border border-[var(--border)] text-[var(--fg)] text-[14px] leading-[1.55] whitespace-pre-wrap break-words">
          {mesaj.content}
        </div>
      </div>
    );
  }

  const bos = mesaj.content === "";
  return (
    <div className="flex justify-start" data-testid="hukukbot-mesaj-model">
      <div className="w-full min-w-0 py-1">
        {bos && mesaj.akiyor && (
          <div role="status" className="flex items-center gap-2 text-[12.5px] text-[var(--fg-muted)]">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            Hukukbot yazıyor...
          </div>
        )}
        {!bos && (
          <div data-testid="hukukbot-yanit" aria-live={mesaj.akiyor ? "polite" : undefined}>
            <HukukbotMarkdown metin={mesaj.content} />
            {mesaj.akiyor && (
              <span
                aria-hidden="true"
                className="inline-block w-1.5 h-3.5 ml-0.5 align-middle bg-[var(--brand)] animate-pulse"
              />
            )}
          </div>
        )}
        {mesaj.durduruldu && (
          <p className="mt-2 font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
            Yanıt durduruldu
          </p>
        )}
        {mesaj.hata && (
          <div
            role="alert"
            data-testid="hukukbot-hata"
            className="mt-2 flex items-start gap-2 border-l-2 border-tone-danger pl-3 py-1 text-[12.5px] text-tone-danger"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{mesaj.hata}</span>
          </div>
        )}
        {mesaj.sources && mesaj.sources.length > 0 && (
          <KaynakListesi kaynaklar={mesaj.sources} onIndir={onIndir} inen={inen} />
        )}
      </div>
    </div>
  );
}
