import { useState } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { CardListSkeleton } from "@/components/skeletons/Skeletons";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { FlowButton } from "@/components/flow/primitives";
import { useConfirm } from "@/hooks/useConfirm";
import { ORNEK_VERI, lexisApi } from "@/lib/lexisApi";
import { tarihYaz } from "@/lib/lexisMetin";
import { ISKELET_BOLUMLERI, type LexisSirket, type SirketProfili, type YazilabilirIskelet } from "@/types/lexis";
import { MuallakKriterTablosu } from "./MuallakKriterTablosu";
import { BolgeBasligi, OtoMetinAlani } from "./ortak";
import { useVeri } from "./useVeri";
import { SECIM_SINIFI, hataMetni } from "./yardimcilar";

/** Sabit metin anahtarlarının görünen adları; tanınmayan anahtar olduğu gibi gösterilir. */
const SABIT_METIN_ADLARI: Record<string, string> = {
  giris_cumlesi: "Değerlendirme giriş cümlesi",
  saygi_cumlesi: "Kapanış (saygı) cümlesi",
  police_genel_sart: "Poliçe genel şart paragrafı",
};

const ISKELETLER = Object.keys(ISKELET_BOLUMLERI) as YazilabilirIskelet[];
const ayni = (a: SirketProfili, b: SirketProfili) => JSON.stringify(a) === JSON.stringify(b);

/**
 * "Şirketler" sekmesi: sigorta şirketi başına rapor profili — ana ve ek raporun iskeleti, rapora aynen giren sabit
 * metinler, kriter metni ve muallak kriter tablosu. Soldan şirket seçilir; kaydedilmemiş değişiklik varken başka
 * şirkete geçiş onay ister. Önizlemede kayıt bellekte kalır (sayfa yenilenince sıfırlanır).
 */
export function SirketProfilleri() {
  const confirm = useConfirm();
  const { veri, hata, yukleniyor, yenile, setVeri } = useVeri((signal) => lexisApi.profiller(signal));
  const [seciliKod, setSeciliKod] = useState<LexisSirket | null>(null);
  const [taslak, setTaslak] = useState<SirketProfili | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const kayitli = veri?.find((p) => p.sirket_kodu === (seciliKod ?? veri[0]?.sirket_kodu)) ?? null;
  // Seçili şirketin düzenlenen kopyası; şirket değişince ya da kayıt sonrası kayıtlı hâlden yeniden kurulur.
  const duzenlenen = taslak && kayitli && taslak.sirket_kodu === kayitli.sirket_kodu ? taslak : kayitli;
  const degisti = !!(duzenlenen && kayitli && !ayni(duzenlenen, kayitli));

  const sirketSec = async (kod: LexisSirket) => {
    if (kod === kayitli?.sirket_kodu) return;
    if (degisti && !(await confirm({ tone: "warning", title: "Kaydedilmemiş değişiklik var", body: "Başka şirkete geçerseniz bu profildeki değişiklikler kaybolur.", confirmLabel: "Vazgeç ve geç" }))) {
      return;
    }
    setTaslak(null);
    setSeciliKod(kod);
  };

  const degistir = (yama: Partial<SirketProfili>) => duzenlenen && setTaslak({ ...duzenlenen, ...yama });

  const kaydet = async () => {
    if (!duzenlenen) return;
    setKaydediliyor(true);
    try {
      const kayit = await lexisApi.profilKaydet(duzenlenen);
      setVeri((onceki) => onceki?.map((p) => (p.sirket_kodu === kayit.sirket_kodu ? kayit : p)) ?? null);
      setTaslak(null);
      toast.success("Profil kaydedildi", ORNEK_VERI ? { description: "Önizleme: sayfa yenilenince sıfırlanır." } : undefined);
    } catch (e) {
      toast.error("Profil kaydedilemedi", { description: hataMetni(e) });
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <div data-testid="lexis-sirketler" className="h-full overflow-y-auto px-3 md:px-6 py-5">
      <h2 className="font-display text-[19px] font-medium text-[var(--fg)] mb-3">Şirket profilleri</h2>

      {hata ? (
        <DataErrorBanner description={hata} onRetry={yenile} isRetrying={yukleniyor} />
      ) : !veri ? (
        <CardListSkeleton count={4} label="Profiller yükleniyor…" />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)] items-start">
          <nav aria-label="Şirketler" className="flex lg:grid gap-1 overflow-x-auto">
            {veri.map((p) => {
              const secili = p.sirket_kodu === kayitli?.sirket_kodu;
              return (
                <button
                  key={p.sirket_kodu}
                  type="button"
                  aria-current={secili ? "true" : undefined}
                  onClick={() => void sirketSec(p.sirket_kodu)}
                  className={`shrink-0 text-left px-3 py-2 border text-[13px] transition-colors ${
                    secili ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--fg)] font-medium" : "border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] hover:text-[var(--fg)]"
                  }`}
                >
                  {p.ad}
                  <span className="block font-mono text-[10.5px] font-normal text-[var(--fg-subtle)]">
                    {p.iskelet_ana} · {p.muallak_tablosu.length} kriter satırı
                  </span>
                </button>
              );
            })}
          </nav>

          {duzenlenen && (
            <form
              aria-label={`${duzenlenen.ad} profili`}
              className="grid gap-6 min-w-0"
              onSubmit={(e) => {
                e.preventDefault();
                void kaydet();
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-display text-[17px] font-medium text-[var(--fg)]">{duzenlenen.ad}</div>
                  <div className="text-[12px] text-[var(--fg-subtle)]">Son güncelleme {tarihYaz(duzenlenen.guncelleme)}</div>
                </div>
                <FlowButton type="submit" size="sm" disabled={!degisti || kaydediliyor}>
                  <Save className="w-3.5 h-3.5" aria-hidden="true" />
                  {degisti ? "Kaydet" : "Kaydedildi"}
                </FlowButton>
              </div>

              <section className="grid gap-2">
                <BolgeBasligi>İskelet</BolgeBasligi>
                <div className="grid sm:grid-cols-2 gap-3 max-w-xl">
                  {(
                    [
                      ["iskelet_ana", "Ana rapor"],
                      ["iskelet_ek", "Ek rapor"],
                    ] as const
                  ).map(([alan, ad]) => (
                    <label key={alan} className="grid gap-1">
                      <span className="text-[11px] text-[var(--fg-subtle)]">{ad}</span>
                      <select className={`${SECIM_SINIFI} w-full`} value={duzenlenen[alan]} onChange={(e) => degistir({ [alan]: e.target.value as YazilabilirIskelet })}>
                        {ISKELETLER.map((kod) => (
                          <option key={kod} value={kod}>
                            {kod} — {ISKELET_BOLUMLERI[kod].length} bölüm
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <p className="text-[12px] leading-[1.5] text-[var(--fg-muted)]">
                  Ana raporun bölümleri: {ISKELET_BOLUMLERI[duzenlenen.iskelet_ana].map((b) => b.baslik).join(" · ")}
                </p>
              </section>

              <section className="grid gap-2">
                <BolgeBasligi>Sabit metinler</BolgeBasligi>
                {Object.keys(duzenlenen.sabit_metinler).length === 0 && <p className="text-[12.5px] text-[var(--fg-muted)]">Bu şirket için sabit metin tanımlı değil.</p>}
                {Object.entries(duzenlenen.sabit_metinler).map(([anahtar, metin]) => (
                  <label key={anahtar} className="grid gap-0.5">
                    <span className="text-[11px] text-[var(--fg-subtle)]">{SABIT_METIN_ADLARI[anahtar] ?? anahtar}</span>
                    <OtoMetinAlani
                      value={metin}
                      className="mx-0 border-[var(--border)] bg-[var(--bg)]"
                      onChange={(e) => degistir({ sabit_metinler: { ...duzenlenen.sabit_metinler, [anahtar]: e.target.value } })}
                    />
                  </label>
                ))}
              </section>

              <section className="grid gap-2">
                <BolgeBasligi>Muallak kriterleri</BolgeBasligi>
                <label className="grid gap-0.5">
                  <span className="text-[11px] text-[var(--fg-subtle)]">Kriter metni (şirketin yazılı kuralı)</span>
                  <OtoMetinAlani
                    value={duzenlenen.kriter_metni}
                    placeholder="Şirketin muallak kriteri yazılı değil."
                    className="mx-0 border-[var(--border)] bg-[var(--bg)]"
                    onChange={(e) => degistir({ kriter_metni: e.target.value })}
                  />
                </label>
                <MuallakKriterTablosu satirlar={duzenlenen.muallak_tablosu} onDegistir={(muallak_tablosu) => degistir({ muallak_tablosu })} />
              </section>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
