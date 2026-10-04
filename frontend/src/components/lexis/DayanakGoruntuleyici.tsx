import type { BolumKodu, LexisTaslak } from "@/types/lexis";
import { BolgeBasligi, BosDurum } from "./ortak";
import { dayanakBul, vurguParcalari } from "./yardimcilar";

type DayanakGoruntuleyiciProps = {
  taslak: LexisTaslak | null;
  /** Seçili madde (1'den başlar). */
  sira: number | null;
  bolumAdlari: Partial<Record<BolumKodu, string>>;
};

/**
 * Seçili maddenin dayanak alıntısını kaynak paragrafta vurgular: insan alıntının maddeyi gerçekten
 * DESTEKLEYİP desteklemediğine buradan bakar (denetim yalnız alıntının dosyada geçtiğini doğrular).
 */
export function DayanakGoruntuleyici({ taslak, sira, bolumAdlari }: DayanakGoruntuleyiciProps) {
  const madde = taslak?.degerlendirme && sira !== null ? taslak.degerlendirme.maddeler[sira - 1] : undefined;
  const konum = taslak && madde ? dayanakBul(taslak, madde) : null;

  return (
    <section aria-label="Dayanak" data-testid="lexis-dayanak" className="grid gap-2">
      <BolgeBasligi sag={madde ? <span className="font-mono text-[10.5px] text-[var(--fg-subtle)]">madde {sira}</span> : undefined}>Dayanak</BolgeBasligi>
      {!madde && <BosDurum>Bir maddede "Kaynakta göster"e basın; alıntı dosyadaki yerinde vurgulanır.</BosDurum>}
      {madde && madde.tur === "KALIP" && <BosDurum>Kalıp madde dayanak taşımaz.</BosDurum>}
      {madde && madde.tur !== "KALIP" && !madde.dayanak_alinti?.trim() && <BosDurum>Bu maddenin dayanak alıntısı yok.</BosDurum>}
      {madde && madde.tur !== "KALIP" && madde.dayanak_alinti?.trim() && !konum && (
        <p className="text-[12.5px] leading-[1.5] text-tone-danger">Alıntı dosyanın bölümlerinde bulunamadı.</p>
      )}
      {konum && (
        <figure className="border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2.5">
          <figcaption className="mb-1 text-[11px] text-[var(--fg-subtle)]">
            {bolumAdlari[konum.bolum] ?? konum.bolum} · paragraf {konum.paragraf + 1}
          </figcaption>
          <p className="text-[13px] leading-[1.65] text-[var(--fg)]">
            {vurguParcalari(konum.metin, konum.araliklar).map((p, i) =>
              p.vurgulu ? (
                <mark key={i} className="bg-tone-caution/25 text-[var(--fg)] px-0.5 [box-decoration-break:clone]">
                  {p.metin}
                </mark>
              ) : (
                <span key={i}>{p.metin}</span>
              ),
            )}
          </p>
        </figure>
      )}
    </section>
  );
}
