import type { BolumKodu, BolumTanimi } from "@/types/lexis";

/** bos: henüz yazılmadı · yaziliyor: akış sürüyor · yazildi: modelden/koddan geldi · duzenlendi: insan değiştirdi */
export type BolumDurumu = "bos" | "yaziliyor" | "yazildi" | "duzenlendi";

type BolumGezginiProps = {
  bolumler: BolumTanimi[];
  durumlar: Partial<Record<BolumKodu, BolumDurumu>>;
  uyariSayilari: Partial<Record<BolumKodu, number>>;
  onGit: (kod: BolumKodu) => void;
};

const DURUM_NOKTASI: Record<BolumDurumu, string> = {
  bos: "bg-[var(--border-strong)]",
  yaziliyor: "bg-[var(--brand)] animate-pulse",
  yazildi: "bg-tone-ok",
  duzenlendi: "bg-tone-info",
};

const DURUM_ADI: Record<BolumDurumu, string> = {
  bos: "boş",
  yaziliyor: "yazılıyor",
  yazildi: "yazıldı",
  duzenlendi: "düzenlendi",
};

/** Taslağın içindekileri: iskeletin bölümleri sırasıyla, her birinde durum noktası ve uyarı sayısı. */
export function BolumGezgini({ bolumler, durumlar, uyariSayilari, onGit }: BolumGezginiProps) {
  return (
    <nav aria-label="Taslak bölümleri" data-testid="lexis-bolum-gezgini" className="flex gap-1 overflow-x-auto">
      {bolumler.map((b, i) => {
        const durum = durumlar[b.kod] ?? "bos";
        const uyari = uyariSayilari[b.kod] ?? 0;
        return (
          <button
            key={b.kod}
            type="button"
            onClick={() => onGit(b.kod)}
            title={`${b.baslik} — ${DURUM_ADI[durum]}${uyari ? `, ${uyari} uyarı` : ""}`}
            className="shrink-0 inline-flex items-center gap-1.5 h-7 px-2 border border-[var(--border)] bg-[var(--bg)] text-[12px] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--brand)] transition-colors"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${DURUM_NOKTASI[durum]}`} aria-hidden="true" />
            <span className="font-mono text-[10px] tabular-nums text-[var(--fg-subtle)]">{i + 1}</span>
            <span className="whitespace-nowrap">{b.baslik}</span>
            {uyari > 0 && (
              <span className="font-mono text-[10px] font-semibold tabular-nums text-tone-caution" aria-label={`${uyari} uyarı`}>
                !{uyari}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
