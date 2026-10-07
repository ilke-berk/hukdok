import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { TableSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { lexisApi } from "@/lib/lexisApi";
import {
  KUSUR_ADLARI,
  RISK_ADLARI,
  SIRKET_ADLARI,
  type KusurTespiti,
  type KutuphaneFiltresi,
  type KutuphaneKaydi,
  type LexisSirket,
  type RaporTuru,
  type RiskDuzeyi,
} from "@/types/lexis";
import { EmsalOkuyucu } from "./EmsalOkuyucu";
import { KararBankasiTablosu } from "./KararBankasiTablosu";
import { KararRafi } from "./KararRafi";
import { useVeri } from "./useVeri";
import { BAGLANTI_SINIFI, SECIM_SINIFI, TD_SINIFI, TH_SINIFI, hataMetni, muallakOzeti } from "./yardimcilar";

type Gorunum = "raporlar" | "raf" | "kararlar";

const BOS_FILTRE: KutuphaneFiltresi = { sirket: null, rapor_turu: null, uzmanlik: null, kusur_tespiti: null, risk_duzeyi: null, metin: "" };

/**
 * "Kütüphane" sekmesi: emsal külliyatını rapor yazmadan da taramak için. Filtre şeridi (metin, şirket, tür,
 * uzmanlık, kusur tespiti, risk) + sonuç tablosu; satır maskeli raporu okuyucuda açar. Diğer görünümler: karar rafı
 * (büronun kendi kararları, kodun çıkardığı sonuç / tutar / gerekçe alanlarıyla — `KararRafi`) ve karar bankası
 * (raporlarda ANILAN kararlar). Uzmanlık seçenekleri ilk (süzülmemiş) yüklemedeki raporlardan türetilir.
 */
export function KutuphaneTarayici() {
  const [gorunum, setGorunum] = useState<Gorunum>("raporlar");
  const [filtre, setFiltre] = useState<KutuphaneFiltresi>(BOS_FILTRE);
  const [metin, setMetin] = useState("");
  const [uzmanliklar, setUzmanliklar] = useState<string[]>([]);
  const [okunan, setOkunan] = useState<KutuphaneKaydi | null>(null);

  // Yazarken her tuşta istek atılmaz.
  useEffect(() => {
    const zamanlayici = setTimeout(() => setFiltre((f) => (f.metin === metin ? f : { ...f, metin })), 250);
    return () => clearTimeout(zamanlayici);
  }, [metin]);

  const { veri, hata, yukleniyor, yenile } = useVeri((signal) => lexisApi.kutuphaneAra(filtre, signal), JSON.stringify(filtre));

  const suzulmus = useMemo(() => Object.values(filtre).some((d) => d !== null && d !== ""), [filtre]);
  useEffect(() => {
    if (!veri || suzulmus) return;
    setUzmanliklar([...new Set(veri.map((k) => k.etiketler.uzmanlik ?? k.okuma.uzmanlik).filter((u): u is string => !!u))].sort((a, b) => a.localeCompare(b, "tr")));
  }, [veri, suzulmus]);

  const raporOku = async (sha256: string) => {
    try {
      setOkunan(await lexisApi.raporGetir(sha256));
    } catch (e) {
      toast.error("Rapor açılamadı", { description: hataMetni(e) });
    }
  };

  const temizle = () => {
    setMetin("");
    setFiltre(BOS_FILTRE);
  };

  return (
    <div data-testid="lexis-kutuphane" className="h-full overflow-y-auto px-3 md:px-6 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <h2 className="font-display text-[19px] font-medium text-[var(--fg)]">
          {gorunum === "raf" ? "Karar rafı" : "Emsal kütüphanesi"}
          {gorunum === "raporlar" && veri && <span className="ml-2 font-mono text-[11px] text-[var(--fg-subtle)] tabular-nums">{veri.length} rapor</span>}
        </h2>
        <div role="group" aria-label="Görünüm" className="inline-flex border border-[var(--border)]">
          {(
            [
              ["raporlar", "Raporlar"],
              ["raf", "Karar rafı"],
              ["kararlar", "Karar bankası"],
            ] as const
          ).map(([kod, ad]) => (
            <button
              key={kod}
              type="button"
              aria-pressed={gorunum === kod}
              onClick={() => setGorunum(kod)}
              className={`h-8 px-3 text-[12px] transition-colors ${
                gorunum === kod ? "bg-[var(--brand-soft)] text-[var(--fg)] font-medium" : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
              }`}
            >
              {ad}
            </button>
          ))}
        </div>
      </div>

      {gorunum === "raf" ? (
        <KararRafi />
      ) : gorunum === "kararlar" ? (
        <div className="border border-[var(--border)] bg-[var(--bg)]">
          <KararBankasiTablosu onRaporOku={(sha) => void raporOku(sha)} />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="lexis-kutuphane-filtreleri">
            <label className="relative block min-w-[220px] flex-1 max-w-md">
              <span className="sr-only">Kütüphanede ara</span>
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" aria-hidden="true" />
              <input
                type="search"
                value={metin}
                onChange={(e) => setMetin(e.target.value)}
                placeholder="İşlem, olay, mahkeme ya da rapor metni…"
                className="w-full h-8 pl-8 pr-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[12.5px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none"
              />
            </label>
            <select
              aria-label="Şirket"
              className={SECIM_SINIFI}
              value={filtre.sirket ?? ""}
              onChange={(e) => setFiltre((f) => ({ ...f, sirket: (e.target.value || null) as LexisSirket | null }))}
            >
              <option value="">Şirket: tümü</option>
              {(Object.keys(SIRKET_ADLARI) as LexisSirket[]).map((kod) => (
                <option key={kod} value={kod}>
                  {SIRKET_ADLARI[kod]}
                </option>
              ))}
            </select>
            <select
              aria-label="Rapor türü"
              className={SECIM_SINIFI}
              value={filtre.rapor_turu ?? ""}
              onChange={(e) => setFiltre((f) => ({ ...f, rapor_turu: (e.target.value || null) as RaporTuru | null }))}
            >
              <option value="">Tür: tümü</option>
              <option value="ANA">Ana rapor</option>
              <option value="EK">Ek rapor</option>
            </select>
            <select
              aria-label="Uzmanlık"
              className={SECIM_SINIFI}
              value={filtre.uzmanlik ?? ""}
              onChange={(e) => setFiltre((f) => ({ ...f, uzmanlik: e.target.value || null }))}
            >
              <option value="">Uzmanlık: tümü</option>
              {uzmanliklar.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
            <select
              aria-label="Kusur tespiti"
              className={SECIM_SINIFI}
              value={filtre.kusur_tespiti ?? ""}
              onChange={(e) => setFiltre((f) => ({ ...f, kusur_tespiti: (e.target.value || null) as KusurTespiti | null }))}
            >
              <option value="">Kusur: tümü</option>
              {(Object.keys(KUSUR_ADLARI) as KusurTespiti[]).map((kod) => (
                <option key={kod} value={kod}>
                  {KUSUR_ADLARI[kod]}
                </option>
              ))}
            </select>
            <select
              aria-label="Risk düzeyi"
              className={SECIM_SINIFI}
              value={filtre.risk_duzeyi ?? ""}
              onChange={(e) => setFiltre((f) => ({ ...f, risk_duzeyi: (e.target.value || null) as RiskDuzeyi | null }))}
            >
              <option value="">Risk: tümü</option>
              {(Object.keys(RISK_ADLARI) as RiskDuzeyi[]).map((kod) => (
                <option key={kod} value={kod}>
                  {RISK_ADLARI[kod]}
                </option>
              ))}
            </select>
            {(suzulmus || metin) && (
              <button type="button" onClick={temizle} className={`text-[12px] ${BAGLANTI_SINIFI}`}>
                Filtreleri temizle
              </button>
            )}
          </div>

          <div className="border border-[var(--border)] bg-[var(--bg)]">
            {hata ? (
              <div className="p-4">
                <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
              </div>
            ) : !veri ? (
              <TableSkeleton rows={6} columns={7} label="Kütüphane yükleniyor…" />
            ) : veri.length === 0 ? (
              <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Bu filtrelere uyan rapor yok.</p>
            ) : (
              <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--border)]">
                      <th className={TH_SINIFI}>Rapor</th>
                      <th className={TH_SINIFI}>Şirket</th>
                      <th className={TH_SINIFI}>Tür</th>
                      <th className={TH_SINIFI}>Yıl</th>
                      <th className={TH_SINIFI}>Uzmanlık</th>
                      <th className={TH_SINIFI}>İşlem · olay</th>
                      <th className={TH_SINIFI}>Kusur · risk</th>
                      <th className={TH_SINIFI}>Muallak</th>
                    </tr>
                  </thead>
                  <tbody>
                    {veri.map((k) => {
                      const { okuma, etiketler } = k;
                      return (
                        <tr
                          key={okuma.sha256}
                          data-testid="lexis-kutuphane-satiri"
                          className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg-elevated)] transition-colors"
                        >
                          <td className={`${TD_SINIFI} whitespace-nowrap`}>
                            <button type="button" onClick={() => setOkunan(k)} className={`font-mono text-[11.5px] ${BAGLANTI_SINIFI}`}>
                              {okuma.rapor_no ?? okuma.dosya}
                            </button>
                          </td>
                          <td className={`${TD_SINIFI} whitespace-nowrap`}>{okuma.sirket ? SIRKET_ADLARI[okuma.sirket] : "—"}</td>
                          <td className={`${TD_SINIFI} whitespace-nowrap`}>
                            {okuma.rapor_turu === "EK" ? "Ek" : "Ana"}
                            <span className="ml-1.5 font-mono text-[10.5px] text-[var(--fg-subtle)]">{okuma.iskelet}</span>
                          </td>
                          <td className={`${TD_SINIFI} font-mono text-[11.5px] tabular-nums`}>{okuma.rapor_tarihi?.slice(0, 4) ?? "—"}</td>
                          <td className={TD_SINIFI}>{etiketler.uzmanlik ?? okuma.uzmanlik ?? "—"}</td>
                          <td className={TD_SINIFI}>
                            {[etiketler.tibbi_islem, ...etiketler.tibbi_olay].filter(Boolean).join(" · ") || "—"}
                            <span className="block text-[12px] text-[var(--fg-muted)] leading-[1.45] max-w-[420px]">{etiketler.iddia_ozeti}</span>
                          </td>
                          <td className={`${TD_SINIFI} whitespace-nowrap`}>
                            {KUSUR_ADLARI[etiketler.kusur_tespiti]}
                            <span className="block text-[12px] text-[var(--fg-muted)]">risk: {RISK_ADLARI[etiketler.risk_duzeyi].toLocaleLowerCase("tr")}</span>
                          </td>
                          <td className={`${TD_SINIFI} font-mono text-[11.5px] tabular-nums`}>{muallakOzeti(okuma) ?? "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <EmsalOkuyucu kayit={okunan} onKapat={() => setOkunan(null)} />
    </div>
  );
}
