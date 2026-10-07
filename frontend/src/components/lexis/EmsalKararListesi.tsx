import { BookOpen, Scale, X } from "lucide-react";
import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import { HUKUM_SINIFI_ADLARI, gosterilecekOneriler, rafAdi, type EmsalOnerisi, type RafKarari } from "@/types/lexis";
import { BolgeBasligi, BosDurum, Rozet, SimgeDugmesi } from "./ortak";
import { BAGLANTI_SINIFI, hukumTonu, kararKunyesi, type RozetTonu } from "./yardimcilar";

/** Puan rozetinin tonu: ≥ 75 güçlü, ≥ 50 orta, altı zayıf. */
const puanTonu = (puan: number): RozetTonu => (puan >= 75 ? "ok" : puan >= 50 ? "caution" : "muted");

const PUAN_SINIFLARI: Record<RozetTonu, string> = {
  ok: "text-tone-ok border-tone-ok/40 bg-tone-ok/10",
  caution: "text-tone-caution border-tone-caution/40 bg-tone-caution/10",
  danger: "text-tone-danger border-tone-danger/40 bg-tone-danger/10",
  muted: "text-[var(--fg-muted)] border-[var(--border-strong)] bg-[var(--bg-sunken)]",
};

type EmsalKararListesiProps = {
  oneriler: readonly EmsalOnerisi[];
  secili: ReadonlySet<number>;
  onSec: (id: number, secili: boolean) => void;
  /** Taslakta zaten olan kararlar: işaretli ve kilitli görünür. */
  mevcut?: ReadonlySet<number>;
  /** "Kararı aç" — `KararOkuyucu`'yu çağıran açar (bu bileşen yalnız kimliği verir). */
  onKararAc: (id: number) => void;
  kilitli?: boolean;
};

/**
 * Emsal ajanının sıralı, gerekçeli sonuç listesi: puan rozeti, künye (mahkeme · E/K · tarih) ve hüküm rozetleri,
 * "neden bu karar" gerekçesi, kaynak kararda birebir bulunmuş alıntı ("kaynakta doğrulandı"), fark, aynı kart ve
 * önbellek işaretleri, denetçinin olgu uyarıları. Satır işaretlenip taslağa alınır (yazıma GİRMEZ, K28); "Kararı aç"
 * kararın tam metnini okuyucuda açar.
 */
export function EmsalKararListesi({ oneriler, secili, onSec, mevcut, onKararAc, kilitli = false }: EmsalKararListesiProps) {
  const gorunen = gosterilecekOneriler(oneriler);
  if (gorunen.length === 0) return <BosDurum>Denetimden geçen emsal önerisi yok. Belge için aday bulunamadı ya da alıntılar kaynak kararda doğrulanamadı.</BosDurum>;
  return (
    <ol data-testid="lexis-emsal-oneriler" className="grid gap-2">
      {gorunen.map((o, i) => {
        const kunye = kararKunyesi(o);
        const taslakta = mevcut?.has(o.id) ?? false;
        return (
          <li key={o.id} data-testid="lexis-emsal-oneri" data-karar-id={o.id} className="grid grid-cols-[auto_auto_minmax(0,1fr)] gap-x-3 border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5">
            <input
              type="checkbox"
              className="mt-[5px] accent-[var(--brand)]"
              aria-label={`Taslağa al: ${kunye}`}
              checked={taslakta || secili.has(o.id)}
              disabled={kilitli || taslakta}
              onChange={(e) => onSec(o.id, e.target.checked)}
            />
            <div className={`grid place-items-center w-12 h-10 border ${PUAN_SINIFLARI[puanTonu(o.puan)]}`} title="Okuyucu puanı (0-100)">
              <span className="font-mono text-[16px] font-semibold tabular-nums leading-none">{Math.round(o.puan)}</span>
              <span className="font-mono text-[9px] tracking-[0.1em] leading-none">/100</span>
            </div>
            <div className="min-w-0 grid gap-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-mono text-[10.5px] text-[var(--fg-subtle)] tabular-nums">{String(i + 1).padStart(2, "0")}</span>
                <button type="button" onClick={() => onKararAc(o.id)} className={`text-left text-[13px] font-medium leading-[1.4] ${BAGLANTI_SINIFI}`}>
                  {kunye}
                </button>
                {o.hukum_sinifi && (
                  <Rozet ton={hukumTonu(o.hukum_sinifi)} title="Kararın bütünü (hükümden)">
                    {rafAdi(HUKUM_SINIFI_ADLARI, o.hukum_sinifi)}
                  </Rozet>
                )}
                {o.sonuc_muvekkil && o.sonuc_muvekkil !== o.hukum_sinifi && (
                  <Rozet ton={hukumTonu(o.sonuc_muvekkil)} title="Müvekkil yönünden (HUKDOK etiketi)">
                    müvekkil: {rafAdi(HUKUM_SINIFI_ADLARI, o.sonuc_muvekkil)}
                  </Rozet>
                )}
                {o.ayni_kart && (
                  <Rozet ton="caution" title="Belgenin kendi kartının kararı: emsal değil, dosyanın zinciri">
                    aynı kart
                  </Rozet>
                )}
                {o.kaynak === "onbellek" && <Rozet title="Okuma önbellekten geldi; model yeniden çağrılmadı">önbellekten</Rozet>}
                {taslakta && <Rozet ton="ok">taslakta</Rozet>}
              </div>
              <p className="text-[12.5px] leading-[1.5] text-[var(--fg)]">{o.gerekce || "Gerekçe yazılmadı."}</p>
              <blockquote className="border-l-2 border-[var(--brand)] pl-2.5 grid gap-1">
                <p className="text-[12.5px] leading-[1.5] italic text-[var(--fg-muted)]">“{o.alinti}”</p>
                <span>
                  <Rozet ton="ok" title="Alıntı kaynak kararın metninde birebir bulundu (kod denetçisi)">
                    kaynakta doğrulandı
                  </Rozet>
                </span>
              </blockquote>
              {o.fark && (
                <p className="text-[12px] leading-[1.45] text-[var(--fg-muted)]">
                  <span className="text-[var(--fg-subtle)]">Fark: </span>
                  {o.fark}
                </p>
              )}
              {o.denetim_uyarilari.length > 0 && (
                <ul className="grid gap-0.5 text-[12px] leading-[1.45] text-tone-caution" aria-label="Denetim uyarıları">
                  {o.denetim_uyarilari.map((u, j) => (
                    <li key={j}>⚠ {u}</li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

type TaslakEmsalListesiProps = {
  kararlar: RafKarari[];
  yukleniyor: boolean;
  hata: string | null;
  onOku: (id: number) => void;
  onCikar: (id: number) => void;
  /** "Bu dosyaya emsal bul" — verilmezse başlık düğmesi çizilmez. */
  onBul?: () => void;
  kilitli?: boolean;
};

/**
 * Tezgâhtaki "Emsal kararlar" bölgesi: taslağa alınan büro kararları (`LexisTaslak.emsal_kararlar`) künyesiyle;
 * kaldırılabilir, okuyucuda açılır. Yazım girdisi olan "Kararlar" listesinden AYRIDIR (K28): buradakiler modele
 * gitmez, Word'de künye satırı olur.
 */
export function TaslakEmsalListesi({ kararlar, yukleniyor, hata, onOku, onCikar, onBul, kilitli = false }: TaslakEmsalListesiProps) {
  return (
    <section aria-label="Emsal kararlar" data-testid="lexis-emsal-kararlar" className="grid gap-2">
      <BolgeBasligi
        sag={
          <>
            {kararlar.length > 0 && <span className="font-mono text-[10.5px] text-[var(--fg-subtle)] tabular-nums">{kararlar.length}</span>}
            {onBul && (
              <SimgeDugmesi etiket="Bu dosyaya emsal bul" onClick={onBul} disabled={kilitli}>
                <Scale className="w-3.5 h-3.5" />
              </SimgeDugmesi>
            )}
          </>
        }
      >
        Emsal kararlar
      </BolgeBasligi>
      {hata && (
        <p role="alert" className="text-[12.5px] text-tone-danger">
          {hata}
        </p>
      )}
      {yukleniyor && <LineListSkeleton count={2} label="Emsal kararlar yükleniyor…" />}
      {!yukleniyor && kararlar.length === 0 && (
        <BosDurum>Emsal karar seçilmedi. Belge satırındaki terazi düğmesiyle büro arşivinde emsal aratın; seçilenler yazıma girmez, Word'de künye satırı olur.</BosDurum>
      )}
      <ul className="grid gap-1">
        {kararlar.map((k) => (
          <li key={k.id} className="flex items-start gap-2 px-2 py-1.5 -mx-2 rounded-[3px] hover:bg-[var(--bg-sunken)]">
            <span className="min-w-0 flex-1 grid gap-0.5">
              <button type="button" onClick={() => onOku(k.id)} className={`text-left text-[12.5px] leading-[1.4] ${BAGLANTI_SINIFI}`}>
                {kararKunyesi(k)}
              </button>
              {k.hukum_sinifi && (
                <span>
                  <Rozet ton={hukumTonu(k.hukum_sinifi)} title="Kararın bütünü (hükümden)">
                    {rafAdi(HUKUM_SINIFI_ADLARI, k.hukum_sinifi)}
                  </Rozet>
                </span>
              )}
            </span>
            <span className="shrink-0 flex">
              <SimgeDugmesi etiket={`Emsal kararı oku: ${kararKunyesi(k)}`} onClick={() => onOku(k.id)}>
                <BookOpen className="w-3.5 h-3.5" />
              </SimgeDugmesi>
              <SimgeDugmesi etiket={`Emsal kararı çıkar: ${kararKunyesi(k)}`} onClick={() => onCikar(k.id)} disabled={kilitli}>
                <X className="w-3.5 h-3.5" />
              </SimgeDugmesi>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
