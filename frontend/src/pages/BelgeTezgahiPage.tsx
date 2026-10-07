import { AlertCircle, FileStack, PenLine, X } from "lucide-react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { DosyaListesi } from "@/components/pdf/DosyaListesi";
import { IslemPaneli } from "@/components/pdf/IslemPaneli";
import { PdfYukleyici } from "@/components/pdf/PdfYukleyici";
import { SayfaIzgarasi } from "@/components/pdf/SayfaIzgarasi";
import { usePdfTezgah } from "@/components/pdf/usePdfTezgah";

/**
 * `/belge-tezgahi` — Belge tezgâhı (G270, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §2-§3, K1/K2/K8).
 * Giriş yapan HER kullanıcı (yönetici kısıtı yok; rota `ProtectedRoute > ShellLayout`). İki yol çipi: "Düzenle (PDF)"
 * bu sürüm; "Yaz (Word)" G285 ile açılır (şimdilik kapalı).
 *
 * PDF tezgâhı üç bölge: sol `DosyaListesi` (+ yükleyici), orta `<section data-slot="sayfalar">` (G271: seçili dosyanın
 * `SayfaIzgarasi`; dosya yokken boş), sağ `IslemPaneli`. Çalışma dosyaları yalnız bu oturumdadır — sayfa yenilenince liste
 * gider, sunucu 1 saat sonra siler (K2). Sayfa `max-w` koymaz (tam genişlik kuralı). Default export: rota `React.lazy`.
 */
export default function BelgeTezgahiPage() {
  useSetPageTitle("Belge tezgâhı", ["Araçlar", "Belge tezgâhı"]);
  const tezgah = usePdfTezgah();

  return (
    <div data-testid="belge-tezgahi-sayfasi" className="flex flex-col gap-5 w-full min-w-0">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">Araçlar · Belge tezgâhı</p>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">Belge tezgâhı</h1>
        </div>
        <div role="group" aria-label="Çalışma yolu" className="flex items-center gap-1.5">
          <span
            data-testid="yol-pdf"
            aria-current="true"
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--brand)] bg-[var(--brand-soft)] px-3 py-1 font-mono text-[11px] tracking-[0.06em] uppercase text-[var(--brand)] font-semibold"
          >
            <FileStack className="w-3.5 h-3.5" />
            Düzenle (PDF)
          </span>
          <button
            type="button"
            data-testid="yol-word"
            disabled
            title="Sonraki sürümde: Word taslağı yazma ve kesinleştirme"
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-3 py-1 font-mono text-[11px] tracking-[0.06em] uppercase text-[var(--fg-subtle)] disabled:cursor-not-allowed"
          >
            <PenLine className="w-3.5 h-3.5" />
            Yaz (Word)
            <span className="normal-case tracking-normal font-sans text-[10px]">· sonraki sürüm</span>
          </button>
        </div>
      </header>

      <p data-testid="ttl-bilgisi" className="text-[12px] text-[var(--fg-muted)] -mt-2">
        Dosyalar yalnız bu sekmede durur ve sunucudan 1 saat sonra silinir; bitirince indirin ya da karta bağlayın.
      </p>

      {tezgah.hata && (
        <div
          role="alert"
          data-testid="tezgah-hatasi"
          className="flex items-start gap-2 rounded-[3px] border border-[rgb(var(--tone-danger-rgb))] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] text-[var(--fg)]"
        >
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-[rgb(var(--tone-danger-rgb))]" />
          <span className="flex-1">{tezgah.hata}</span>
          <button type="button" aria-label="Hatayı kapat" onClick={tezgah.hatayiKapat} className="text-[var(--fg-subtle)] hover:text-[var(--fg)]">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)_340px] items-start">
        <aside aria-label="Dosyalar" className="flex flex-col gap-3 min-w-0">
          <PdfYukleyici
            onDosyalar={tezgah.yukleHepsini}
            yuklemeler={tezgah.yuklemeler}
            yukleniyor={tezgah.yukleniyor}
            onTemizle={tezgah.yuklemeleriTemizle}
          />
          <DosyaListesi
            dosyalar={tezgah.dosyalar}
            seciliId={tezgah.seciliId}
            isaretliler={tezgah.isaretliler}
            onSec={tezgah.sec}
            onIsaretle={tezgah.isaretle}
            onKaldir={tezgah.listedenKaldir}
            onTasi={tezgah.tasi}
          />
        </aside>

        {/* G271: seçili dosyanın sayfa ızgarası (önizleme, sürükle-sırala, döndür, sil, aralık seçimi); G272 çizim katmanı. */}
        <section
          data-slot="sayfalar"
          aria-label="Sayfalar"
          className={[
            "min-h-[320px] rounded-[3px] border bg-[var(--bg-elevated)]",
            tezgah.secili && tezgah.sayfaDuzeni ? "border-[var(--border)]" : "border-dashed border-[var(--border)]",
          ].join(" ")}
        >
          {tezgah.secili && tezgah.sayfaDuzeni && (
            <SayfaIzgarasi
              key={tezgah.secili.id}
              dosya={tezgah.secili}
              duzen={tezgah.sayfaDuzeni}
              degisiklikVar={tezgah.sayfaDegisikligi}
              uygulaniyor={tezgah.surenIslem === "sayfa_duzenle"}
              onTasi={tezgah.sayfaTasi}
              onDondur={tezgah.sayfaDondur}
              onSil={tezgah.sayfaSilToggle}
              onSec={tezgah.sayfaSec}
              onHepsiniSec={tezgah.sayfalariSec}
              onSifirla={tezgah.sayfaDuzeniniSifirla}
              onUygula={() => void tezgah.sayfaDuzeniniUygula()}
            />
          )}
        </section>

        <aside aria-label="İşlemler" className="rounded-[3px] border border-[var(--border)] bg-[var(--bg-elevated)] p-4 min-w-0">
          <IslemPaneli
            secili={tezgah.secili}
            isaretliler={tezgah.isaretliDosyalar}
            surenIslem={tezgah.surenIslem}
            indiriliyor={tezgah.indiriliyor}
            onIslem={(istek) => void tezgah.islemKos(istek)}
            onIndir={() => void tezgah.indirSecili()}
            seciliSayfalar={tezgah.sayfaDuzeni?.secili ?? []}
            sayfaDegisikligi={tezgah.sayfaDegisikligi}
            onSayfaDuzenle={() => void tezgah.sayfaDuzeniniUygula()}
          />
        </aside>
      </div>
    </div>
  );
}
