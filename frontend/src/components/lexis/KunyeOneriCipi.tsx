import { useState } from "react";
import { Check, FileSearch, Undo2, X } from "lucide-react";
import { BELGE_TURU_ADLARI, type KunyeHatDurumu, type KunyeOneriDurumu, type KunyeOnerisi, type LexisBelgeTuru } from "@/types/lexis";
import { Rozet } from "./ortak";
import { BAGLANTI_SINIFI } from "./yardimcilar";

type KararFn = (oneri: KunyeOnerisi, durum: KunyeOneriDurumu) => void;

const KART_NOTU: Record<KunyeOnerisi["kart_durumu"], string | null> = {
  ayni: "karttakiyle aynı",
  farkli: null, // kart değeri ayrıca yazılır
  kartta_bos: "kartta boş",
  kartta_yok: null,
};

/** Değerin belge adıyla görünen etiketi; alıntı `title`'da (üstüne gelince) ve ekran okuyucuya açık. */
function oneriBasligi(o: KunyeOnerisi, belgeAdi: (id: number) => string): string {
  return `Belge: ${belgeAdi(o.belge_id)}${o.metin_kaynagi === "gorsel" ? " (taranmış — model okuması)" : ""}\nAlıntı: “${o.alinti}”${o.kart_durumu === "farkli" && o.kart_degeri ? `\nKartta: ${o.kart_degeri}` : ""}`;
}

/**
 * Bir künye alanının belgeden gelen önerisi (K33-K34): değer + belge adı, alıntı üstüne gelince; kabul / ret. Kart
 * değeri farklıysa ikisi yan yana yazılır — sessizce biri seçilmez. Reddedilen öneri gösterilmez.
 */
export function KunyeOneriCipi({ oneri, belgeAdi, onKarar, kilitli = false }: { oneri: KunyeOnerisi; belgeAdi: (id: number) => string; onKarar: KararFn; kilitli?: boolean }) {
  const kabul = oneri.durum === "kabul";
  const not = KART_NOTU[oneri.kart_durumu];
  return (
    <span
      data-testid="kunye-oneri"
      title={oneriBasligi(oneri, belgeAdi)}
      className={`inline-flex flex-wrap items-center gap-1 px-1.5 py-0.5 border rounded-[3px] text-[11.5px] leading-[1.4] ${
        kabul ? "border-tone-ok/50 bg-tone-ok/10" : "border-[var(--border-strong)] bg-[var(--bg-sunken)]"
      }`}
    >
      <FileSearch className="w-3 h-3 shrink-0 text-[var(--fg-subtle)]" aria-hidden="true" />
      <span className="font-medium text-[var(--fg)] break-words">{oneri.deger}</span>
      <span className="text-[var(--fg-subtle)]">· {belgeAdi(oneri.belge_id)}</span>
      {oneri.kart_durumu === "farkli" && oneri.kart_degeri && <span className="text-tone-caution">· kartta: {oneri.kart_degeri}</span>}
      {not && <span className="text-[var(--fg-subtle)]">· {not}</span>}
      {oneri.metin_kaynagi === "gorsel" && <span className="text-tone-caution">· taranmış belgeden</span>}
      <span className="sr-only">Alıntı: {oneri.alinti}</span>
      {kabul ? (
        <button type="button" disabled={kilitli} onClick={() => onKarar(oneri, "oneri")} aria-label={`${oneri.deger} kabulünü geri al`} className={`inline-flex items-center gap-0.5 ${BAGLANTI_SINIFI}`}>
          <Undo2 className="w-3 h-3" aria-hidden="true" /> geri al
        </button>
      ) : (
        <>
          <button type="button" disabled={kilitli} onClick={() => onKarar(oneri, "kabul")} aria-label={`${oneri.deger} önerisini kabul et`} className="p-0.5 text-tone-ok hover:bg-tone-ok/15 rounded-[2px] disabled:opacity-50">
            <Check className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          <button type="button" disabled={kilitli} onClick={() => onKarar(oneri, "ret")} aria-label={`${oneri.deger} önerisini reddet`} className="p-0.5 text-tone-danger hover:bg-tone-danger/15 rounded-[2px] disabled:opacity-50">
            <X className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </>
      )}
    </span>
  );
}

type KunyeDoldurProps = {
  hat: KunyeHatDurumu | null;
  calisiyor: boolean;
  ilerleme: string | null;
  uyarilar: string[];
  hata: string | null;
  /** Belge sınıfı önerileri (türü boş / "Diğer" belge; S9). */
  siniflar: KunyeOnerisi[];
  belgeAdi: (id: number) => string;
  onDoldur: (onay: boolean) => void;
  onKarar: KararFn;
  kilitli?: boolean;
};

/**
 * "Belgelerden doldur": kartın belgelerinden künye önerisi (Aşama 13). Gerçek kipte belgeler modele MASKESİZ gider —
 * her koşuda onay kutusu (K4); onay koşudan sonra sıfırlanır. Örnek kipte ve hat kapalıyken çizilmez.
 */
export function KunyeDoldur({ hat, calisiyor, ilerleme, uyarilar, hata, siniflar, belgeAdi, onDoldur, onKarar, kilitli = false }: KunyeDoldurProps) {
  const [onay, setOnay] = useState(false);
  if (!hat) return null;
  if (!hat.acik) {
    return hat.neden === "ornek" ? null : (
      <p className="text-[11.5px] text-[var(--fg-subtle)]">Belgeden künye çıkarımı kapalı ({hat.neden}).</p>
    );
  }
  const bekleyenSinif = siniflar.filter((s) => s.durum !== "ret");
  return (
    <div data-testid="kunye-doldur" className="grid gap-1.5 border border-[var(--border)] bg-[var(--bg-sunken)] px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={kilitli || calisiyor || (hat.onay_gerekir && !onay)}
          onClick={() => {
            onDoldur(onay);
            setOnay(false);
          }}
          className="h-7 px-2.5 border border-[var(--brand)] text-[12px] font-medium text-[var(--brand)] hover:bg-[var(--brand)]/10 rounded-[3px] disabled:opacity-50"
        >
          {calisiyor ? "Okunuyor…" : "Belgelerden doldur"}
        </button>
        {hat.kip === "sahte" ? <Rozet>sahte üretici</Rozet> : <Rozet ton="caution">{hat.model}</Rozet>}
        {ilerleme && <span role="status" className="text-[11.5px] text-[var(--fg-muted)]">{ilerleme}</span>}
      </div>
      {hat.onay_gerekir && (
        <label className="flex items-start gap-2 text-[11.5px] leading-[1.45] text-[var(--fg)]">
          <input type="checkbox" className="mt-[2px] accent-[var(--brand)]" checked={onay} disabled={calisiyor} onChange={(e) => setOnay(e.target.checked)} />
          <span>Kartın belgeleri <span className="font-medium">{hat.model}</span> modeline (Google) maskesiz gönderilecek. Bu koşu için onaylıyorum.</span>
        </label>
      )}
      {hata && <p role="alert" className="text-[11.5px] text-tone-danger">{hata}</p>}
      {uyarilar.length > 0 && (
        <details className="text-[11.5px] text-[var(--fg-muted)]">
          <summary className="cursor-pointer">{uyarilar.length} uyarı (okunamayan belge, düşen öneri)</summary>
          <ul className="mt-1 grid gap-0.5 list-disc pl-4">
            {uyarilar.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </details>
      )}
      {bekleyenSinif.length > 0 && (
        <div className="grid gap-1">
          <span className="text-[11px] text-[var(--fg-subtle)]">Belge türü önerisi (kartta türü boş / Diğer)</span>
          {bekleyenSinif.map((s) => (
            <KunyeOneriCipi
              key={s.id}
              oneri={{ ...s, deger: BELGE_TURU_ADLARI[s.deger as LexisBelgeTuru] ?? s.deger }}
              belgeAdi={belgeAdi}
              onKarar={(o, d) => onKarar({ ...o, deger: s.deger }, d)}
              kilitli={kilitli}
            />
          ))}
        </div>
      )}
    </div>
  );
}

