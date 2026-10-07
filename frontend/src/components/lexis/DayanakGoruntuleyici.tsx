import { useEffect, useState } from "react";
import { lexisApi } from "@/lib/lexisApi";
import { alintiAraliklari, type MetinAraligi } from "@/lib/lexisMetin";
import type { BolumKodu, LexisTaslak, RafKarari } from "@/types/lexis";
import { BolgeBasligi, BosDurum } from "./ortak";
import { BAGLANTI_SINIFI, dayanakBul, iptalMi, kararKunyesi, vurguParcalari } from "./yardimcilar";

type DayanakGoruntuleyiciProps = {
  taslak: LexisTaslak | null;
  /** Seçili madde (1'den başlar). */
  sira: number | null;
  bolumAdlari: Partial<Record<BolumKodu, string>>;
  /** Dava kartının kararları: alıntı karardan geldiyse künyesi gösterilir. */
  kararlar?: RafKarari[];
  onKararOku?: (id: number) => void;
};

/** Karardaki alıntının çevresinden gösterilen metin (karakter): alıntının önünden ve ardından bu kadar. */
const CEVRE = 260;

interface KararKonumu {
  kararId: number;
  metin: string;
  araliklar: MetinAraligi[];
  bastanKesik: boolean;
  sondanKesik: boolean;
}

/** Alıntının karar metnindeki yeri: çevresiyle birlikte kesit + kesite göre vurgu aralıkları. Bulunamazsa `null`. */
function karardaBul(kararId: number, metin: string, alinti: string): KararKonumu | null {
  const araliklar = alintiAraliklari(metin, alinti);
  if (!araliklar) return null;
  const bas = Math.max(0, araliklar[0].bas - CEVRE);
  const son = Math.min(metin.length, araliklar[araliklar.length - 1].son + CEVRE);
  return {
    kararId,
    metin: metin.slice(bas, son),
    araliklar: araliklar.map((a) => ({ bas: a.bas - bas, son: a.son - bas })),
    bastanKesik: bas > 0,
    sondanKesik: son < metin.length,
  };
}

function Vurgulu({ metin, araliklar }: { metin: string; araliklar: MetinAraligi[] }) {
  return (
    <>
      {vurguParcalari(metin, araliklar).map((p, i) =>
        p.vurgulu ? (
          <mark key={i} className="bg-tone-caution/25 text-[var(--fg)] px-0.5 [box-decoration-break:clone]">
            {p.metin}
          </mark>
        ) : (
          <span key={i}>{p.metin}</span>
        ),
      )}
    </>
  );
}

/**
 * Seçili maddenin dayanak alıntısını kaynağında vurgular: insan alıntının maddeyi gerçekten DESTEKLEYİP
 * desteklemediğine buradan bakar (denetim yalnız alıntının dosyada geçtiğini doğrular). Alıntı önce taslağın özet
 * bölümlerinde, orada yoksa taslağın yazıldığı KARARLARIN metninde aranır (kararlardan yazılan maddenin dayanağı
 * karardır); karar metni gerektiğinde servisten alınır.
 */
export function DayanakGoruntuleyici({ taslak, sira, bolumAdlari, kararlar = [], onKararOku }: DayanakGoruntuleyiciProps) {
  const madde = taslak?.degerlendirme && sira !== null ? taslak.degerlendirme.maddeler[sira - 1] : undefined;
  const konum = taslak && madde ? dayanakBul(taslak, madde) : null;
  const alinti = madde && madde.tur !== "KALIP" ? (madde.dayanak_alinti?.trim() ?? "") : "";
  // Özet bölümlerinde bulunamayan alıntı kararlarda aranır.
  const kararIdleri = !konum && alinti ? (taslak?.kararlar ?? []) : [];
  const aramaAnahtari = kararIdleri.length > 0 ? `${kararIdleri.join(",")}|${alinti}` : "";
  const [kararKonumu, setKararKonumu] = useState<{ anahtar: string; sonuc: KararKonumu | null } | null>(null);

  useEffect(() => {
    if (!aramaAnahtari) return;
    const ac = new AbortController();
    (async () => {
      for (const id of kararIdleri) {
        try {
          const bulunan = karardaBul(id, (await lexisApi.kararGetir(id, ac.signal)).metin, alinti);
          if (bulunan) return bulunan;
        } catch (e) {
          if (iptalMi(e)) throw e;
        }
      }
      return null;
    })()
      .then((sonuc) => setKararKonumu({ anahtar: aramaAnahtari, sonuc }))
      .catch(() => undefined);
    return () => ac.abort();
    // `kararIdleri` ve `alinti` anahtarın içindedir.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aramaAnahtari]);

  const karardaAraniyor = aramaAnahtari !== "" && kararKonumu?.anahtar !== aramaAnahtari;
  const karardaki = aramaAnahtari !== "" && kararKonumu?.anahtar === aramaAnahtari ? kararKonumu.sonuc : null;
  const kaynakKarar = karardaki ? kararlar.find((k) => k.id === karardaki.kararId) : undefined;

  return (
    <section aria-label="Dayanak" data-testid="lexis-dayanak" className="grid gap-2">
      <BolgeBasligi sag={madde ? <span className="font-mono text-[10.5px] text-[var(--fg-subtle)]">madde {sira}</span> : undefined}>Dayanak</BolgeBasligi>
      {!madde && <BosDurum>Bir maddede "Kaynakta göster"e basın; alıntı dosyadaki yerinde vurgulanır.</BosDurum>}
      {madde && madde.tur === "KALIP" && <BosDurum>Kalıp madde dayanak taşımaz.</BosDurum>}
      {madde && madde.tur !== "KALIP" && !alinti && <BosDurum>Bu maddenin dayanak alıntısı yok.</BosDurum>}
      {alinti && !konum && karardaAraniyor && <BosDurum>Alıntı kararlarda aranıyor…</BosDurum>}
      {alinti && !konum && !karardaAraniyor && !karardaki && (
        <p className="text-[12.5px] leading-[1.5] text-tone-danger">
          {kararIdleri.length > 0 ? "Alıntı dosyanın bölümlerinde ve kararlarında bulunamadı." : "Alıntı dosyanın bölümlerinde bulunamadı."}
        </p>
      )}
      {konum && (
        <figure className="border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2.5">
          <figcaption className="mb-1 text-[11px] text-[var(--fg-subtle)]">
            {bolumAdlari[konum.bolum] ?? konum.bolum} · paragraf {konum.paragraf + 1}
          </figcaption>
          <p className="text-[13px] leading-[1.65] text-[var(--fg)]">
            <Vurgulu metin={konum.metin} araliklar={konum.araliklar} />
          </p>
        </figure>
      )}
      {karardaki && (
        <figure data-testid="lexis-dayanak-karar" className="border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2.5">
          <figcaption className="mb-1 text-[11px] text-[var(--fg-subtle)]">
            Karar:{" "}
            {onKararOku ? (
              <button type="button" onClick={() => onKararOku(karardaki.kararId)} className={BAGLANTI_SINIFI}>
                {kaynakKarar ? kararKunyesi(kaynakKarar) : `#${karardaki.kararId}`}
              </button>
            ) : kaynakKarar ? (
              kararKunyesi(kaynakKarar)
            ) : (
              `#${karardaki.kararId}`
            )}
          </figcaption>
          <p className="text-[13px] leading-[1.65] text-[var(--fg)] whitespace-pre-line">
            {karardaki.bastanKesik && "… "}
            <Vurgulu metin={karardaki.metin} araliklar={karardaki.araliklar} />
            {karardaki.sondanKesik && " …"}
          </p>
        </figure>
      )}
    </section>
  );
}
