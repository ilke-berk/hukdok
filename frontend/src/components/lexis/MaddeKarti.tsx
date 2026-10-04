import { ArrowDown, ArrowUp, Quote, Trash2 } from "lucide-react";
import type { BolumKodu, LexisUyari, Madde, MaddeTuru } from "@/types/lexis";
import { OtoMetinAlani, Rozet, SimgeDugmesi } from "./ortak";
import { BAGLANTI_SINIFI, maddeKimligi, maddeRozetleri } from "./yardimcilar";

type MaddeKartiProps = {
  /** 1'den başlayan sıra — uyarılar bu numarayla gelir. */
  sira: number;
  madde: Madde;
  /** Bu maddeye ait uyarılar (son denetimden). */
  uyarilar: LexisUyari[];
  /** Son denetimden sonra düzenlendi: eski sonuç gösterilmez. */
  degisti: boolean;
  /** Dayanağı sağ panelde gösterilen madde. */
  secili: boolean;
  /** Uyarıdan gelindi: kısa süre vurgulanır. */
  vurgulu?: boolean;
  /** Dayanak bölümü seçenekleri (iskeletin özet bölümleri). */
  dayanakBolumleri: { kod: BolumKodu; baslik: string }[];
  ilk: boolean;
  son: boolean;
  onSec: () => void;
  onDegistir: (yama: Partial<Madde>) => void;
  onSil: () => void;
  onTasi: (yon: -1 | 1) => void;
  onBlur?: () => void;
  kilitli?: boolean;
};

/**
 * Değerlendirmenin bir maddesi (K13): `metin` rapora girer; dayanak (bölüm + dosyadan AYNEN alıntı) rapora
 * girmez, denetim içindir. Rozet son denetimin sonucudur: doğrulandı · dayanaksız · alıntı dosyada yok ·
 * emsalden taşınma · belge yokluğu iddiası. KALIP madde (son muallak cümlesi) dayanak istemez.
 */
export function MaddeKarti({
  sira,
  madde,
  uyarilar,
  degisti,
  secili,
  vurgulu = false,
  dayanakBolumleri,
  ilk,
  son,
  onSec,
  onDegistir,
  onSil,
  onTasi,
  onBlur,
  kilitli = false,
}: MaddeKartiProps) {
  const rozetler = maddeRozetleri(madde, uyarilar, degisti);
  const kalip = madde.tur === "KALIP";
  return (
    <article
      id={maddeKimligi(sira)}
      aria-label={`Madde ${sira}`}
      data-testid="lexis-madde"
      data-secili={secili ? "1" : "0"}
      className={`group border transition-colors ${
        vurgulu ? "border-[var(--brand)] bg-[var(--brand-soft)]" : secili ? "border-[var(--brand)] bg-[var(--bg)]" : "border-[var(--border)] bg-[var(--bg)]"
      }`}
    >
      <header className="flex items-center gap-2 pl-3 pr-1.5 pt-1.5">
        <span className="font-mono text-[11px] font-semibold tabular-nums text-[var(--fg-subtle)]">{String(sira).padStart(2, "0")}</span>
        <div className="flex flex-wrap gap-1 min-w-0" data-testid="lexis-madde-rozetleri">
          {rozetler.map((r, i) => (
            <Rozet key={`${r.kod}-${i}`} ton={r.ton}>
              {r.ad}
            </Rozet>
          ))}
        </div>
        <div className="ml-auto flex items-center opacity-60 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
          <select
            aria-label={`Madde ${sira} türü`}
            value={madde.tur}
            disabled={kilitli}
            onChange={(e) => onDegistir({ tur: e.target.value as MaddeTuru })}
            onBlur={onBlur}
            className="h-7 px-1 bg-transparent border border-transparent hover:border-[var(--border)] rounded-[3px] font-mono text-[10px] tracking-[0.08em] uppercase text-[var(--fg-subtle)] focus:border-[var(--brand)] focus:outline-none"
          >
            <option value="TESPIT">Tespit</option>
            <option value="KALIP">Kalıp</option>
          </select>
          <SimgeDugmesi etiket={`Madde ${sira}: yukarı taşı`} onClick={() => onTasi(-1)} disabled={kilitli || ilk}>
            <ArrowUp className="w-3.5 h-3.5" />
          </SimgeDugmesi>
          <SimgeDugmesi etiket={`Madde ${sira}: aşağı taşı`} onClick={() => onTasi(1)} disabled={kilitli || son}>
            <ArrowDown className="w-3.5 h-3.5" />
          </SimgeDugmesi>
          <SimgeDugmesi etiket={`Madde ${sira}: sil`} onClick={onSil} disabled={kilitli}>
            <Trash2 className="w-3.5 h-3.5" />
          </SimgeDugmesi>
        </div>
      </header>

      <div className="px-3 pb-1">
        <OtoMetinAlani
          value={madde.metin}
          disabled={kilitli}
          aria-label={`Madde ${sira} metni`}
          placeholder="Madde metni…"
          onChange={(e) => onDegistir({ metin: e.target.value })}
          onBlur={onBlur}
        />
      </div>

      {kalip ? (
        <p className="px-3 pb-2.5 text-[11.5px] text-[var(--fg-subtle)]">Kalıp madde dayanak istemez; muallak tutarı sağdaki karttan rapora yazılır.</p>
      ) : (
        <div className="mx-3 mb-2.5 pl-2.5 border-l-2 border-[var(--border-strong)] grid gap-1">
          <div className="flex items-center gap-2">
            <Quote className="w-3 h-3 shrink-0 text-[var(--fg-subtle)]" aria-hidden="true" />
            <span className="text-[11px] text-[var(--fg-subtle)]">Dayanak</span>
            <select
              aria-label={`Madde ${sira} dayanak bölümü`}
              value={madde.dayanak_bolum ?? ""}
              disabled={kilitli}
              onChange={(e) => onDegistir({ dayanak_bolum: (e.target.value || null) as BolumKodu | null })}
              onBlur={onBlur}
              className="h-6 px-1 bg-transparent border border-[var(--border)] rounded-[3px] text-[11.5px] text-[var(--fg-muted)] focus:border-[var(--brand)] focus:outline-none"
            >
              <option value="">bölüm seçilmedi</option>
              {dayanakBolumleri.map((b) => (
                <option key={b.kod} value={b.kod}>
                  {b.baslik}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onSec}
              aria-pressed={secili}
              className={`ml-auto text-[11.5px] ${BAGLANTI_SINIFI}`}
            >
              Kaynakta göster
            </button>
          </div>
          <OtoMetinAlani
            value={madde.dayanak_alinti ?? ""}
            disabled={kilitli}
            aria-label={`Madde ${sira} dayanak alıntısı`}
            placeholder="Dosyadan aynen alınmış kısa alıntı (rapora girmez)…"
            className="!text-[12.5px] !leading-[1.55] italic text-[var(--fg-muted)]"
            onChange={(e) => onDegistir({ dayanak_alinti: e.target.value || null })}
            onBlur={onBlur}
          />
        </div>
      )}

      {!degisti && uyarilar.length > 0 && (
        <ul className="px-3 pb-2.5 grid gap-0.5">
          {uyarilar.map((u) => (
            <li key={u.id} className={`text-[12px] leading-[1.45] ${u.seviye === "HATA" ? "text-tone-danger" : "text-tone-caution"}`}>
              {u.metin}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
