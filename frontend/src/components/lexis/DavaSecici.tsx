import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { lexisApi } from "@/lib/lexisApi";
import { SIRKET_ADLARI, type LexisDava } from "@/types/lexis";
import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import { BolgeBasligi, BosDurum, SimgeDugmesi } from "./ortak";
import { hataMetni, iptalMi } from "./yardimcilar";

type DavaSeciciProps = {
  secili: LexisDava | null;
  onSec: (dava: LexisDava | null) => void;
  /** Taslak yazılırken dava değiştirilemez. */
  kilitli?: boolean;
  /** Yazarken arama gecikmesi (ms). */
  gecikme?: number;
};

/**
 * Rapor yazılacak davayı arar ve seçer. Seçilen dava çip olarak kalır; "Değiştir" aramaya döner. Boş sorgu
 * son davaları listeler. Arama `lexisApi.davaAra` üzerinden — entegrasyonda HukuDok dava aramasına bağlanır.
 */
export function DavaSecici({ secili, onSec, kilitli = false, gecikme = 250 }: DavaSeciciProps) {
  const [sorgu, setSorgu] = useState("");
  const [sonuclar, setSonuclar] = useState<LexisDava[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    if (secili) return;
    const ac = new AbortController();
    const zamanlayici = setTimeout(
      () => {
        lexisApi
          .davaAra(sorgu, ac.signal)
          .then((liste) => {
            setSonuclar(liste);
            setHata(null);
          })
          .catch((e: unknown) => {
            if (!iptalMi(e)) setHata(hataMetni(e));
          });
      },
      sorgu ? gecikme : 0,
    );
    return () => {
      clearTimeout(zamanlayici);
      ac.abort();
    };
  }, [sorgu, secili, gecikme]);

  if (secili) {
    return (
      <section aria-label="Seçili dava" data-testid="lexis-secili-dava" className="grid gap-2">
        <BolgeBasligi
          sag={
            <SimgeDugmesi etiket="Davayı değiştir" onClick={() => onSec(null)} disabled={kilitli}>
              <X className="w-3.5 h-3.5" />
            </SimgeDugmesi>
          }
        >
          Dava
        </BolgeBasligi>
        <div className="border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2.5 min-w-0">
          <div className="font-mono text-[12px] font-semibold text-[var(--fg)] break-all">{secili.ofis_no}</div>
          <div className="mt-1 text-[12.5px] text-[var(--fg-muted)] leading-[1.5]">
            {[secili.mahkeme, secili.esas_no && `${secili.esas_no} E.`].filter(Boolean).join(" · ") || "Mahkeme bilgisi yok"}
          </div>
          <div className="text-[12.5px] text-[var(--fg-muted)]">{[secili.sigortali, secili.karsi_taraf].filter(Boolean).join(" — ")}</div>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Dava seç" className="grid gap-2">
      <BolgeBasligi>Dava seç</BolgeBasligi>
      <label className="relative block">
        <span className="sr-only">Dava ara</span>
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" aria-hidden="true" />
        <input
          type="search"
          value={sorgu}
          onChange={(e) => setSorgu(e.target.value)}
          placeholder="Ofis no, esas no, hasar no, taraf…"
          className="w-full h-9 pl-8 pr-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none"
        />
      </label>
      {hata && (
        <p role="alert" className="text-[12.5px] text-tone-danger">
          {hata}
        </p>
      )}
      {!hata && sonuclar === null && <LineListSkeleton count={3} label="Davalar yükleniyor…" />}
      {sonuclar && sonuclar.length === 0 && <BosDurum>Bu aramaya uyan dava yok.</BosDurum>}
      {sonuclar && sonuclar.length > 0 && (
        <ul className="grid gap-1.5" data-testid="lexis-dava-sonuclari">
          {sonuclar.map((d) => (
            <li key={d.case_id}>
              <button
                type="button"
                onClick={() => onSec(d)}
                className="w-full text-left border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 hover:border-[var(--brand)] transition-colors min-w-0"
              >
                <div className="font-mono text-[11.5px] font-semibold text-[var(--fg)] break-all">{d.ofis_no}</div>
                <div className="mt-0.5 text-[12px] text-[var(--fg-muted)] leading-[1.45]">
                  {[d.sirket && SIRKET_ADLARI[d.sirket], d.mahkeme, d.esas_no && `${d.esas_no} E.`].filter(Boolean).join(" · ")}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
