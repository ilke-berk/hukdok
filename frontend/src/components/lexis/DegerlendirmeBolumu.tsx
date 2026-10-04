import { Plus } from "lucide-react";
import type { BolumKodu, DegerlendirmeTaslagi, LexisUyari, Madde } from "@/types/lexis";
import { MaddeKarti } from "./MaddeKarti";
import { OtoMetinAlani } from "./ortak";

type DegerlendirmeBolumuProps = {
  degerlendirme: DegerlendirmeTaslagi;
  /** `maddeler` ile aynı sırada kararlı kimlikler (React anahtarı, "değişti" izi). */
  maddeKimlikleri: string[];
  degisenMaddeler: ReadonlySet<string>;
  /** Değerlendirme bölümünün uyarıları. */
  uyarilar: LexisUyari[];
  seciliMadde: number | null;
  vurguluMadde: number | null;
  dayanakBolumleri: { kod: BolumKodu; baslik: string }[];
  onGiris: (metin: string) => void;
  onSulh: (metin: string) => void;
  onMadde: (sira: number, yama: Partial<Madde>) => void;
  onMaddeEkle: () => void;
  onMaddeSil: (sira: number) => void;
  onMaddeTasi: (sira: number, yon: -1 | 1) => void;
  onMaddeSec: (sira: number) => void;
  onBlur?: () => void;
  kilitli?: boolean;
  /** "Sulhe Uygunluk Durumu" satırı yalnız ANADOLU iskeletinde vardır (çekirdekte `yazici.KALIPLAR`). */
  sulhSatiri?: boolean;
};

/**
 * Değerlendirme (muhakeme) bölümü: giriş cümlesi, dayanaklı maddeler, sulh satırı. Sıra numaraları 1'den başlar
 * ve uyarılarla aynıdır. Yeni madde sondaki muallak (KALIP) maddesinin önüne eklenir.
 */
export function DegerlendirmeBolumu({
  degerlendirme,
  maddeKimlikleri,
  degisenMaddeler,
  uyarilar,
  seciliMadde,
  vurguluMadde,
  dayanakBolumleri,
  onGiris,
  onSulh,
  onMadde,
  onMaddeEkle,
  onMaddeSil,
  onMaddeTasi,
  onMaddeSec,
  onBlur,
  kilitli = false,
  sulhSatiri = true,
}: DegerlendirmeBolumuProps) {
  const sayi = degerlendirme.maddeler.length;
  return (
    <div className="grid gap-2.5">
      <OtoMetinAlani
        value={degerlendirme.giris}
        disabled={kilitli}
        aria-label="Giriş cümlesi"
        placeholder="Tarafımıza iletilen …"
        onChange={(e) => onGiris(e.target.value)}
        onBlur={onBlur}
      />
      <div className="grid gap-2">
        {degerlendirme.maddeler.map((m, i) => {
          const sira = i + 1;
          const kimlik = maddeKimlikleri[i] ?? String(i);
          return (
            <MaddeKarti
              key={kimlik}
              sira={sira}
              madde={m}
              uyarilar={uyarilar.filter((u) => u.madde === sira)}
              degisti={degisenMaddeler.has(kimlik)}
              secili={seciliMadde === sira}
              vurgulu={vurguluMadde === sira}
              dayanakBolumleri={dayanakBolumleri}
              ilk={i === 0}
              son={i === sayi - 1}
              onSec={() => onMaddeSec(sira)}
              onDegistir={(yama) => onMadde(sira, yama)}
              onSil={() => onMaddeSil(sira)}
              onTasi={(yon) => onMaddeTasi(sira, yon)}
              onBlur={onBlur}
              kilitli={kilitli}
            />
          );
        })}
      </div>
      <button
        type="button"
        onClick={onMaddeEkle}
        disabled={kilitli}
        className="justify-self-start inline-flex items-center gap-1 text-[12px] text-[var(--fg-subtle)] hover:text-[var(--brand)] disabled:opacity-50"
      >
        <Plus className="w-3 h-3" aria-hidden="true" />
        Madde ekle
      </button>
      {sulhSatiri && (
        <label className="grid sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)] items-center gap-x-3 gap-y-0.5 border border-[var(--border)] bg-[var(--bg)] px-3 py-1">
          <span className="text-[12.5px] text-[var(--fg-muted)]">Sulhe Uygunluk Durumu</span>
          <input
            type="text"
            value={degerlendirme.sulh_uygunluk}
            disabled={kilitli}
            onChange={(e) => onSulh(e.target.value)}
            onBlur={onBlur}
            className="w-full h-7 px-2 -mx-2 bg-transparent border border-transparent rounded-[3px] text-[13px] text-[var(--fg)] hover:border-[var(--border)] focus:border-[var(--brand)] focus:bg-[var(--bg-elevated)] focus:outline-none"
          />
        </label>
      )}
    </div>
  );
}
