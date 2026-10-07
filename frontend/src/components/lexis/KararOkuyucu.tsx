import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DetailSkeleton } from "@/components/skeletons/Skeletons";
import { lexisApi } from "@/lib/lexisApi";
import { tarihYaz } from "@/lib/lexisMetin";
import { BELGE_TURU_RAF_ADLARI, DERECE_ADLARI, HUKUM_SINIFI_ADLARI, KONU_ADLARI, SONUC_ILISKISI_ADLARI, rafAdi } from "@/types/lexis";
import { Rozet } from "./ortak";
import { useVeri } from "./useVeri";
import { hukumTonu, kararNumarasi, tutarListesi } from "./yardimcilar";

type KararOkuyucuProps = {
  /** Açık kararın kimliği; `null` diyaloğu kapatır. */
  kararId: number | null;
  onKapat: () => void;
};

const BASLIK = "font-mono text-[10px] tracking-[0.2em] uppercase font-semibold text-[var(--fg-subtle)]";
const PARAGRAF = "text-[13px] leading-[1.65] text-[var(--fg)] whitespace-pre-line";

/**
 * Karar rafındaki tek kararı okutur: künye, iki sonuç alanı, tutarlar, kodun ayırdığı parçalar (hüküm, iddia, savunma,
 * konu işaretli gerekçe paragrafları) ve istenirse tam metin.
 *
 * Sonuç İKİ AYRI ALANDIR (K22): "kararın bütünü" kodun hükümden okuduğudur, "müvekkil yönünden" HUKDOK'un etiketidir.
 * Karma hükümde ikisi bilerek farklı olabilir; hükmedilen tutar kararın bütününe aittir. Metin büronun kendi
 * kararıdır ve MASKESİZDİR — modele giden kopya ayrıca maskelenir.
 */
export function KararOkuyucu({ kararId, onKapat }: KararOkuyucuProps) {
  return (
    <Dialog open={kararId !== null} onOpenChange={(o) => !o && onKapat()}>
      {kararId !== null && (
        <DialogContent
          className="theme-classic max-w-3xl max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none text-[var(--fg)]"
          data-testid="lexis-karar-okuyucu"
        >
          <KararGovdesi key={kararId} kararId={kararId} />
        </DialogContent>
      )}
    </Dialog>
  );
}

function KararGovdesi({ kararId }: { kararId: number }) {
  const { veri: k, hata } = useVeri((signal) => lexisApi.kararGetir(kararId, signal), String(kararId));
  const [konu, setKonu] = useState<string | null>(null);
  const [tamMetin, setTamMetin] = useState(false);

  if (hata) {
    return (
      <DialogHeader>
        <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">Karar açılamadı</DialogTitle>
        <DialogDescription role="alert" className="text-[12.5px] text-tone-danger">
          {hata}
        </DialogDescription>
      </DialogHeader>
    );
  }
  if (!k) {
    return (
      <>
        <DialogHeader>
          <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">Karar yükleniyor…</DialogTitle>
          <DialogDescription className="sr-only">Karar metni getiriliyor</DialogDescription>
        </DialogHeader>
        <DetailSkeleton label="Karar yükleniyor…" />
      </>
    );
  }

  const tutarlar = (
    [
      ["Talep (maddi)", k.talep_maddi],
      ["Talep (manevi)", k.talep_manevi],
      ["Hükmedilen (maddi)", k.hukmedilen_maddi],
      ["Hükmedilen (manevi)", k.hukmedilen_manevi],
      ["Hükmedilen (ayrıştırılmamış)", k.hukmedilen_birlesik],
      ["Vekâlet ücreti", k.vekalet_ucreti],
      ["Yargılama gideri", k.yargilama_gideri],
    ] as const
  ).filter(([, liste]) => liste.length > 0);
  const olgular = [
    k.olay && (k.olay === "OLUM" ? "ölüm" : "yaralanma"),
    k.maluliyet_orani.length > 0 && `maluliyet ${k.maluliyet_orani.join(", ")}`,
    k.kusur_orani.length > 0 && `kusur ${k.kusur_orani.join(", ")}`,
    k.yas.length > 0 && `yaş ${k.yas.join(", ")}`,
    k.davaci_sayisi && `${k.davaci_sayisi} davacı`,
    ...k.dayanak_kurul,
    ...k.faiz,
  ].filter(Boolean);
  const konular = Object.keys(k.konular).sort((a, b) => k.konular[b] - k.konular[a]);
  const gerekce = konu ? k.parcalar.gerekce.filter((p) => p.konular.includes(konu)) : k.parcalar.gerekce;
  const parcaYok = !k.parcalar.hukum && k.parcalar.iddia.length === 0 && k.parcalar.savunma.length === 0 && k.parcalar.gerekce.length === 0;

  return (
    <>
      <DialogHeader>
        <DialogTitle className="font-display text-[19px] font-medium text-[var(--fg)]">
          {k.mahkeme ?? "Mahkemesi bilinmeyen karar"}
          {kararNumarasi(k) && <span className="ml-2 font-mono text-[12px] text-[var(--fg-subtle)]">{kararNumarasi(k)}</span>}
        </DialogTitle>
        <DialogDescription className="text-[12.5px] text-[var(--fg-muted)]">
          {[k.karar_tarihi && tarihYaz(k.karar_tarihi), rafAdi(BELGE_TURU_RAF_ADLARI, k.belge_turu), k.derece && rafAdi(DERECE_ADLARI, k.derece), k.uzmanlik]
            .filter(Boolean)
            .join(" · ")}
          {" — maskesiz metin"}
        </DialogDescription>
      </DialogHeader>

      <dl data-testid="lexis-karar-sonuclari" className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-[12.5px]">
        <div>
          <dt className="text-[var(--fg-subtle)]">Kararın bütünü (hükümden)</dt>
          <dd className="mt-0.5">{k.hukum_sinifi ? <Rozet ton={hukumTonu(k.hukum_sinifi)}>{rafAdi(HUKUM_SINIFI_ADLARI, k.hukum_sinifi)}</Rozet> : "kod okuyamadı"}</dd>
        </div>
        <div>
          <dt className="text-[var(--fg-subtle)]">Müvekkil yönünden (HUKDOK etiketi)</dt>
          <dd className="mt-0.5">
            {k.sonuc_muvekkil ? <Rozet ton={hukumTonu(k.sonuc_muvekkil)}>{rafAdi(HUKUM_SINIFI_ADLARI, k.sonuc_muvekkil)}</Rozet> : "etiket yok"}
            {k.sonuc_iliskisi && k.sonuc_iliskisi !== "AYNI" && (
              <span className="ml-2 text-[12px] text-[var(--fg-muted)]">{rafAdi(SONUC_ILISKISI_ADLARI, k.sonuc_iliskisi)}</span>
            )}
          </dd>
        </div>
      </dl>

      {tutarlar.length > 0 && (
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-[12.5px]">
          {tutarlar.map(([etiket, liste]) => (
            <div key={etiket}>
              <dt className="text-[var(--fg-subtle)]">{etiket}</dt>
              <dd className="font-mono tabular-nums text-[var(--fg)]">{tutarListesi([...liste])}</dd>
            </div>
          ))}
        </dl>
      )}
      {olgular.length > 0 && <p className="text-[12.5px] text-[var(--fg-muted)]">{olgular.join(" · ")}</p>}

      {parcaYok && <p className="text-[12.5px] text-[var(--fg-muted)]">Bu belgede kodun ayırdığı parça yok; tam metinden okuyun.</p>}

      {k.parcalar.hukum && (
        <section aria-label="Hüküm" className="grid gap-1">
          <h4 className={BASLIK}>Hüküm</h4>
          <p className={`${PARAGRAF} border-l-2 border-[var(--brand)] pl-3`}>{k.parcalar.hukum}</p>
        </section>
      )}

      {(
        [
          ["İddia", k.parcalar.iddia],
          ["Savunma", k.parcalar.savunma],
        ] as const
      ).map(
        ([ad, parcalar]) =>
          parcalar.length > 0 && (
            <section key={ad} aria-label={ad} className="grid gap-1">
              <h4 className={BASLIK}>{ad}</h4>
              {parcalar.map((p, i) => (
                <p key={i} className={PARAGRAF}>
                  {p}
                </p>
              ))}
            </section>
          ),
      )}

      {k.parcalar.gerekce.length > 0 && (
        <section aria-label="Gerekçe" className="grid gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <h4 className={`${BASLIK} mr-1`}>
              Gerekçe · {gerekce.length}/{k.parcalar.gerekce.length} paragraf
            </h4>
            {konular.map((kod) => (
              <button
                key={kod}
                type="button"
                aria-pressed={konu === kod}
                onClick={() => setKonu(konu === kod ? null : kod)}
                className={`px-1.5 py-0.5 border text-[11px] transition-colors ${
                  konu === kod ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--fg)]" : "border-[var(--border)] text-[var(--fg-muted)] hover:text-[var(--fg)]"
                }`}
              >
                {rafAdi(KONU_ADLARI, kod)} <span className="font-mono tabular-nums">{k.konular[kod]}</span>
              </button>
            ))}
          </div>
          {gerekce.map((p, i) => (
            <div key={i}>
              <p className={PARAGRAF}>{p.metin}</p>
              {p.konular.length > 0 && <span className="text-[11px] text-[var(--fg-subtle)]">{p.konular.map((kod) => rafAdi(KONU_ADLARI, kod)).join(" · ")}</span>}
            </div>
          ))}
        </section>
      )}

      <section aria-label="Tam metin" className="grid gap-1">
        <button type="button" aria-expanded={tamMetin} onClick={() => setTamMetin((a) => !a)} className={`${BASLIK} justify-self-start hover:text-[var(--brand)]`}>
          {tamMetin ? "Tam metni gizle" : `Tam metni göster · ${k.metin_uzunluk.toLocaleString("tr-TR")} karakter`}
        </button>
        {tamMetin && <p className={`${PARAGRAF} border border-[var(--border)] bg-[var(--bg)] px-3 py-2`}>{k.metin}</p>}
      </section>
    </>
  );
}
