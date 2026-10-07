import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Search } from "lucide-react";
import { TableSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { lexisApi } from "@/lib/lexisApi";
import { tarihYaz } from "@/lib/lexisMetin";
import { BELGE_TURU_RAF_ADLARI, DERECE_ADLARI, HUKUM_SINIFI_ADLARI, KONU_ADLARI, rafAdi, type RafSecenekleri, type RafSuzgeci } from "@/types/lexis";
import { KararOkuyucu } from "./KararOkuyucu";
import { Rozet } from "./ortak";
import { useVeri } from "./useVeri";
import { BAGLANTI_SINIFI, SECIM_SINIFI, TD_SINIFI, TH_SINIFI, hukumTonu, kararNumarasi, tutarListesi } from "./yardimcilar";

export const RAF_SAYFA_BOYU = 50;

type Suzgec = Required<Pick<RafSuzgeci, "belge_turu" | "derece" | "hukum_sinifi" | "sonuc_muvekkil" | "uzmanlik" | "konu" | "yalniz_kartli" | "metin">>;
const BOS_SUZGEC: Suzgec = { belge_turu: "karar", derece: null, hukum_sinifi: null, sonuc_muvekkil: null, uzmanlik: null, konu: null, yalniz_kartli: false, metin: "" };
const BOS_SECENEKLER: RafSecenekleri = { derece: [], uzmanlik: [], belge_turu: [], hukum_sinifi: [], sonuc_muvekkil: [] };

/**
 * Karar rafı (Kütüphane sekmesinin görünümü): büronun kendi kararları, kodun çıkardığı alanlarla — kararın bütünü
 * (hükümden), müvekkil yönünden sonuç (HUKDOK etiketi), talep ve hükmedilen tutarlar, gerekçe konuları. Süzgeçler ve
 * metin araması sunucuda koşar (karar metninin içinde de arar); satır kararı okuyucuda açar. Sayfa `RAF_SAYFA_BOYU`.
 *
 * Raf yalnız büro belgelerini gösterir (dış kararlarda ikinci düzey ayrım yok). Kodun okuyamadığı alan boş gelir.
 */
export function KararRafi() {
  const [suzgec, setSuzgec] = useState<Suzgec>(BOS_SUZGEC);
  const [metin, setMetin] = useState("");
  const [sayfa, setSayfa] = useState(0);
  const [okunan, setOkunan] = useState<number | null>(null);

  // Yazarken her tuşta istek atılmaz (metin araması bütün karar metinlerini tarar).
  useEffect(() => {
    const zamanlayici = setTimeout(() => setSuzgec((s) => (s.metin === metin ? s : { ...s, metin })), 400);
    return () => clearTimeout(zamanlayici);
  }, [metin]);

  const anahtar = JSON.stringify(suzgec);
  // Süzgeç değişince ilk sayfaya dönülür.
  useEffect(() => setSayfa(0), [anahtar]);

  const secenekler = useVeri((signal) => lexisApi.rafSecenekleri(signal)).veri ?? BOS_SECENEKLER;
  const { veri, hata, yukleniyor, yenile } = useVeri(
    (signal) => lexisApi.kararAra({ ...suzgec, limit: RAF_SAYFA_BOYU, offset: sayfa * RAF_SAYFA_BOYU }, signal),
    `${anahtar}:${sayfa}`,
  );

  const suzulmus = useMemo(() => JSON.stringify(suzgec) !== JSON.stringify(BOS_SUZGEC), [suzgec]);
  const sayfaSayisi = veri ? Math.max(1, Math.ceil(veri.toplam / RAF_SAYFA_BOYU)) : 1;

  const secim = (alan: "belge_turu" | "derece" | "hukum_sinifi" | "sonuc_muvekkil" | "uzmanlik" | "konu", etiket: string, degerler: string[], adlar?: Record<string, string>) => (
    <select aria-label={etiket} className={SECIM_SINIFI} value={suzgec[alan] ?? ""} onChange={(e) => setSuzgec((s) => ({ ...s, [alan]: e.target.value || null }))}>
      <option value="">{etiket}: tümü</option>
      {degerler.map((d) => (
        <option key={d} value={d}>
          {adlar ? rafAdi(adlar, d) : d}
        </option>
      ))}
    </select>
  );

  return (
    <div data-testid="lexis-karar-rafi">
      <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="lexis-raf-suzgecleri">
        <label className="relative block min-w-[220px] flex-1 max-w-md">
          <span className="sr-only">Kararlarda ara</span>
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" aria-hidden="true" />
          <input
            type="search"
            value={metin}
            onChange={(e) => setMetin(e.target.value)}
            placeholder="Mahkeme, esas no ya da karar metni…"
            className="w-full h-8 pl-8 pr-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[12.5px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none"
          />
        </label>
        {secim("hukum_sinifi", "Kararın bütünü", secenekler.hukum_sinifi, HUKUM_SINIFI_ADLARI)}
        {secim("sonuc_muvekkil", "Müvekkil yönünden", secenekler.sonuc_muvekkil, HUKUM_SINIFI_ADLARI)}
        {secim("derece", "Derece", secenekler.derece, DERECE_ADLARI)}
        {secim("konu", "Gerekçe konusu", Object.keys(KONU_ADLARI), KONU_ADLARI)}
        {secim("uzmanlik", "Uzmanlık", secenekler.uzmanlik)}
        {secim("belge_turu", "Belge", secenekler.belge_turu, BELGE_TURU_RAF_ADLARI)}
        <label className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--fg-muted)]">
          <input type="checkbox" className="accent-[var(--brand)]" checked={suzgec.yalniz_kartli} onChange={(e) => setSuzgec((s) => ({ ...s, yalniz_kartli: e.target.checked }))} />
          Yalnız karta bağlı
        </label>
        {(suzulmus || metin) && (
          <button
            type="button"
            onClick={() => {
              setMetin("");
              setSuzgec(BOS_SUZGEC);
            }}
            className={`text-[12px] ${BAGLANTI_SINIFI}`}
          >
            Süzgeçleri temizle
          </button>
        )}
      </div>

      <div className="border border-[var(--border)] bg-[var(--bg)]">
        {hata ? (
          <div className="p-4">
            <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
          </div>
        ) : !veri ? (
          <TableSkeleton rows={8} columns={7} label="Karar rafı yükleniyor…" />
        ) : veri.kararlar.length === 0 ? (
          <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Bu süzgeçlere uyan karar yok.</p>
        ) : (
          <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className={TH_SINIFI}>Mahkeme</th>
                  <th className={TH_SINIFI}>Esas / Karar</th>
                  <th className={TH_SINIFI}>Tarih</th>
                  <th className={TH_SINIFI}>Kararın bütünü</th>
                  <th className={TH_SINIFI}>Müvekkil yönünden</th>
                  <th className={TH_SINIFI}>Talep → hükmedilen</th>
                  <th className={TH_SINIFI}>Gerekçe konuları</th>
                  <th className={TH_SINIFI}>Kart</th>
                </tr>
              </thead>
              <tbody>
                {veri.kararlar.map((k) => {
                  const talep = tutarListesi([...k.talep_maddi, ...k.talep_manevi]);
                  const hukmedilen = tutarListesi([...k.hukmedilen_maddi, ...k.hukmedilen_manevi, ...k.hukmedilen_birlesik]);
                  return (
                    <tr key={k.id} data-testid="lexis-raf-satiri" className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg-elevated)] transition-colors">
                      <td className={`${TD_SINIFI} min-w-[220px]`}>
                        <button type="button" onClick={() => setOkunan(k.id)} className={`text-left ${BAGLANTI_SINIFI}`}>
                          {k.mahkeme ?? rafAdi(BELGE_TURU_RAF_ADLARI, k.belge_turu)}
                        </button>
                        <span className="block text-[12px] text-[var(--fg-muted)]">{[k.derece && rafAdi(DERECE_ADLARI, k.derece), k.uzmanlik].filter(Boolean).join(" · ")}</span>
                      </td>
                      <td className={`${TD_SINIFI} font-mono text-[11.5px] whitespace-nowrap`}>{kararNumarasi(k) ?? "—"}</td>
                      <td className={`${TD_SINIFI} font-mono text-[11.5px] tabular-nums whitespace-nowrap`}>{k.karar_tarihi ? tarihYaz(k.karar_tarihi) : "—"}</td>
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        {k.hukum_sinifi ? <Rozet ton={hukumTonu(k.hukum_sinifi)}>{rafAdi(HUKUM_SINIFI_ADLARI, k.hukum_sinifi)}</Rozet> : "—"}
                      </td>
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        {k.sonuc_muvekkil ? <Rozet ton={hukumTonu(k.sonuc_muvekkil)}>{rafAdi(HUKUM_SINIFI_ADLARI, k.sonuc_muvekkil)}</Rozet> : "—"}
                        {k.sonuc_iliskisi && k.sonuc_iliskisi !== "AYNI" && (
                          <span className="block mt-0.5 text-[11px] text-[var(--fg-subtle)]">{k.sonuc_iliskisi === "KARMA" ? "karma hüküm" : "incele"}</span>
                        )}
                      </td>
                      <td className={`${TD_SINIFI} font-mono text-[11.5px] tabular-nums`}>
                        {talep || hukmedilen ? (
                          <>
                            <span className="block text-[var(--fg-muted)]">{talep ?? "—"}</span>
                            <span className="block">→ {hukmedilen ?? "—"}</span>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className={`${TD_SINIFI} text-[12px] text-[var(--fg-muted)]`}>
                        {Object.keys(k.konular)
                          .sort((a, b) => k.konular[b] - k.konular[a])
                          .map((kod) => `${rafAdi(KONU_ADLARI, kod).toLocaleLowerCase("tr")} ${k.konular[kod]}`)
                          .join(" · ") || "—"}
                      </td>
                      <td className={`${TD_SINIFI} whitespace-nowrap`}>
                        {k.kart_id !== null ? (
                          // Örnek kipte kart uydurmadır: bağlantı verilmez.
                          lexisApi.kalici ? (
                            <Link to={`/cases/${k.kart_id}`} className={`font-mono text-[11.5px] ${BAGLANTI_SINIFI}`}>
                              #{k.kart_id}
                            </Link>
                          ) : (
                            <span className="font-mono text-[11.5px]">#{k.kart_id}</span>
                          )
                        ) : (
                          <span className="text-[12px] text-[var(--fg-subtle)]">bağsız</span>
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

      {veri && veri.toplam > 0 && (
        <div className="flex items-center justify-between gap-3 mt-2 text-[12px] text-[var(--fg-muted)]" data-testid="lexis-raf-sayfalama">
          <span className="font-mono tabular-nums">
            {veri.toplam.toLocaleString("tr-TR")} karar · sayfa {sayfa + 1}/{sayfaSayisi}
          </span>
          <span className="inline-flex gap-3">
            <button type="button" disabled={sayfa === 0 || yukleniyor} onClick={() => setSayfa((s) => s - 1)} className={BAGLANTI_SINIFI}>
              Önceki
            </button>
            <button type="button" disabled={sayfa + 1 >= sayfaSayisi || yukleniyor} onClick={() => setSayfa((s) => s + 1)} className={BAGLANTI_SINIFI}>
              Sonraki
            </button>
          </span>
        </div>
      )}

      <KararOkuyucu kararId={okunan} onKapat={() => setOkunan(null)} />
    </div>
  );
}
