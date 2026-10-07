import { FileText, Plus, Trash2 } from "lucide-react";
import type { LexisBelge, OzetParagraf, RafKarari } from "@/types/lexis";
import { BosDurum, OtoMetinAlani, SimgeDugmesi } from "./ortak";
import { BAGLANTI_SINIFI, kararKunyesi } from "./yardimcilar";

type OzetBolumProps = {
  baslik: string;
  paragraflar: OzetParagraf[];
  /** Kaynak çipindeki belge adını çözmek için. */
  belgeler: LexisBelge[];
  /** Kaynak çipindeki karar künyesini çözmek için (dava kartının kararları). */
  kararlar?: RafKarari[];
  onKararOku?: (id: number) => void;
  onDegistir: (sira: number, metin: string) => void;
  onEkle: () => void;
  onSil: (sira: number) => void;
  onBlur?: () => void;
  kilitli?: boolean;
};

/**
 * Özet bölüm (iddia, beyan, yargı süreci, uzman görüşü, poliçe, ek inceleme): modelin dosyanın belgelerinden
 * yazdığı paragraflar. Her paragraf hangi belgeden yazıldığını taşır; insanın eklediği paragrafta kaynak yoktur.
 */
export function OzetBolum({ baslik, paragraflar, belgeler, kararlar = [], onKararOku, onDegistir, onEkle, onSil, onBlur, kilitli = false }: OzetBolumProps) {
  return (
    <div className="grid gap-2">
      {paragraflar.length === 0 && <BosDurum>Bu bölüm boş: dayanacağı belge dava kartında yok ya da seçilmedi.</BosDurum>}
      {paragraflar.map((p, i) => {
        const kaynak = p.kaynak_belge_id === null ? null : belgeler.find((b) => b.id === p.kaynak_belge_id);
        const kararId = p.kaynak_karar_id ?? null;
        const kaynakKarar = kararId === null ? undefined : kararlar.find((k) => k.id === kararId);
        return (
          <div key={i} className="group grid grid-cols-[minmax(0,1fr)_auto] items-start gap-1">
            <div className="min-w-0">
              <OtoMetinAlani
                value={p.metin}
                disabled={kilitli}
                aria-label={`${baslik}, paragraf ${i + 1}`}
                onChange={(e) => onDegistir(i, e.target.value)}
                onBlur={onBlur}
              />
              <span className="inline-flex items-center gap-1 mt-0.5 text-[11px] text-[var(--fg-subtle)]">
                <FileText className="w-3 h-3 shrink-0" aria-hidden="true" />
                {kararId != null ? (
                  // Kararlardan yazılan paragraf: kaynağı karardır; tıklanınca karar okuyucuda açılır.
                  <>
                    Kaynak karar:{" "}
                    {onKararOku ? (
                      <button type="button" onClick={() => onKararOku(kararId)} className={BAGLANTI_SINIFI}>
                        {kaynakKarar ? kararKunyesi(kaynakKarar) : `#${kararId}`}
                      </button>
                    ) : kaynakKarar ? (
                      kararKunyesi(kaynakKarar)
                    ) : (
                      `#${kararId}`
                    )}
                  </>
                ) : kaynak ? (
                  `Kaynak: ${kaynak.ad}`
                ) : p.kaynak_belge_id === null ? (
                  "Elle eklendi"
                ) : (
                  "Kaynak belge kartta yok"
                )}
              </span>
            </div>
            <div className="opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
              <SimgeDugmesi etiket={`Paragrafı sil: ${baslik} ${i + 1}`} onClick={() => onSil(i)} disabled={kilitli}>
                <Trash2 className="w-3.5 h-3.5" />
              </SimgeDugmesi>
            </div>
          </div>
        );
      })}
      <button
        type="button"
        onClick={onEkle}
        disabled={kilitli}
        className="justify-self-start inline-flex items-center gap-1 text-[12px] text-[var(--fg-subtle)] hover:text-[var(--brand)] disabled:opacity-50"
      >
        <Plus className="w-3 h-3" aria-hidden="true" />
        Paragraf ekle
      </button>
    </div>
  );
}
