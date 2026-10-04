import { useState } from "react";
import { toast } from "sonner";
import { TableSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { FlowButton } from "@/components/flow/primitives";
import { lexisApi } from "@/lib/lexisApi";
import { BAG_ANAHTARI_ADLARI, BAG_DURUMU_ADLARI, SIRKET_ADLARI, type BagDurumu, type RaporBagi } from "@/types/lexis";
import { KartSecimDiyalogu } from "./KartSecimDiyalogu";
import { Rozet } from "./ortak";
import { useVeri } from "./useVeri";
import { BAGLANTI_SINIFI, TD_SINIFI, TH_SINIFI, hataMetni, type RozetTonu } from "./yardimcilar";

type Suzgec = BagDurumu | "TUMU" | "BEKLEYEN";

const DURUM_TONU: Record<BagDurumu, RozetTonu> = { TEK: "ok", COK_ADAY: "caution", CELISKI: "danger", YOK: "muted" };

/** Kart seçimi bekleyen satır: çok adaylı ya da çelişkili ve insan henüz seçmemiş. */
const bekliyor = (s: RaporBagi) => (s.bag.durum === "COK_ADAY" || s.bag.durum === "CELISKI") && s.bag.birincil === null;

/**
 * "Kart bağı" sekmesi: eski raporu dava kartına bağlarken tek karta inmeyen satırlar (çok aday, çelişki, bağ
 * yok). Çok adaylı ve çelişkili satırda kartı insan seçer (K8); seçim geri alınabilir. Bağ yok satırında
 * yapılacak iş yoktur — hiçbir anahtar karta götürmemiştir, yalnız listelenir.
 */
export function KartBagiListesi() {
  const { veri, hata, yukleniyor, yenile, setVeri } = useVeri((signal) => lexisApi.kartBaglari(signal));
  const [suzgec, setSuzgec] = useState<Suzgec>("BEKLEYEN");
  const [secilenRapor, setSecilenRapor] = useState<string | null>(null);
  const [isleniyor, setIsleniyor] = useState(false);

  const sec = async (rapor: string, kartId: number | null) => {
    setIsleniyor(true);
    try {
      const guncel = await lexisApi.kartSec(rapor, kartId);
      setVeri((onceki) => onceki?.map((s) => (s.rapor === rapor ? guncel : s)) ?? null);
      setSecilenRapor(null);
      toast.success(kartId === null ? "Seçim geri alındı" : `Rapor kart #${kartId}'e bağlandı`);
    } catch (e) {
      toast.error("Seçim kaydedilemedi", { description: hataMetni(e) });
    } finally {
      setIsleniyor(false);
    }
  };

  const sayilar = (veri ?? []).reduce<Partial<Record<Suzgec, number>>>((s, satir) => {
    s[satir.bag.durum] = (s[satir.bag.durum] ?? 0) + 1;
    if (bekliyor(satir)) s.BEKLEYEN = (s.BEKLEYEN ?? 0) + 1;
    return s;
  }, {});
  const gorunen = (veri ?? []).filter((s) => (suzgec === "TUMU" ? true : suzgec === "BEKLEYEN" ? bekliyor(s) : s.bag.durum === suzgec));
  const secilen = veri?.find((s) => s.rapor === secilenRapor) ?? null;

  const suzgecler: [Suzgec, string, number][] = [
    ["BEKLEYEN", "Seçim bekleyen", sayilar.BEKLEYEN ?? 0],
    ["COK_ADAY", BAG_DURUMU_ADLARI.COK_ADAY, sayilar.COK_ADAY ?? 0],
    ["CELISKI", BAG_DURUMU_ADLARI.CELISKI, sayilar.CELISKI ?? 0],
    ["YOK", BAG_DURUMU_ADLARI.YOK, sayilar.YOK ?? 0],
    ["TUMU", "Tümü", veri?.length ?? 0],
  ];

  return (
    <div data-testid="lexis-kart-bagi" className="h-full overflow-y-auto px-3 md:px-6 py-5">
      <div className="mb-3 max-w-3xl">
        <h2 className="font-display text-[19px] font-medium text-[var(--fg)]">Kart bağı incelemesi</h2>
        <p className="mt-1 text-[12.5px] leading-[1.55] text-[var(--fg-muted)]">
          Eski raporlar dava kartına hasar no → dosya no → mahkeme + esas no sırasıyla bağlanır. Tek karta inen raporlar burada görünmez; aşağıdakiler
          birden çok karta düşen, anahtarları çelişen ya da hiçbir karta ulaşmayan raporlardır.
        </p>
      </div>

      <div role="group" aria-label="Durum süzgeci" className="flex flex-wrap gap-1.5 mb-3" data-testid="lexis-bag-suzgecleri">
        {suzgecler.map(([kod, ad, sayi]) => (
          <button
            key={kod}
            type="button"
            aria-pressed={suzgec === kod}
            onClick={() => setSuzgec(kod)}
            className={`inline-flex items-center gap-1.5 h-7 px-2.5 border text-[12px] transition-colors ${
              suzgec === kod ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--fg)] font-medium" : "border-[var(--border)] text-[var(--fg-muted)] hover:text-[var(--fg)]"
            }`}
          >
            {ad}
            <span className="font-mono text-[10.5px] tabular-nums text-[var(--fg-subtle)]">{sayi}</span>
          </button>
        ))}
      </div>

      <div className="border border-[var(--border)] bg-[var(--bg)]">
        {hata ? (
          <div className="p-4">
            <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
          </div>
        ) : !veri ? (
          <TableSkeleton rows={4} columns={5} label="Kart bağları yükleniyor…" />
        ) : gorunen.length === 0 ? (
          <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">
            {suzgec === "BEKLEYEN" ? "Seçim bekleyen rapor kalmadı." : "Bu durumda rapor yok."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className={TH_SINIFI}>Rapor</th>
                  <th className={TH_SINIFI}>Kimlikleri</th>
                  <th className={TH_SINIFI}>Durum</th>
                  <th className={TH_SINIFI}>Kart</th>
                  <th className={TH_SINIFI}>İşlem</th>
                </tr>
              </thead>
              <tbody>
                {gorunen.map((s) => {
                  const secilebilir = s.bag.adaylar.length > 0;
                  return (
                    <tr key={s.rapor} data-testid="lexis-bag-satiri" className="border-b border-[var(--border)] last:border-b-0">
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        <span className="font-mono text-[11.5px] font-semibold">{s.klasor}</span>
                        <span className="block text-[12px] text-[var(--fg-muted)]">
                          {[s.sirket && SIRKET_ADLARI[s.sirket], s.rapor_turu === "EK" ? "ek rapor" : "ana rapor"].filter(Boolean).join(" · ")}
                        </span>
                      </td>
                      <td className={TD_SINIFI}>
                        <span className="block">
                          <span className="text-[var(--fg-subtle)]">hasar no </span>
                          <span className="font-mono text-[11.5px]">{s.hasar_no ?? "—"}</span>
                        </span>
                        <span className="block text-[12px] text-[var(--fg-muted)]">{[s.mahkeme, s.esas_no && `${s.esas_no} E.`].filter(Boolean).join(" · ") || "mahkeme bilgisi yok"}</span>
                      </td>
                      <td className={TD_SINIFI}>
                        <Rozet ton={DURUM_TONU[s.bag.durum]}>{BAG_DURUMU_ADLARI[s.bag.durum]}</Rozet>
                        <span className="block mt-0.5 text-[12px] text-[var(--fg-muted)]">
                          {s.bag.anahtar ? `${BAG_ANAHTARI_ADLARI[s.bag.anahtar]} · ${s.bag.adaylar.length} aday` : "hiçbir anahtar karta götürmedi"}
                        </span>
                        {s.bag.uyarilar.map((u) => (
                          <span key={u} className="block text-[12px] text-tone-caution">
                            {u}
                          </span>
                        ))}
                      </td>
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        {s.bag.birincil !== null ? (
                          <>
                            <span className="font-mono text-[11.5px] font-semibold">Kart #{s.bag.birincil}</span>
                            {s.bag.insan_secimi && <span className="block text-[12px] text-[var(--fg-muted)]">insan seçimi</span>}
                          </>
                        ) : (
                          <span className="text-[var(--fg-subtle)]">{secilebilir ? "seçilmedi" : "—"}</span>
                        )}
                      </td>
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        {secilebilir ? (
                          <span className="inline-flex items-center gap-3">
                            <FlowButton variant={s.bag.birincil === null ? "primary" : "secondary"} size="sm" onClick={() => setSecilenRapor(s.rapor)} disabled={isleniyor}>
                              {s.bag.birincil === null ? "Kart seç" : "Değiştir"}
                            </FlowButton>
                            {s.bag.insan_secimi && (
                              <button type="button" onClick={() => void sec(s.rapor, null)} disabled={isleniyor} className={`text-[12px] ${BAGLANTI_SINIFI}`}>
                                Seçimi geri al
                              </button>
                            )}
                          </span>
                        ) : (
                          <span className="text-[12px] text-[var(--fg-subtle)]">yapılacak iş yok</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <KartSecimDiyalogu satir={secilen} isleniyor={isleniyor} onSec={(kartId) => secilen && void sec(secilen.rapor, kartId)} onKapat={() => setSecilenRapor(null)} />
    </div>
  );
}
