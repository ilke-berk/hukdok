import { BookOpen, Plus, X } from "lucide-react";
import type { Emsal } from "@/types/lexis";
import { CardListSkeleton } from "@/components/skeletons/Skeletons";
import { BolgeBasligi, BosDurum, SimgeDugmesi } from "./ortak";
import { muallakOzeti, raporKunyesi } from "./yardimcilar";

type EmsalListesiProps = {
  emsaller: Emsal[];
  yukleniyor: boolean;
  hata: string | null;
  onOku: (emsal: Emsal) => void;
  onCikar: (sha256: string) => void;
  onEkle: () => void;
  kilitli?: boolean;
};

/**
 * Taslak yazılırken bakılacak eski raporlar (K3: hangi raporlara bakıldığı gösterilir). Her satır puanı ve
 * "neden bu rapor" gerekçesini taşır; kullanıcı raporu okuyabilir, çıkarabilir ya da kütüphaneden ekleyebilir.
 */
export function EmsalListesi({ emsaller, yukleniyor, hata, onOku, onCikar, onEkle, kilitli = false }: EmsalListesiProps) {
  return (
    <section aria-label="Emsal raporlar" data-testid="lexis-emsaller" className="grid gap-2">
      <BolgeBasligi
        sag={
          <SimgeDugmesi etiket="Kütüphaneden emsal ekle" onClick={onEkle} disabled={kilitli}>
            <Plus className="w-3.5 h-3.5" />
          </SimgeDugmesi>
        }
      >
        Emsal raporlar
      </BolgeBasligi>
      {hata && (
        <p role="alert" className="text-[12.5px] text-tone-danger">
          {hata}
        </p>
      )}
      {yukleniyor && <CardListSkeleton count={3} itemClassName="h-[68px]" label="Emsaller aranıyor…" />}
      {!yukleniyor && !hata && emsaller.length === 0 && <BosDurum>Emsal seçilmedi. Taslak yalnız dosyanın belgelerine dayanır.</BosDurum>}
      {!yukleniyor && (
        <ul className="grid gap-1.5">
          {emsaller.map((e) => {
            const { okuma } = e.kayit;
            const muallak = muallakOzeti(okuma);
            return (
              <li key={okuma.sha256} className="flex items-start gap-2.5 border border-[var(--border)] bg-[var(--bg-elevated)] pl-3 pr-1.5 py-2 min-w-0">
                <div className="shrink-0 w-9 text-right" title="Benzerlik puanı (tavan 20)">
                  <span className="font-mono text-[15px] font-semibold tabular-nums text-[var(--fg)]">
                    {e.puan.toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] font-medium text-[var(--fg)]">{raporKunyesi(okuma)}</div>
                  <div className="text-[12px] leading-[1.45] text-[var(--fg-muted)]">{e.gerekce || "ortak özellik yok"}</div>
                  {muallak && <div className="text-[11.5px] text-[var(--fg-subtle)]">Muallak: {muallak}</div>}
                </div>
                <div className="shrink-0 flex flex-col">
                  <SimgeDugmesi etiket={`Emsali oku: ${okuma.rapor_no ?? okuma.dosya}`} onClick={() => onOku(e)}>
                    <BookOpen className="w-3.5 h-3.5" />
                  </SimgeDugmesi>
                  <SimgeDugmesi etiket={`Emsali çıkar: ${okuma.rapor_no ?? okuma.dosya}`} onClick={() => onCikar(okuma.sha256)} disabled={kilitli}>
                    <X className="w-3.5 h-3.5" />
                  </SimgeDugmesi>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
