import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { bilesenAdi } from "@/lib/lexisApi";
import { tarihYaz, tutarYaz } from "@/lib/lexisMetin";
import {
  ISKELET_BOLUMLERI,
  KUSUR_ADLARI,
  RISK_ADLARI,
  TEMINAT_ADLARI,
  type BolumKodu,
  type Emsal,
  type KutuphaneKaydi,
} from "@/types/lexis";
import { Rozet } from "./ortak";
import { raporKunyesi } from "./yardimcilar";

type EmsalOkuyucuProps = {
  /** Açık rapor; `null` diyaloğu kapatır. */
  kayit: KutuphaneKaydi | null;
  /** Dosyaya göre puanı varsa bileşen dökümü gösterilir. */
  emsal?: Emsal | null;
  onKapat: () => void;
};

/** Eski raporlarda bölüm başlığı saklanmaz; kod → okunur ad. */
const BOLUM_ADLARI: Partial<Record<BolumKodu, string>> = {
  hasar: "Hasar bilgileri",
  hastane: "Hastane",
  sulh_muallak: "Sulh ve muallak",
  iddia: "İddia",
  beyan: "Sigortalı hekim beyanı",
  police: "Poliçe",
  yargi_sureci: "Yargı süreci",
  uzman_gorusu: "Uzman / tıbbi görüş",
  ek_inceleme: "Ek inceleme",
  degerlendirme: "Değerlendirme",
};

function bolumSirasi(kayit: KutuphaneKaydi): BolumKodu[] {
  const mevcut = Object.keys(kayit.okuma.bolumler) as BolumKodu[];
  const { iskelet } = kayit.okuma;
  if (iskelet === "ESKI" || iskelet === "BILINMEYEN") return mevcut;
  const sira = ISKELET_BOLUMLERI[iskelet].map((b) => b.kod);
  return [...sira.filter((k) => mevcut.includes(k)), ...mevcut.filter((k) => !sira.includes(k))];
}

/**
 * Eski raporu okutur: künye, etiketler, (varsa) puan dökümü, MASKELİ bölüm metinleri ve anılan kararlar.
 * Kütüphanede yalnız maskeli metin durur (K4) — kişi adları `[SİGORTALI]` / `[HASTA]` yer tutucularıdır.
 */
export function EmsalOkuyucu({ kayit, emsal, onKapat }: EmsalOkuyucuProps) {
  const acik = kayit !== null;
  return (
    <Dialog open={acik} onOpenChange={(o) => !o && onKapat()}>
      {kayit && (
        <DialogContent
          className="theme-classic max-w-3xl max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none text-[var(--fg)]"
          data-testid="lexis-emsal-okuyucu"
        >
          <DialogHeader>
            <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">
              {raporKunyesi(kayit.okuma)}
              {kayit.okuma.rapor_no && <span className="ml-2 font-mono text-[12px] text-[var(--fg-subtle)]">{kayit.okuma.rapor_no}</span>}
            </DialogTitle>
            <DialogDescription className="text-[12.5px] text-[var(--fg-muted)]">
              {[
                kayit.okuma.rapor_tarihi && tarihYaz(kayit.okuma.rapor_tarihi),
                kayit.okuma.mahkeme,
                kayit.okuma.esas_no && `${kayit.okuma.esas_no} E.`,
                kayit.etiketler.uzmanlik ?? kayit.okuma.uzmanlik,
              ]
                .filter(Boolean)
                .join(" · ")}
              {" — maskeli metin"}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap gap-1.5">
            <Rozet>{KUSUR_ADLARI[kayit.etiketler.kusur_tespiti]}</Rozet>
            <Rozet>Risk: {RISK_ADLARI[kayit.etiketler.risk_duzeyi]}</Rozet>
            <Rozet>{TEMINAT_ADLARI[kayit.etiketler.teminat]}</Rozet>
            {kayit.etiketler.tibbi_islem && <Rozet>{kayit.etiketler.tibbi_islem}</Rozet>}
            {kayit.etiketler.tibbi_olay.map((o) => (
              <Rozet key={o}>{o}</Rozet>
            ))}
          </div>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-[12.5px]">
            {(
              [
                ["Talep (maddi)", kayit.okuma.talep_maddi],
                ["Talep (manevi)", kayit.okuma.talep_manevi],
                ["Muallak (maddi)", kayit.okuma.muallak_maddi],
                ["Muallak (manevi)", kayit.okuma.muallak_manevi],
              ] as const
            ).map(([etiket, tutar]) => (
              <div key={etiket}>
                <dt className="text-[var(--fg-subtle)]">{etiket}</dt>
                <dd className="font-mono tabular-nums text-[var(--fg)]">{tutar === null ? "—" : tutarYaz(tutar)}</dd>
              </div>
            ))}
          </dl>

          {emsal && (
            <section aria-label="Puan dökümü" className="grid gap-1.5">
              <h4 className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)]">
                Neden bu rapor · puan {emsal.puan.toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              </h4>
              <ul className="grid gap-1">
                {emsal.bilesenler
                  .filter((b) => b.benzerlik > 0)
                  .sort((a, b) => b.agirlik * b.benzerlik - a.agirlik * a.benzerlik)
                  .map((b) => (
                    <li key={b.ad} className="grid grid-cols-[88px_minmax(0,1fr)_44px] items-center gap-2 text-[12px]">
                      <span className="text-[var(--fg-muted)]">{bilesenAdi(b.ad)}</span>
                      <span className="min-w-0">
                        <span className="block h-1.5 bg-[var(--bg-sunken)]">
                          <span className="block h-full bg-brand-solid" style={{ width: `${Math.round(b.benzerlik * 100)}%` }} />
                        </span>
                        {b.ortak.length > 0 && <span className="block mt-0.5 text-[11.5px] text-[var(--fg-subtle)] truncate">{b.ortak.join(", ")}</span>}
                      </span>
                      <span className="font-mono tabular-nums text-right text-[var(--fg)]">
                        +{(b.agirlik * b.benzerlik).toLocaleString("tr-TR", { maximumFractionDigits: 1 })}
                      </span>
                    </li>
                  ))}
              </ul>
            </section>
          )}

          <div className="grid gap-4">
            {bolumSirasi(kayit).map((kod) => (
              <section key={kod} aria-label={BOLUM_ADLARI[kod] ?? kod}>
                <h4 className="font-display text-[14px] font-medium text-[var(--fg)] mb-1">{BOLUM_ADLARI[kod] ?? kod}</h4>
                {(kayit.okuma.bolumler[kod] ?? "").split("\n").map((satir, i) => (
                  <p key={i} className="text-[13px] leading-[1.65] text-[var(--fg)] mb-1.5">
                    {satir}
                  </p>
                ))}
              </section>
            ))}
          </div>

          {kayit.okuma.kararlar.length > 0 && (
            <section aria-label="Anılan kararlar" className="grid gap-1">
              <h4 className="font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)]">Anılan kararlar</h4>
              <ul className="text-[12.5px] text-[var(--fg)]">
                {kayit.okuma.kararlar.map((k) => (
                  <li key={`${k.esas_no}-${k.karar_no}`}>
                    {[k.merci, `${k.esas_no} E., ${k.karar_no} K.`, k.tarih && tarihYaz(k.tarih)].filter(Boolean).join(" · ")}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </DialogContent>
      )}
    </Dialog>
  );
}
