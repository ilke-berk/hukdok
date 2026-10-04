import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import type { BolumKodu, LexisUyari, UyariSeviyesi } from "@/types/lexis";
import { BolgeBasligi, BosDurum } from "./ortak";

type UyariListesiProps = {
  uyarilar: LexisUyari[];
  /** Bölüm kodu → görünen başlık (iskelete göre). */
  bolumAdlari: Partial<Record<BolumKodu, string>>;
  /** Taslak henüz yazılmadı: liste yerine açıklama. */
  taslakVar: boolean;
  /** Son denetimden sonra taslak değişti. */
  bayat: boolean;
  onGit: (uyari: LexisUyari) => void;
};

const SEVIYE_SIRASI: UyariSeviyesi[] = ["HATA", "UYARI", "BILGI"];
const SEVIYE_ADLARI: Record<UyariSeviyesi, string> = { HATA: "Düzeltilmeli", UYARI: "Gözden geçirin", BILGI: "Bilgi" };
const SEVIYE_SIMGESI = { HATA: AlertOctagon, UYARI: AlertTriangle, BILGI: Info } as const;
const SEVIYE_RENGI: Record<UyariSeviyesi, string> = { HATA: "text-tone-danger", UYARI: "text-tone-caution", BILGI: "text-[var(--fg-subtle)]" };

/** Denetimin bütün uyarıları, seviyeye göre gruplu. Satıra tıklanınca taslakta ilgili madde / alan / bölüme gidilir. */
export function UyariListesi({ uyarilar, bolumAdlari, taslakVar, bayat, onGit }: UyariListesiProps) {
  return (
    <section aria-label="Uyarılar" data-testid="lexis-uyarilar" className="grid gap-2">
      <BolgeBasligi sag={taslakVar ? <span className="font-mono text-[10.5px] tabular-nums text-[var(--fg-subtle)]">{uyarilar.length}</span> : undefined}>
        Uyarılar
      </BolgeBasligi>
      {!taslakVar && <BosDurum>Taslak yazılınca dayanak, atıf ve muallak denetiminin sonuçları burada listelenir.</BosDurum>}
      {taslakVar && bayat && <p className="text-[12px] text-[var(--fg-muted)]">Taslak değişti; aşağıdaki sonuçlar son denetime aittir.</p>}
      {taslakVar && uyarilar.length === 0 && (
        <p className="flex items-center gap-1.5 text-[12.5px] text-tone-ok">
          <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
          Uyarı yok.
        </p>
      )}
      {SEVIYE_SIRASI.map((seviye) => {
        const grup = uyarilar.filter((u) => u.seviye === seviye);
        if (grup.length === 0) return null;
        const Simge = SEVIYE_SIMGESI[seviye];
        return (
          <div key={seviye} className="grid gap-1">
            <div className={`flex items-center gap-1.5 text-[11.5px] font-medium ${SEVIYE_RENGI[seviye]}`}>
              <Simge className="w-3.5 h-3.5" aria-hidden="true" />
              {SEVIYE_ADLARI[seviye]} · {grup.length}
            </div>
            <ul className="grid gap-1">
              {grup.map((u) => {
                const yer = [u.bolum && (bolumAdlari[u.bolum] ?? u.bolum), u.madde !== null && `madde ${u.madde}`].filter(Boolean).join(" · ");
                return (
                  <li key={u.id}>
                    <button
                      type="button"
                      onClick={() => onGit(u)}
                      disabled={!u.bolum}
                      className="w-full text-left border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-1.5 hover:border-[var(--brand)] disabled:hover:border-[var(--border)] disabled:cursor-default transition-colors"
                    >
                      <span className="block text-[12.5px] leading-[1.45] text-[var(--fg)]">{u.metin}</span>
                      {yer && <span className="block text-[11px] text-[var(--fg-subtle)]">{yer}</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
