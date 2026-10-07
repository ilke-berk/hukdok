import { useCallback, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { FlaskConical, Menu } from "lucide-react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { useOdakModu } from "@/hooks/useOdakModu";
import { ORNEK_VERI, veriKipiAyarla, type VeriKipi } from "@/lib/lexisApi";
import { BAGLANTI_SINIFI } from "@/components/lexis/yardimcilar";
import { GecmisTablosu } from "@/components/lexis/GecmisTablosu";
import { KartBagiListesi } from "@/components/lexis/KartBagiListesi";
import { KutuphaneTarayici } from "@/components/lexis/KutuphaneTarayici";
import { SirketProfilleri } from "@/components/lexis/SirketProfilleri";
import { Tezgah } from "@/components/lexis/Tezgah";

/**
 * `/lexis` — Lexis medikolegal rapor aracının ÖNİZLEMESİ (04.10.2026). Çekirdek ayrı depoda (`lexis-rapor`) ayrı
 * servis olarak koşar. Varsayılan kip örnek veridir (`lib/lexisApi.ts` örnek adaptörü, sentetik; tek ağ isteği
 * "Word indir"); "gerçek dava" kipinde (`?veri=gercek`) beş sekme de servisten gelir ve taslak, koşu geçmişi, kart
 * seçimi, şirket profili servisin kendi veritabanında saklanır (`lib/lexisServis.ts`).
 * Entegrasyona dek yalnız yönetici görür (menü + `ProtectedAdminRoute`).
 *
 * - Odak modu (`useOdakModu`, Hukukbot deseni): kabuk Topbar'ı çizmez, sayfa tam yüksekliktir; HUKDOK menüsü
 *   üst çubuktaki ☰ ile açılır. Sayfa `max-w` koymaz.
 * - Sekme URL'de: `/lexis?sekme=<kod>` (varsayılan "Rapor yaz" parametresizdir). "Rapor yaz" gövdesi sekme
 *   değişince de bağlı kalır (gizlenir) — yarım taslak kaybolmaz; diğer sekmeler açılınca bağlanır.
 * - Default export: rota `React.lazy` ile bağlanır.
 */
const SEKMELER = [
  { kod: "yaz", ad: "Rapor yaz" },
  { kod: "gecmis", ad: "Geçmiş" },
  { kod: "kutuphane", ad: "Kütüphane" },
  { kod: "kart-bagi", ad: "Kart bağı" },
  { kod: "sirketler", ad: "Şirketler" },
] as const;

type SekmeKodu = (typeof SEKMELER)[number]["kod"];
const VARSAYILAN_SEKME: SekmeKodu = "yaz";

function sekmeCoz(deger: string | null): SekmeKodu {
  return SEKMELER.some((s) => s.kod === deger) ? (deger as SekmeKodu) : VARSAYILAN_SEKME;
}

export default function LexisPage() {
  useSetPageTitle("Lexis", ["Araçlar", "Lexis"]);
  const menuyuAc = useOdakModu();
  const [params, setParams] = useSearchParams();
  const sekme = sekmeCoz(params.get("sekme"));
  // Veri kipi URL'dedir (`?veri=gercek`); adaptör modül düzeyinde seçilir, çocuklar çizilmeden ÖNCE ayarlanır.
  const kip: VeriKipi = params.get("veri") === "gercek" ? "gercek" : "ornek";
  veriKipiAyarla(kip);

  const kipDegistir = useCallback(() => {
    setParams(
      (onceki) => {
        const sonraki = new URLSearchParams(onceki);
        if (kip === "gercek") sonraki.delete("veri");
        else sonraki.set("veri", "gercek");
        return sonraki;
      },
      { replace: true },
    );
  }, [kip, setParams]);

  const sekmeyeGit = useCallback(
    (hedef: SekmeKodu) => {
      setParams(
        (onceki) => {
          const sonraki = new URLSearchParams(onceki);
          if (hedef === VARSAYILAN_SEKME) sonraki.delete("sekme");
          else sonraki.set("sekme", hedef);
          return sonraki;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const govde = (kod: SekmeKodu): ReactNode => {
    switch (kod) {
      case "yaz":
        return <Tezgah key={kip} />;
      case "gecmis":
        return <GecmisTablosu key={kip} />;
      case "kutuphane":
        return <KutuphaneTarayici key={kip} />;
      case "kart-bagi":
        return <KartBagiListesi key={kip} />;
      case "sirketler":
        return <SirketProfilleri key={kip} />;
    }
  };

  return (
    <div data-testid="lexis-sayfasi" className="flex flex-col w-full min-w-0 h-full min-h-0 bg-[var(--bg-elevated)] overflow-hidden">
      <header className="h-12 shrink-0 flex items-center gap-3 px-3 md:px-5 border-b border-[var(--border)] bg-[var(--bg)]">
        <button
          type="button"
          onClick={menuyuAc}
          aria-label="HUKDOK menüsünü aç"
          className="w-8 h-8 grid place-items-center rounded-[3px] border border-[var(--border)] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:border-[var(--brand)] shrink-0"
        >
          <Menu className="w-4 h-4" />
        </button>
        <h1 className="font-display text-[17px] font-medium tracking-[-0.005em] text-[var(--fg)] shrink-0">Lexis</h1>
        <div role="tablist" aria-label="Lexis sekmeleri" className="flex items-stretch gap-1 h-full min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {SEKMELER.map((s) => {
            const secili = s.kod === sekme;
            return (
              <button
                key={s.kod}
                type="button"
                role="tab"
                id={`lexis-sekme-${s.kod}`}
                aria-selected={secili}
                aria-controls={`lexis-govde-${s.kod}`}
                onClick={() => sekmeyeGit(s.kod)}
                className={`relative px-2.5 whitespace-nowrap font-mono text-[11px] tracking-[0.06em] uppercase transition-colors ${
                  secili ? "text-[var(--fg)] font-semibold" : "text-[var(--fg-muted)] hover:text-[var(--fg)]"
                }`}
              >
                {s.ad}
                {secili && <span className="absolute left-2 right-2 bottom-0 h-[2px] bg-brand-solid" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      </header>

      {ORNEK_VERI && (
        <div
          role="note"
          data-testid="lexis-ornek-seridi"
          className="shrink-0 flex items-center gap-2 px-3 md:px-5 py-1.5 border-b border-dashed border-[var(--border-strong)] text-[12px] text-[var(--fg-muted)]"
        >
          <FlaskConical className="w-3.5 h-3.5 shrink-0 text-[var(--fg-subtle)]" aria-hidden="true" />
          <span className="font-medium text-[var(--fg)] whitespace-nowrap shrink-0">{kip === "gercek" ? "Gerçek dava" : "Örnek veri"}</span>
          <span className="min-w-0 truncate">
            {kip === "gercek"
              ? "— beş sekme de gerçek veridir (eski rapor metni maskeli). Taslak karttan iskelet olarak gelir; karta bağlı karar seçilirse (yazım açıksa) onayınızla maskelenip modele gönderilir ve kararlardan yazılır. Siz yazdıkça kaydedilir, dava yeniden seçilince geri açılır."
              : "— gerçek dosya değil. Ekran tasarımı önizlemesidir; hiçbir şey kaydedilmez. Yalnız \"Word indir\" örnek taslağı Lexis servisine gönderir."}
          </span>
          <button type="button" data-testid="lexis-kip-dugmesi" onClick={kipDegistir} className={`ml-auto shrink-0 whitespace-nowrap ${BAGLANTI_SINIFI}`}>
            {kip === "gercek" ? "Örnek veriye dön" : "Gerçek davalarla dene"}
          </button>
        </div>
      )}

      <div className="flex-1 min-h-0 min-w-0">
        {SEKMELER.map((s) => {
          const secili = s.kod === sekme;
          // "Rapor yaz" hep bağlı kalır; diğer sekmeler yalnız açıkken.
          if (!secili && s.kod !== VARSAYILAN_SEKME) return null;
          return (
            <div
              key={s.kod}
              role="tabpanel"
              id={`lexis-govde-${s.kod}`}
              aria-labelledby={`lexis-sekme-${s.kod}`}
              hidden={!secili}
              className="h-full min-h-0"
            >
              {govde(s.kod)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
