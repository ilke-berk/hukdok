import { useCallback, useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { HukukbotMarkdown } from "./HukukbotMarkdown";
import { KaynakListesi } from "./KaynakListesi";
import { atiflariNumarala, kaynakNumarasi } from "./atiflar";
import type { EkranMesaji } from "./yardimcilar";

type MesajBalonuProps = {
  mesaj: EkranMesaji;
  onIndir: (kaynak: HukukbotKaynak) => void;
  inen?: string | null;
};

/**
 * Tek mesaj (G205): kullanıcı sağda açık zeminli balonda düz metin (markdown DEĞİL — yazdığı gibi); model
 * balonsuz, okuma sütununda düz metin gibi akar (markdown + kaynaklar). Akış sürerken parça parça büyür; ilk
 * parça gelene dek "yazıyor" göstergesi. Metin içi "(Kaynak: …pdf)" atıfları numaralı rozete çevrilir (28.09,
 * `atiflar.ts`); rozete tıklayınca aynı numaralı kaynak kartına kaydırılır ve kart kısa süre vurgulanır.
 */
export function MesajBalonu({ mesaj, onIndir, inen }: MesajBalonuProps) {
  if (mesaj.role === "user") return <KullaniciMesaji icerik={mesaj.content} />;
  return <ModelMesaji mesaj={mesaj} onIndir={onIndir} inen={inen} />;
}

function KullaniciMesaji({ icerik }: { icerik: string }) {
  return (
    <div className="flex justify-end" data-testid="hukukbot-mesaj-kullanici">
      <div className="max-w-[85%] px-4 py-2.5 rounded-[16px] rounded-br-[4px] bg-[var(--brand-soft)] border border-[var(--border)] text-[var(--fg)] text-[14px] leading-[1.55] whitespace-pre-wrap break-words">
        {icerik}
      </div>
    </div>
  );
}

function ModelMesaji({ mesaj, onIndir, inen }: MesajBalonuProps) {
  const onek = useId();
  const [vurgulu, setVurgulu] = useState<number | null>(null);
  const zamanlayici = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { metin, adlar } = useMemo(() => atiflariNumarala(mesaj.content), [mesaj.content]);
  const kaynaklar = useMemo(() => mesaj.sources ?? [], [mesaj.sources]);

  const atifEtiketi = useCallback(
    (n: number) => {
      const k = kaynaklar.find((x) => kaynakNumarasi(x, adlar) === n);
      return k ? k.file_display_name || k.filename : adlar[n - 1];
    },
    [kaynaklar, adlar],
  );
  const onAtif = useCallback(
    (n: number) => {
      document.getElementById(`${onek}-kaynak-${n}`)?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      setVurgulu(n);
      if (zamanlayici.current) clearTimeout(zamanlayici.current);
      zamanlayici.current = setTimeout(() => setVurgulu(null), 1600);
    },
    [onek],
  );

  const bos = mesaj.content === "";
  return (
    <div className="flex justify-start" data-testid="hukukbot-mesaj-model">
      <div className="w-full min-w-0 py-1">
        {bos && mesaj.akiyor && (
          <div
            role="status"
            data-testid="hukukbot-durum"
            className="flex items-start gap-2 text-[12.5px] text-[var(--fg-muted)] min-w-0"
          >
            <Loader2 className="w-4 h-4 mt-0.5 shrink-0 animate-spin" aria-hidden="true" />
            <span className="break-words min-w-0">{mesaj.durum || "Hukukbot yazıyor..."}</span>
          </div>
        )}
        {!bos && (
          <div data-testid="hukukbot-yanit" aria-live={mesaj.akiyor ? "polite" : undefined}>
            <HukukbotMarkdown metin={metin} onAtif={onAtif} atifEtiketi={atifEtiketi} />
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
        {kaynaklar.length > 0 && (
          <KaynakListesi
            kaynaklar={kaynaklar}
            onIndir={onIndir}
            inen={inen}
            atifAdlari={adlar}
            idOneki={onek}
            vurgulu={vurgulu}
          />
        )}
      </div>
    </div>
  );
}
