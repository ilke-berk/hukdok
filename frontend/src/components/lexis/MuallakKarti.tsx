import { BOS, tutarYaz } from "@/lib/lexisMetin";
import { KUSUR_ADLARI, RISK_ADLARI, TEMINAT_ADLARI, type MuallakDayanakTuru, type MuallakOnerisi } from "@/types/lexis";
import { BolgeBasligi, BosDurum, Rozet, TutarGirdisi } from "./ortak";
import type { MuallakSiniflari } from "./useTezgah";
import { BAGLANTI_SINIFI, type RozetTonu } from "./yardimcilar";

type MuallakKartiProps = {
  oneri: MuallakOnerisi | null;
  /** İnsanın yazdığı kesin tutarlar; `null` = öneri geçerli. */
  maddi: number | null;
  manevi: number | null;
  talepMaddi: number | null;
  talepManevi: number | null;
  teminatLimiti: number | null;
  onDegistir: (yama: { maddi?: number | null; manevi?: number | null }) => void;
  /** Dayanak satırındaki emsal raporu okuyucuda açar. */
  onRaporOku: (sha256: string) => void;
  /** Verilirse sınıflar seçilebilir olur (gerçek dava kipi); verilmezse rozet olarak gösterilir. */
  onSinif?: (yama: MuallakSiniflari) => void;
  kilitli?: boolean;
};

const DAYANAK: Record<MuallakDayanakTuru, { ad: string; ton: RozetTonu; aciklama: string }> = {
  KRITER: { ad: "Kriter tablosu", ton: "ok", aciklama: "Tutar şirketin kriter tablosundaki satırdan alındı." },
  EMSAL: { ad: "Emsal raporlar", ton: "caution", aciklama: "Kriter satırı yok; tutar aynı sınıftaki en yakın yıllı emsal raporlardan alındı." },
  YOK: { ad: "Dayanak yok", ton: "danger", aciklama: "Kriter satırı da tutarlı emsal de yok; tutar önerilmedi." },
};

/**
 * Muallak (K11): tutarı kod önerir, model seçmez. Kart önerinin DAYANAĞINI gösterir (kriter satırı ya da emsal
 * raporların tutarları) ve kesin tutarı insana bıraktırır — boş bırakılan alanda öneri geçerlidir.
 */
export function MuallakKarti({ oneri, maddi, manevi, talepMaddi, talepManevi, teminatLimiti, onDegistir, onRaporOku, onSinif, kilitli = false }: MuallakKartiProps) {
  if (!oneri) {
    return (
      <section aria-label="Muallak" className="grid gap-2">
        <BolgeBasligi>Muallak</BolgeBasligi>
        <BosDurum>Öneri taslakla birlikte hesaplanır: önce şirket kriter tablosu, yoksa aynı sınıftaki emsal raporlar.</BosDurum>
      </section>
    );
  }
  const dayanak = DAYANAK[oneri.dayanak];
  const elle = maddi !== null || manevi !== null;
  return (
    <section aria-label="Muallak" data-testid="lexis-muallak" className="grid gap-2.5">
      <BolgeBasligi sag={<Rozet ton={dayanak.ton}>{dayanak.ad}</Rozet>}>Muallak</BolgeBasligi>

      <div className="grid grid-cols-2 gap-2">
        {(
          [
            ["Öneri (maddi)", oneri.maddi],
            ["Öneri (manevi)", oneri.manevi],
          ] as const
        ).map(([etiket, tutar]) => (
          <div key={etiket} className="border border-[var(--border)] bg-[var(--bg-elevated)] px-2.5 py-2 min-w-0">
            <div className="text-[11px] text-[var(--fg-subtle)]">{etiket}</div>
            {/* Tutar önerilmeyen kalem "—"; hiç dayanak yoksa doldurulmamış yer işareti */}
            <div className={`font-mono text-[14px] font-semibold tabular-nums truncate ${tutar === null ? "text-[var(--fg-subtle)]" : "text-[var(--fg)]"}`}>
              {tutar === null ? (oneri.dayanak === "YOK" ? BOS : "—") : tutarYaz(tutar)}
            </div>
          </div>
        ))}
      </div>

      <p className="text-[12px] leading-[1.5] text-[var(--fg-muted)]">{dayanak.aciklama}</p>

      {onSinif ? (
        // Sınıfları insan seçer (belgelerden yazım gelene kadar); her değişimde öneri yeniden hesaplanır.
        <div className="grid gap-1.5" data-testid="lexis-muallak-siniflar">
          {(
            [
              ["Kusur tespiti", "kusur_tespiti", KUSUR_ADLARI, oneri.kusur_tespiti],
              ["Risk düzeyi", "risk_duzeyi", RISK_ADLARI, oneri.risk_duzeyi],
              ["Teminat", "teminat", TEMINAT_ADLARI, oneri.teminat],
            ] as const
          ).map(([etiket, alan, adlar, deger]) => (
            <label key={alan} className="grid grid-cols-[92px_minmax(0,1fr)] items-center gap-2 text-[12px] text-[var(--fg-muted)]">
              {etiket}
              <select
                aria-label={etiket}
                value={deger}
                disabled={kilitli}
                onChange={(e) => onSinif({ [alan]: e.target.value })}
                className="h-7 min-w-0 px-1.5 rounded-[3px] border border-[var(--border)] bg-[var(--bg-elevated)] text-[12.5px] text-[var(--fg)] focus:border-[var(--brand)] focus:outline-none disabled:opacity-60"
              >
                {Object.entries(adlar).map(([kod, ad]) => (
                  <option key={kod} value={kod}>
                    {ad}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1">
          <Rozet>{KUSUR_ADLARI[oneri.kusur_tespiti]}</Rozet>
          <Rozet>Risk: {RISK_ADLARI[oneri.risk_duzeyi]}</Rozet>
          <Rozet>{TEMINAT_ADLARI[oneri.teminat]}</Rozet>
        </div>
      )}

      {oneri.dayanak_satirlari.length > 0 && (
        <table className="w-full text-[12px]" data-testid="lexis-muallak-dayanak">
          <caption className="sr-only">Muallak dayanağı</caption>
          <thead>
            <tr className="text-left text-[11px] text-[var(--fg-subtle)]">
              <th className="font-normal pb-1">Dayanak</th>
              <th className="font-normal pb-1 text-right">Maddi</th>
              <th className="font-normal pb-1 text-right">Manevi</th>
            </tr>
          </thead>
          <tbody>
            {oneri.dayanak_satirlari.map((s, i) => (
              <tr key={i} className="border-t border-[var(--border)] align-top">
                <td className="py-1 pr-2 text-[var(--fg)]">
                  {s.rapor_sha ? (
                    <button type="button" onClick={() => onRaporOku(s.rapor_sha!)} className={`text-left ${BAGLANTI_SINIFI}`}>
                      {s.aciklama}
                    </button>
                  ) : (
                    s.aciklama
                  )}
                </td>
                <td className="py-1 font-mono tabular-nums text-right whitespace-nowrap">{s.maddi === null ? "—" : tutarYaz(s.maddi)}</td>
                <td className="py-1 font-mono tabular-nums text-right whitespace-nowrap">{s.manevi === null ? "—" : tutarYaz(s.manevi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {oneri.uyarilar.map((u) => (
        <p key={u} className="text-[12px] leading-[1.45] text-tone-caution">
          {u}
        </p>
      ))}

      <div className="grid gap-1.5 border-t border-[var(--border)] pt-2.5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--fg)]">Rapora yazılacak tutar</span>
          {elle && (
            <button
              type="button"
              onClick={() => onDegistir({ maddi: null, manevi: null })}
              disabled={kilitli}
              className={`text-[11.5px] ${BAGLANTI_SINIFI}`}
            >
              Öneriye dön
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <TutarGirdisi key={`maddi-${maddi}`} etiket="Maddi (TL)" deger={maddi} oneri={oneri.maddi} kilitli={kilitli} onDegistir={(d) => onDegistir({ maddi: d })} />
          <TutarGirdisi
            key={`manevi-${manevi}`}
            etiket="Manevi (TL)"
            deger={manevi}
            oneri={oneri.manevi}
            kilitli={kilitli}
            onDegistir={(d) => onDegistir({ manevi: d })}
          />
        </div>
        <p className="text-[11.5px] leading-[1.5] text-[var(--fg-subtle)]">
          Sınırlar — talep: {tutarYaz(talepMaddi)} maddi, {tutarYaz(talepManevi)} manevi · teminat limiti: {tutarYaz(teminatLimiti)}. Boş bırakılan alanda
          öneri yazılır.
        </p>
      </div>
    </section>
  );
}
