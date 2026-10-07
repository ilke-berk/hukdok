import { Link } from "react-router";
import { AlertTriangle, Scale } from "lucide-react";
import { tarihYaz } from "@/lib/lexisMetin";
import { BEKLENEN_BELGELER, BELGE_TURU_ADLARI, emsalBelgesiMi, type LexisBelge } from "@/types/lexis";
import { BolgeBasligi, BosDurum, SimgeDugmesi } from "./ortak";
import { BAGLANTI_SINIFI } from "./yardimcilar";

type BelgeListesiProps = {
  belgeler: LexisBelge[];
  /** Rapora girecek (modele gönderilecek) belgeler. */
  secili: ReadonlySet<number>;
  onSec: (id: number, secili: boolean) => void;
  /** "Bu belgeye emsal bul" satır düğmesi (yalnız pdf / docx / udf); verilmezse çizilmez. */
  onEmsalBul?: (belge: LexisBelge) => void;
  kilitli?: boolean;
};

/**
 * Dava kartındaki belgeler; işaretli olanlar taslağa girer. Raporun beklediği türlerden (dilekçe, hekim beyanı,
 * bilirkişi/ATK raporu, poliçe) kartta olmayan uyarıyla gösterilir — belge HUKDOK'a yüklenir, araç kendi
 * yükleme yolunu açmaz (`lexis-rapor/PLAN.md` K10). Satırdaki terazi düğmesi belgeyi emsal ajanına verir (K27).
 */
export function BelgeListesi({ belgeler, secili, onSec, onEmsalBul, kilitli = false }: BelgeListesiProps) {
  const eksikler = BEKLENEN_BELGELER.filter((tur) => !belgeler.some((b) => b.tur === tur));
  const seciliSayisi = belgeler.filter((b) => secili.has(b.id)).length;

  return (
    <section aria-label="Belgeler" data-testid="lexis-belgeler" className="grid gap-2">
      <BolgeBasligi sag={<span className="font-mono text-[10.5px] text-[var(--fg-subtle)] tabular-nums">{seciliSayisi}/{belgeler.length} seçili</span>}>
        Belgeler
      </BolgeBasligi>
      {belgeler.length === 0 && <BosDurum>Dava kartında belge yok.</BosDurum>}
      <ul className="grid gap-1">
        {belgeler.map((b) => (
          <li key={b.id} className="flex items-start gap-1 -mx-2">
            <label className="min-w-0 flex-1 flex items-start gap-2.5 px-2 py-1.5 rounded-[3px] hover:bg-[var(--bg-sunken)] cursor-pointer">
              <input
                type="checkbox"
                className="mt-[3px] accent-[var(--brand)]"
                checked={secili.has(b.id)}
                disabled={kilitli}
                onChange={(e) => onSec(b.id, e.target.checked)}
              />
              <span className="min-w-0">
                <span className="block text-[13px] text-[var(--fg)] leading-[1.4]">{b.ad}</span>
                <span className="block text-[11.5px] text-[var(--fg-subtle)]">
                  {[BELGE_TURU_ADLARI[b.tur], tarihYaz(b.tarih), b.sayfa !== null && `${b.sayfa} sayfa`].filter(Boolean).join(" · ")}
                </span>
                {b.ozet && <span className="block mt-0.5 text-[12px] text-[var(--fg-muted)] leading-[1.45]">{b.ozet}</span>}
              </span>
            </label>
            {onEmsalBul && emsalBelgesiMi(b.ad) && (
              <span className="shrink-0 pt-0.5">
                <SimgeDugmesi etiket={`Bu belgeye emsal bul: ${b.ad}`} onClick={() => onEmsalBul(b)} disabled={kilitli}>
                  <Scale className="w-3.5 h-3.5" />
                </SimgeDugmesi>
              </span>
            )}
          </li>
        ))}
      </ul>
      {eksikler.length > 0 && (
        <div role="note" data-testid="lexis-eksik-belgeler" className="border border-tone-caution/40 bg-tone-caution/10 px-2.5 py-2 text-[12px] leading-[1.5]">
          <div className="flex items-start gap-2 text-[var(--fg)]">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-tone-caution" aria-hidden="true" />
            <span>
              Kartta yok: <span className="font-medium">{eksikler.map((t) => BELGE_TURU_ADLARI[t]).join(", ")}</span>. İlgili bölüm boş kalır.
            </span>
          </div>
          <Link to="/upload" className={`inline-block mt-1 ml-[22px] ${BAGLANTI_SINIFI}`}>
            Belgeyi HUKDOK'a yükle
          </Link>
        </div>
      )}
    </section>
  );
}
