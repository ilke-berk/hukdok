import { RefreshCw } from "lucide-react";
import { TableSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { lexisApi } from "@/lib/lexisApi";
import { tarihSaatYaz } from "@/lib/lexisMetin";
import { SIRKET_ADLARI } from "@/types/lexis";
import { Rozet, SimgeDugmesi } from "./ortak";
import { useVeri } from "./useVeri";
import { TD_SINIFI, TH_SINIFI } from "./yardimcilar";

/**
 * "Geçmiş" sekmesi: yazılan taslakların koşu logu — kim, hangi dava, hangi iskelet, kaç emsal, kaç uyarı ve Word
 * indirildi mi. Sekme her açılışta yeniden çeker ("Rapor yaz"da biten koşu burada en üstte görünür).
 */
export function GecmisTablosu() {
  const { veri, hata, yukleniyor, yenile } = useVeri((signal) => lexisApi.gecmis(signal));

  return (
    <div data-testid="lexis-gecmis" className="h-full overflow-y-auto px-3 md:px-6 py-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="font-display text-[19px] font-medium text-[var(--fg)]">
          Taslak geçmişi
          {veri && <span className="ml-2 font-mono text-[11px] text-[var(--fg-subtle)] tabular-nums">{veri.length} koşu</span>}
        </h2>
        <SimgeDugmesi etiket="Geçmişi yenile" onClick={yenile} disabled={yukleniyor}>
          <RefreshCw className={`w-3.5 h-3.5 ${yukleniyor ? "animate-spin" : ""}`} />
        </SimgeDugmesi>
      </div>

      <div className="border border-[var(--border)] bg-[var(--bg)]">
        {hata ? (
          <div className="p-4">
            <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
          </div>
        ) : !veri ? (
          <TableSkeleton rows={4} columns={6} label="Geçmiş yükleniyor…" />
        ) : veri.length === 0 ? (
          <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Henüz taslak yazılmadı.</p>
        ) : (
          <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className={TH_SINIFI}>Zaman</th>
                  <th className={TH_SINIFI}>Dava</th>
                  <th className={TH_SINIFI}>Rapor</th>
                  <th className={`${TH_SINIFI} text-right`}>Emsal</th>
                  <th className={`${TH_SINIFI} text-right`}>Uyarı</th>
                  <th className={TH_SINIFI}>Kullanıcı</th>
                  <th className={TH_SINIFI}>Word</th>
                </tr>
              </thead>
              <tbody>
                {veri.map((k) => (
                  <tr key={k.id} data-testid="lexis-kosu" className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg-elevated)] transition-colors">
                    <td className={`${TD_SINIFI} font-mono text-[11px] tabular-nums whitespace-nowrap`}>{tarihSaatYaz(k.tarih)}</td>
                    <td className={`${TD_SINIFI} font-mono text-[11.5px]`}>{k.ofis_no}</td>
                    <td className={`${TD_SINIFI} whitespace-nowrap`}>
                      {[k.sirket && SIRKET_ADLARI[k.sirket], k.rapor_turu === "EK" ? "ek rapor" : "ana rapor"].filter(Boolean).join(" · ")}
                      <span className="ml-1.5 font-mono text-[10.5px] text-[var(--fg-subtle)]">{k.iskelet}</span>
                    </td>
                    <td className={`${TD_SINIFI} text-right tabular-nums`}>{k.emsal_sayisi}</td>
                    <td className={`${TD_SINIFI} text-right tabular-nums ${k.uyari_sayisi > 0 ? "text-tone-caution" : "text-tone-ok"}`}>{k.uyari_sayisi}</td>
                    <td className={`${TD_SINIFI} max-w-[240px] truncate`} title={k.kullanici}>
                      {k.kullanici}
                    </td>
                    <td className={`${TD_SINIFI} whitespace-nowrap`}>
                      {k.indirme_tarihi ? <Rozet ton="ok" title={tarihSaatYaz(k.indirme_tarihi)}>indirildi</Rozet> : <Rozet>taslak</Rozet>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
