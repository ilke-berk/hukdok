import { Plus, Trash2 } from "lucide-react";
import { KUSUR_ADLARI, RISK_ADLARI, type KusurTespiti, type MuallakKriterSatiri, type RiskDuzeyi } from "@/types/lexis";
import { BosDurum, SimgeDugmesi, TutarGirdisi } from "./ortak";
import { SECIM_SINIFI, TH_SINIFI } from "./yardimcilar";

type MuallakKriterTablosuProps = {
  satirlar: MuallakKriterSatiri[];
  onDegistir: (satirlar: MuallakKriterSatiri[]) => void;
};

const HUCRE = "px-1.5 py-1 align-middle";
const METIN_GIRDISI =
  "w-full h-8 px-2 border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[3px] text-[12.5px] text-[var(--fg)] focus:border-[var(--brand)] focus:outline-none";

/**
 * Şirketin muallak kriter tablosu: yıl × kusur tespiti × risk düzeyi → tutar. Muallak önerisi ÖNCE bu tabloya
 * bakar (K11); satır yoksa emsal raporlara düşer. Boş tutar "bu kalemde muallak ayrılmaz" demektir.
 */
export function MuallakKriterTablosu({ satirlar, onDegistir }: MuallakKriterTablosuProps) {
  const guncelle = (sira: number, yama: Partial<MuallakKriterSatiri>) => onDegistir(satirlar.map((s, i) => (i === sira ? { ...s, ...yama } : s)));
  const ekle = () =>
    onDegistir([...satirlar, { yil: new Date().getFullYear(), kusur_tespiti: "KOMPLIKASYON", risk_duzeyi: "RISKLI", maddi: null, manevi: null, aciklama: "" }]);

  return (
    <div className="grid gap-2" data-testid="lexis-kriter-tablosu">
      {satirlar.length === 0 ? (
        <BosDurum>Kriter satırı yok: bu şirkette muallak önerisi yalnız emsal raporlara dayanır.</BosDurum>
      ) : (
        <div className="overflow-x-auto border border-[var(--border)] bg-[var(--bg)]">
          <table className="w-full border-collapse min-w-[720px]">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className={`${TH_SINIFI} w-[84px]`}>Yıl</th>
                <th className={TH_SINIFI}>Kusur tespiti</th>
                <th className={TH_SINIFI}>Risk</th>
                <th className={`${TH_SINIFI} text-right`}>Maddi (TL)</th>
                <th className={`${TH_SINIFI} text-right`}>Manevi (TL)</th>
                <th className={TH_SINIFI}>Açıklama</th>
                <th className={`${TH_SINIFI} w-9`}>
                  <span className="sr-only">İşlem</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {satirlar.map((s, i) => (
                <tr key={i} className="border-b border-[var(--border)] last:border-b-0">
                  <td className={HUCRE}>
                    <input
                      type="number"
                      aria-label={`Satır ${i + 1} yıl`}
                      value={s.yil}
                      min={2000}
                      max={2100}
                      onChange={(e) => guncelle(i, { yil: Number(e.target.value) || s.yil })}
                      className={`${METIN_GIRDISI} font-mono tabular-nums`}
                    />
                  </td>
                  <td className={HUCRE}>
                    <select
                      aria-label={`Satır ${i + 1} kusur tespiti`}
                      className={`${SECIM_SINIFI} w-full`}
                      value={s.kusur_tespiti}
                      onChange={(e) => guncelle(i, { kusur_tespiti: e.target.value as KusurTespiti })}
                    >
                      {(Object.keys(KUSUR_ADLARI) as KusurTespiti[]).map((kod) => (
                        <option key={kod} value={kod}>
                          {KUSUR_ADLARI[kod]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className={HUCRE}>
                    <select
                      aria-label={`Satır ${i + 1} risk düzeyi`}
                      className={`${SECIM_SINIFI} w-full`}
                      value={s.risk_duzeyi}
                      onChange={(e) => guncelle(i, { risk_duzeyi: e.target.value as RiskDuzeyi })}
                    >
                      {(Object.keys(RISK_ADLARI) as RiskDuzeyi[]).map((kod) => (
                        <option key={kod} value={kod}>
                          {RISK_ADLARI[kod]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className={`${HUCRE} w-[150px]`}>
                    <TutarGirdisi key={`maddi-${i}-${s.maddi}`} ariaEtiket={`Satır ${i + 1} maddi tutar`} deger={s.maddi} onDegistir={(d) => guncelle(i, { maddi: d })} />
                  </td>
                  <td className={`${HUCRE} w-[150px]`}>
                    <TutarGirdisi key={`manevi-${i}-${s.manevi}`} ariaEtiket={`Satır ${i + 1} manevi tutar`} deger={s.manevi} onDegistir={(d) => guncelle(i, { manevi: d })} />
                  </td>
                  <td className={HUCRE}>
                    <input
                      type="text"
                      aria-label={`Satır ${i + 1} açıklama`}
                      value={s.aciklama}
                      onChange={(e) => guncelle(i, { aciklama: e.target.value })}
                      className={METIN_GIRDISI}
                    />
                  </td>
                  <td className={HUCRE}>
                    <SimgeDugmesi etiket={`Satır ${i + 1}: sil`} onClick={() => onDegistir(satirlar.filter((_, j) => j !== i))}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </SimgeDugmesi>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" onClick={ekle} className="justify-self-start inline-flex items-center gap-1 text-[12px] text-[var(--fg-subtle)] hover:text-[var(--fg)]">
        <Plus className="w-3 h-3" aria-hidden="true" />
        Satır ekle
      </button>
    </div>
  );
}
