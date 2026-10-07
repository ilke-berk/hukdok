import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import { tarihYaz } from "@/lib/lexisMetin";
import { BELGE_TURU_RAF_ADLARI, HUKUM_SINIFI_ADLARI, rafAdi, type RafKarari, type YazimDurumu } from "@/types/lexis";
import { BolgeBasligi, BosDurum, Rozet } from "./ortak";
import { BAGLANTI_SINIFI, hukumTonu, kararNumarasi, tutarListesi } from "./yardimcilar";

type KararListesiProps = {
  kararlar: RafKarari[];
  yukleniyor: boolean;
  hata: string | null;
  /** Kararlardan yazım açıksa satırlar işaretlenebilir; kapalıyken (ve örnek kipte) liste yalnız okunur. */
  yazim: YazimDurumu | null;
  secili: ReadonlySet<number>;
  onSec: (id: number, secili: boolean) => void;
  onOku: (id: number) => void;
  kilitli?: boolean;
};

const KAPALI_NOTLARI: Record<string, string> = {
  kapali: "Kararlardan yazım bu kurulumda kapalı: taslak iskelet olarak gelir, kararları buradan okuyabilirsiniz.",
  anahtar_yok: "Kararlardan yazım için servisin model anahtarı tanımlı değil: taslak iskelet olarak gelir.",
  paket_yok: "Kararlardan yazım için servis imajında model paketi yok: taslak iskelet olarak gelir.",
};

/**
 * Dava kartına bağlı kararlar (servisin karar veritabanından): mahkeme, esas / karar no, tarih ve iki sonuç alanı —
 * kararın bütünü (hükümden) ve müvekkil yönünden (HUKDOK etiketi). Satır kararı okuyucuda açar. Yazım açıksa
 * işaretli kararların MASKELİ metni taslak yazımında modele gider (onay kutusunda ayrıca gösterilir, K4).
 */
export function KararListesi({ kararlar, yukleniyor, hata, yazim, secili, onSec, onOku, kilitli = false }: KararListesiProps) {
  const yazimAcik = yazim?.acik === true;
  const seciliSayisi = kararlar.filter((k) => secili.has(k.id)).length;

  return (
    <section aria-label="Kararlar" data-testid="lexis-kararlar" className="grid gap-2">
      <BolgeBasligi
        sag={
          kararlar.length > 0 ? (
            <span className="font-mono text-[10.5px] text-[var(--fg-subtle)] tabular-nums">{yazimAcik ? `${seciliSayisi}/${kararlar.length} seçili` : kararlar.length}</span>
          ) : undefined
        }
      >
        Kararlar
      </BolgeBasligi>
      {yukleniyor && <LineListSkeleton count={2} label="Kararlar yükleniyor…" />}
      {hata && (
        <p role="alert" className="text-[12.5px] text-tone-danger">
          {hata}
        </p>
      )}
      {!yukleniyor && !hata && kararlar.length === 0 && <BosDurum>Bu dava kartına bağlı karar yok.</BosDurum>}
      <ul className="grid gap-1">
        {kararlar.map((k) => {
          const hukmedilen = tutarListesi([...k.hukmedilen_maddi, ...k.hukmedilen_manevi, ...k.hukmedilen_birlesik]);
          return (
            <li key={k.id} className="flex items-start gap-2.5 px-2 py-1.5 -mx-2 rounded-[3px] hover:bg-[var(--bg-sunken)]">
              {yazimAcik && (
                <input
                  type="checkbox"
                  className="mt-[3px] accent-[var(--brand)]"
                  aria-label={`Yazıma al: ${k.mahkeme ?? "karar"} ${kararNumarasi(k) ?? ""}`}
                  checked={secili.has(k.id)}
                  disabled={kilitli}
                  onChange={(e) => onSec(k.id, e.target.checked)}
                />
              )}
              <span className="min-w-0 grid gap-0.5">
                <button type="button" onClick={() => onOku(k.id)} className={`text-left text-[13px] leading-[1.4] ${BAGLANTI_SINIFI}`}>
                  {k.mahkeme ?? rafAdi(BELGE_TURU_RAF_ADLARI, k.belge_turu)}
                </button>
                <span className="block text-[11.5px] text-[var(--fg-subtle)]">
                  {[kararNumarasi(k), k.karar_tarihi && tarihYaz(k.karar_tarihi), k.belge_turu !== "karar" && rafAdi(BELGE_TURU_RAF_ADLARI, k.belge_turu)].filter(Boolean).join(" · ") || "künye yok"}
                </span>
                <span className="flex flex-wrap items-center gap-1">
                  {k.hukum_sinifi && (
                    <Rozet ton={hukumTonu(k.hukum_sinifi)} title="Kararın bütünü (hükümden)">
                      {rafAdi(HUKUM_SINIFI_ADLARI, k.hukum_sinifi)}
                    </Rozet>
                  )}
                  {k.sonuc_muvekkil && k.sonuc_muvekkil !== k.hukum_sinifi && (
                    <Rozet ton={hukumTonu(k.sonuc_muvekkil)} title="Müvekkil yönünden (HUKDOK etiketi)">
                      müvekkil: {rafAdi(HUKUM_SINIFI_ADLARI, k.sonuc_muvekkil)}
                    </Rozet>
                  )}
                  {hukmedilen && <span className="font-mono text-[11px] tabular-nums text-[var(--fg-muted)]">{hukmedilen}</span>}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {kararlar.length > 0 && yazim && !yazimAcik && yazim.neden && KAPALI_NOTLARI[yazim.neden] && (
        <p data-testid="lexis-yazim-kapali" className="text-[12px] leading-[1.5] text-[var(--fg-muted)]">
          {KAPALI_NOTLARI[yazim.neden]}
        </p>
      )}
    </section>
  );
}
