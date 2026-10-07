import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { AlertCircle, FileStack, PenLine, X } from "lucide-react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { DosyaListesi } from "@/components/pdf/DosyaListesi";
import { IslemPaneli } from "@/components/pdf/IslemPaneli";
import { KarartmaListesi } from "@/components/pdf/KarartmaKatmani";
import { KartaBaglaDiyalogu } from "@/components/pdf/KartaBaglaDiyalogu";
import { KarttanAlDiyalogu } from "@/components/pdf/KarttanAlDiyalogu";
import type { BelgeTezgahiGirisi, Dosya } from "@/types/pdfAraclari";
import { PdfYukleyici } from "@/components/pdf/PdfYukleyici";
import { SayfaGorunumu } from "@/components/pdf/SayfaGorunumu";
import { SayfaIzgarasi } from "@/components/pdf/SayfaIzgarasi";
import { usePdfTezgah } from "@/components/pdf/usePdfTezgah";

/**
 * `/belge-tezgahi` — Belge tezgâhı (G270, plan `docs/plan/pdf-araclari-plani-2026-10-07.md` §2-§3, K1/K2/K8).
 * Giriş yapan HER kullanıcı (yönetici kısıtı yok; rota `ProtectedRoute > ShellLayout`). İki yol çipi: "Düzenle (PDF)"
 * bu sürüm; "Yaz (Word)" G285 ile açılır (şimdilik kapalı).
 *
 * PDF tezgâhı üç bölge: sol `DosyaListesi` (+ yükleyici), orta `<section data-slot="sayfalar">` (G271: seçili dosyanın
 * `SayfaIzgarasi`; G272: karttaki "büyüt" ya da çizim kipi açılınca `SayfaGorunumu` — karartma/not katmanları; biriken
 * karartma alanları `KarartmaListesi`'nde yuvanın altında, dosya başına `key`; dosya yokken boş), sağ `IslemPaneli`.
 * Çalışma dosyaları yalnız bu oturumdadır — sayfa yenilenince liste gider, sunucu 1 saat sonra siler (K2). Sayfa
 * `max-w` koymaz (tam genişlik kuralı). Default export: rota `React.lazy`.
 *
 * G273: `CaseDetails`'ten `navigate("/belge-tezgahi", { state: { document_ids, case } })` ile gelen belgeler açılışta
 * SIRAYLA `karttan-al` ile tezgâha alınır (bir kez; `document_ids` ≥ 2 ise listede işaretlenir — birleştirmeye hazır),
 * `state.case` "Karta bağla" diyaloğunda ön-seçilidir. İki diyalog: `KartaBaglaDiyalogu` (seçili dosya) ve
 * `KarttanAlDiyalogu` (dava ara → belgeleri seç → tezgâha al / al ve birleştir).
 */
export default function BelgeTezgahiPage() {
  useSetPageTitle("Belge tezgâhı", ["Araçlar", "Belge tezgâhı"]);
  const tezgah = usePdfTezgah();
  const location = useLocation();
  const giris = (location.state ?? null) as BelgeTezgahiGirisi | null;
  const [kartaBaglaAcik, setKartaBaglaAcik] = useState(false);
  const [karttanAlAcik, setKarttanAlAcik] = useState(false);
  const onYuklendi = useRef(false);
  const { karttanAlHepsini, isaretle } = tezgah;

  // Açılışta karttan gelen belgeler (bir kez; sayfa içi yeniden çizimde tekrar etmez).
  useEffect(() => {
    if (onYuklendi.current) return;
    const idler = giris?.document_ids?.filter((n) => Number.isInteger(n) && n > 0) ?? [];
    if (idler.length === 0) return;
    onYuklendi.current = true;
    void karttanAlHepsini(idler).then((dosyalar) => {
      if (dosyalar.length >= 2) for (const d of dosyalar) isaretle(d.id, true);
    });
  }, [giris, karttanAlHepsini, isaretle]);

  const karttanAlinanlar = (dosyalar: Dosya[]) => tezgah.dosyaEkle(dosyalar);
  const karttanAlVeBirlestir = (dosyalar: Dosya[]) =>
    void tezgah.islemKos({ islem: "birlestir", girdiler: dosyalar.map((d) => d.id), parametreler: {} });

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

        {/* G271: seçili dosyanın sayfa ızgarası (önizleme, sürükle-sırala, döndür, sil, aralık seçimi);
            G272: büyük sayfa görünümü + karartma/not çizim katmanı, altında karartma alan listesi. */}
        <div className="flex flex-col gap-3 min-w-0">
          <section
            data-slot="sayfalar"
            aria-label="Sayfalar"
            className={[
              "min-h-[320px] rounded-[3px] border bg-[var(--bg-elevated)]",
              tezgah.secili && tezgah.sayfaDuzeni ? "border-[var(--border)]" : "border-dashed border-[var(--border)]",
            ].join(" ")}
          >
            {tezgah.secili && tezgah.buyukSayfa !== null ? (
              <SayfaGorunumu
                key={tezgah.secili.id}
                dosya={tezgah.secili}
                sayfaNo={tezgah.buyukSayfa}
                cizimKipi={tezgah.cizimKipi}
                karartmaAlanlari={tezgah.karartmaAlanlari}
                mesgul={tezgah.surenIslem !== null}
                onIzgara={tezgah.izgarayaDon}
                onSayfaGit={tezgah.buyukSayfayaGit}
                onKip={tezgah.cizimKipiniAyarla}
                onKarartmaEkle={tezgah.karartmaEkle}
                onNotEkle={tezgah.notEkle}
              />
            ) : (
              tezgah.secili &&
              tezgah.sayfaDuzeni && (
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
                  onBuyut={tezgah.sayfayiBuyut}
                />
              )
            )}
          </section>
          {tezgah.secili && (tezgah.karartmaAlanlari.length > 0 || tezgah.cizimKipi === "karart") && (
            <KarartmaListesi
              key={tezgah.secili.id}
              alanlar={tezgah.karartmaAlanlari}
              mesgul={tezgah.surenIslem !== null}
              onSil={tezgah.karartmaSil}
              onTemizle={tezgah.karartmalariTemizle}
              onKarart={() => void tezgah.karartmayiUygula()}
            />
          )}
        </div>

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
            cizimKipi={tezgah.cizimKipi}
            onCizimKipi={tezgah.cizimKipiniAyarla}
            karartmaSayisi={tezgah.karartmaAlanlari.length}
            onKartaBagla={() => setKartaBaglaAcik(true)}
            onKarttanAl={() => setKarttanAlAcik(true)}
          />
        </aside>
      </div>

      <KartaBaglaDiyalogu
        acik={kartaBaglaAcik}
        dosya={tezgah.secili}
        onSecilenKart={giris?.case ?? null}
        onKapat={() => setKartaBaglaAcik(false)}
      />
      <KarttanAlDiyalogu
        acik={karttanAlAcik}
        onKapat={() => setKarttanAlAcik(false)}
        onDosyalar={karttanAlinanlar}
        onBirlestir={karttanAlVeBirlestir}
      />
    </div>
  );
}
