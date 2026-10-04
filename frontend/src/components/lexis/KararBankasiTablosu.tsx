import { TableSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { lexisApi } from "@/lib/lexisApi";
import { tarihYaz } from "@/lib/lexisMetin";
import { Rozet } from "./ortak";
import { useVeri } from "./useVeri";
import { BAGLANTI_SINIFI, TD_SINIFI, TH_SINIFI } from "./yardimcilar";

type KararBankasiTablosuProps = {
  /** Kararın geçtiği raporu okuyucuda açar. */
  onRaporOku: (sha256: string) => void;
};

/**
 * Karar bankası: kütüphanedeki raporlarda anılan yargı kararları, merci + E/K ile tekil. Taslaktaki emsal karar
 * atfı yalnız buradan ya da dosyanın kendi belgelerinden gelebilir (atıf doğrulaması).
 */
export function KararBankasiTablosu({ onRaporOku }: KararBankasiTablosuProps) {
  const { veri, hata, yukleniyor, yenile } = useVeri((signal) => lexisApi.kararBankasi(signal));

  if (hata) {
    return (
      <div className="p-4">
        <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
      </div>
    );
  }
  if (!veri) return <TableSkeleton rows={3} columns={5} label="Karar bankası yükleniyor…" />;
  if (veri.length === 0) return <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Kütüphanede anılan karar yok.</p>;

  return (
    <div className="overflow-x-auto" data-testid="lexis-karar-bankasi">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className={TH_SINIFI}>Merci</th>
            <th className={TH_SINIFI}>Esas / Karar</th>
            <th className={TH_SINIFI}>Tarih</th>
            <th className={TH_SINIFI}>Niteliği</th>
            <th className={TH_SINIFI}>Geçtiği raporlar</th>
          </tr>
        </thead>
        <tbody>
          {veri.map((k) => (
            <tr key={`${k.merci}-${k.esas_no}-${k.karar_no}`} className="border-b border-[var(--border)] last:border-b-0">
              <td className={TD_SINIFI}>{k.merci ?? "—"}</td>
              <td className={`${TD_SINIFI} font-mono text-[11.5px] whitespace-nowrap`}>
                {k.esas_no} E., {k.karar_no} K.
              </td>
              <td className={`${TD_SINIFI} font-mono text-[11.5px] tabular-nums whitespace-nowrap`}>{k.tarih ? tarihYaz(k.tarih) : "—"}</td>
              <td className={TD_SINIFI}>{k.emsal ? <Rozet ton="ok">emsal</Rozet> : <Rozet>dosyanın kararı</Rozet>}</td>
              <td className={TD_SINIFI}>
                <span className="inline-flex flex-wrap gap-x-2 gap-y-0.5">
                  {k.raporlar.map((sha, i) => (
                    <button key={sha} type="button" onClick={() => onRaporOku(sha)} className={BAGLANTI_SINIFI}>
                      rapor {i + 1}
                    </button>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
