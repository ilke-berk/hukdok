import { useCallback, useMemo } from "react";
import { AlertTriangle, BookOpen, Loader2 } from "lucide-react";
import { HukukbotMarkdown } from "./HukukbotMarkdown";
import { alintiDogrulandi, atiflariNumarala, kaynakNumarasi, supheliKaynakSayisi } from "./atiflar";
import type { EkranMesaji } from "./yardimcilar";

type MesajBalonuProps = {
  mesaj: EkranMesaji;
  /** Kaynak panelini bu mesajın kaynaklarıyla aç; `n` verilirse o numaralı kaynak vurgulanır. */
  onKaynakAc?: (anahtar: string, n: number | null) => void;
  /** Sağdaki panel şu an bu mesajın kaynaklarını gösteriyor. */
  kaynakPanelinde?: boolean;
};

/**
 * Tek mesaj (G205): kullanıcı sağda açık zeminli balonda düz metin (markdown DEĞİL — yazdığı gibi); model
 * balonsuz, okuma sütununda düz metin gibi akar (markdown + kaynaklar). Akış sürerken parça parça büyür; ilk
 * parça gelene dek "yazıyor" göstergesi. Metin içi "(Kaynak: …pdf)" atıfları numaralı rozete çevrilir (28.09,
 * `atiflar.ts`). Kaynak kartları metnin altında DEĞİL, sayfanın sağındaki açılır-kapanır `KaynakPaneli`nde (28.09);
 * metnin altında yalnız "Kaynaklar · N" düğmesi kalır. Rozet ya da düğme paneli bu mesajın kaynaklarıyla açar.
 */
export function MesajBalonu({ mesaj, onKaynakAc, kaynakPanelinde = false }: MesajBalonuProps) {
  if (mesaj.role === "user") return <KullaniciMesaji icerik={mesaj.content} />;
  return <ModelMesaji mesaj={mesaj} onKaynakAc={onKaynakAc} kaynakPanelinde={kaynakPanelinde} />;
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

function ModelMesaji({ mesaj, onKaynakAc, kaynakPanelinde }: MesajBalonuProps) {
  const { metin, adlar, alintilar } = useMemo(() => atiflariNumarala(mesaj.content), [mesaj.content]);
  const kaynaklar = useMemo(() => mesaj.sources ?? [], [mesaj.sources]);

  const atifEtiketi = useCallback(
    (n: number) => {
      const k = kaynaklar.find((x) => kaynakNumarasi(x, adlar) === n);
      return k ? k.file_display_name || k.filename : adlar[n - 1];
    },
    [kaynaklar, adlar],
  );
  const onAtif = useCallback((n: number) => onKaynakAc?.(mesaj.anahtar, n), [onKaynakAc, mesaj.anahtar]);
  const alintiDurumu = useCallback(
    (i: number) => (alintilar[i] === undefined ? null : alintiDogrulandi(alintilar[i], kaynaklar)),
    [alintilar, kaynaklar],
  );
  const supheli = supheliKaynakSayisi(kaynaklar);

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
            <HukukbotMarkdown metin={metin} onAtif={onAtif} atifEtiketi={atifEtiketi} alintiDurumu={alintiDurumu} />
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
          <button
            type="button"
            data-testid="kaynaklari-goster"
            aria-pressed={kaynakPanelinde}
            onClick={() => onKaynakAc?.(mesaj.anahtar, null)}
            className={`mt-3 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full border text-[12px] transition-colors ${
              kaynakPanelinde
                ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand)]"
                : "border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--fg)]"
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />
            Kaynaklar · {kaynaklar.length}
            {supheli > 0 && (
              <span className="inline-flex items-center gap-1 text-tone-caution" title={`${supheli} kaynakta doğrulanamayan atıf/alıntı`}>
                <AlertTriangle className="w-3 h-3" aria-hidden="true" />
                {supheli}
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
