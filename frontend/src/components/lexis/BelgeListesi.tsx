import { Link } from "react-router";
import { AlertTriangle } from "lucide-react";
import { tarihYaz } from "@/lib/lexisMetin";
import { BEKLENEN_BELGELER, BELGE_TURU_ADLARI, type LexisBelge } from "@/types/lexis";
import { BolgeBasligi, BosDurum } from "./ortak";
import { BAGLANTI_SINIFI } from "./yardimcilar";

type BelgeListesiProps = {
  belgeler: LexisBelge[];
  /** Rapora girecek (modele gönderilecek) belgeler. */
  secili: ReadonlySet<number>;
  onSec: (id: number, secili: boolean) => void;
  kilitli?: boolean;
};

/**
 * Dava kartındaki belgeler; işaretli olanlar taslağa girer. Raporun beklediği türlerden (dilekçe, hekim beyanı,
 * bilirkişi/ATK raporu, poliçe) kartta olmayan uyarıyla gösterilir — belge HukuDok'a yüklenir, araç kendi
 * yükleme yolunu açmaz (`lexis-rapor/PLAN.md` K10).
 */
export function BelgeListesi({ belgeler, secili, onSec, kilitli = false }: BelgeListesiProps) {
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
          <li key={b.id}>
            <label className="flex items-start gap-2.5 px-2 py-1.5 -mx-2 rounded-[3px] hover:bg-[var(--bg-sunken)] cursor-pointer">
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
            Belgeyi HukuDok'a yükle
          </Link>
        </div>
      )}
    </section>
  );
}
