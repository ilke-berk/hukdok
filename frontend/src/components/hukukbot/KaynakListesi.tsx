import { AlertTriangle, CheckCircle2, FileText, Loader2 } from "lucide-react";
import type { HukukbotAlinti, HukukbotKaynak } from "@/types/hukukbot";
import { kaynakNumarasi } from "./atiflar";

type KaynakListesiProps = {
  kaynaklar: HukukbotKaynak[];
  /** PDF'i açar — sayfa `hukukbotApi.indir(filename)` çağırır (yetkili indirme, düz link ÇALIŞMAZ). */
  onIndir: (kaynak: HukukbotKaynak) => void;
  /** Şu an inmekte olan dosya adı (düğme kilitlenir). */
  inen?: string | null;
  /** Metindeki atıf adları, numara sırasıyla (`atiflariNumarala`) — kart numarası ve sıralama bundan. */
  atifAdlari?: string[];
  /** Kart DOM kimliği öneki: `${idOneki}-kaynak-${n}` (rozet tıklaması buraya kaydırır). */
  idOneki?: string;
  /** Rozeti tıklanan kartın numarası — kısa süre vurgulanır. */
  vurgulu?: number | null;
};

/** Kaynak kartının doğrulama rozeti — alanlar yoksa (eski mesaj) rozet de yok. */
function DogrulamaRozeti({ kaynak }: { kaynak: HukukbotKaynak }) {
  if (kaynak.aramada_getirildi === false) {
    return (
      <span
        data-testid="kaynak-dogrulanamadi"
        title="Bu belge cevapta anıldı ama arama bu cevap için onu getirmedi. Atıf doğrulanamadı; belgeyi açıp kontrol edin."
        className="inline-flex items-center gap-1 text-[11px] font-medium text-tone-caution"
      >
        <AlertTriangle className="w-3 h-3" aria-hidden="true" />
        Atıf doğrulanamadı
      </span>
    );
  }
  if (kaynak.aramada_getirildi === true && kaynak.metinde_atif === false) {
    return (
      <span
        data-testid="kaynak-kullanilmadi"
        title="Arama bu belgeyi getirdi ama cevapta ona atıf yapılmadı."
        className="text-[11px] text-[var(--fg-subtle)]"
      >
        Cevapta kullanılmadı
      </span>
    );
  }
  if (kaynak.aramada_getirildi === true) {
    return (
      <span
        data-testid="kaynak-dogrulandi"
        title="Bu belge, cevap üretilirken aramada getirilen belgeler arasında."
        className="inline-flex items-center gap-1 text-[11px] text-tone-ok"
      >
        <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
        Aramada bulundu
      </span>
    );
  }
  return null;
}

function Alinti({ alinti }: { alinti: HukukbotAlinti }) {
  const bulunamadi = alinti.dogrulandi === false;
  return (
    <li
      data-testid={bulunamadi ? "alinti-bulunamadi" : "alinti"}
      className={`text-[11.5px] leading-[1.5] pl-2 border-l-2 break-words ${
        bulunamadi ? "border-tone-caution text-[var(--fg)]" : "border-[var(--border-strong)] text-[var(--fg-muted)]"
      }`}
    >
      <span className="italic">“{alinti.metin}”</span>
      {alinti.dogrulandi === true && (
        <span className="ml-1.5 not-italic text-tone-ok" title="Alıntı belge metninde birebir bulundu.">
          · belgede var
        </span>
      )}
      {bulunamadi && (
        <span
          className="ml-1.5 not-italic font-medium text-tone-caution"
          title="Bu alıntı getirilen belge metninde birebir bulunamadı; model ifadeyi değiştirmiş ya da uydurmuş olabilir."
        >
          · belgede birebir bulunamadı
        </span>
      )}
    </li>
  );
}

/**
 * Yanıtın kaynakları (G205): `/ask` akışının `sources` olayı. Her kaynak adı + önizleme metni;
 * "PDF'i aç" düğmesi `download_url`'i KULLANMAZ (hukbot'a göreli, Authorization ister) — dosya adını
 * sayfaya iletir, sayfa G204 `indir()` ile açar.
 *
 * Atıf doğrulaması (hukbot `citation_check`, 28.09): kart rozeti belgenin aramada gerçekten getirilip
 * getirilmediğini, alıntı listesi her `[Alıntı: "..."]`'nin belge metninde birebir bulunup
 * bulunmadığını gösterir. Cevapta kullanılmayan kaynaklar sunucuda sona sıralanır ve soluk görünür.
 *
 * Numara (28.09): metinde atıfla anılan kaynak kartı, metindeki rozetle aynı numarayı taşır ve numara sırasıyla
 * öne gelir; anılmayanlar numarasız, sunucu sırasıyla arkada.
 */
export function KaynakListesi({ kaynaklar, onIndir, inen, atifAdlari = [], idOneki, vurgulu = null }: KaynakListesiProps) {
  if (kaynaklar.length === 0) return null;
  const sirali = kaynaklar
    .map((k, i) => ({ k, i, no: kaynakNumarasi(k, atifAdlari) }))
    .sort((a, b) => (a.no ?? Infinity) - (b.no ?? Infinity) || a.i - b.i);
  const supheli = kaynaklar.filter(
    (k) => k.aramada_getirildi === false || (k.alintilar ?? []).some((a) => a.dogrulandi === false),
  ).length;
  return (
    <section
      aria-label="Kaynaklar"
      data-testid="hukukbot-kaynaklar"
      className="mt-3 border-t border-[var(--border)] pt-3 grid gap-2"
    >
      <h4 className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
        Kaynaklar · {kaynaklar.length}
      </h4>
      {supheli > 0 && (
        <p
          role="note"
          data-testid="hukukbot-dogrulama-uyarisi"
          className="flex items-start gap-2 border-l-2 border-tone-caution pl-3 py-1 text-[12px] text-[var(--fg)]"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-tone-caution" aria-hidden="true" />
          <span>
            {supheli} kaynakta atıf ya da alıntı belge metniyle doğrulanamadı. İşaretli yerleri belgeyi açarak
            kontrol edin.
          </span>
        </p>
      )}
      <ul className="grid gap-2">
        {sirali.map(({ k, i, no }) => {
          const ad = k.file_display_name || k.filename;
          const iniyor = inen === k.filename;
          const pdf = /\.pdf$/i.test(k.filename);
          const kullanilmadi = k.metinde_atif === false;
          const alintilar = k.alintilar ?? [];
          return (
            <li
              key={`${k.filename}-${i}`}
              id={no !== null && idOneki ? `${idOneki}-kaynak-${no}` : undefined}
              data-testid="kaynak-karti"
              data-atif={no ?? undefined}
              className={`flex items-start gap-2.5 p-2.5 bg-[var(--bg)] border rounded-[3px] min-w-0 scroll-mt-4 transition-colors ${
                no !== null && no === vurgulu ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)]"
              } ${kullanilmadi ? "opacity-70" : ""}`}
            >
              {no !== null ? (
                <span
                  aria-label={`Kaynak ${no}`}
                  className="mt-px shrink-0 grid place-items-center min-w-[20px] h-5 px-1 rounded-full bg-[var(--brand-soft)] border border-[var(--border)] text-[11px] font-semibold tabular-nums text-[var(--brand)]"
                >
                  {no}
                </span>
              ) : (
                <FileText className="w-4 h-4 mt-0.5 shrink-0 text-[var(--fg-subtle)]" aria-hidden="true" />
              )}
              <div className="flex-1 min-w-0 grid gap-1">
                <span className="text-[12.5px] font-medium text-[var(--fg)] break-words">{ad}</span>
                <DogrulamaRozeti kaynak={k} />
                {alintilar.length > 0 ? (
                  <ul className="grid gap-1" aria-label="Alıntılar">
                    {alintilar.map((a, j) => (
                      <Alinti key={j} alinti={a} />
                    ))}
                  </ul>
                ) : (
                  k.text_preview && (
                    <p className="text-[11.5px] leading-[1.5] text-[var(--fg-muted)] line-clamp-3 break-words">
                      {k.text_preview}
                    </p>
                  )
                )}
              </div>
              {k.filename && (
                <button
                  type="button"
                  disabled={iniyor}
                  onClick={() => onIndir(k)}
                  aria-label={`${pdf ? "PDF'i aç" : "Dosyayı indir"}: ${ad}`}
                  className="shrink-0 inline-flex items-center gap-1.5 h-7 px-2.5 rounded-[3px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[11.5px] text-[var(--fg)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors disabled:opacity-50 disabled:cursor-wait"
                >
                  {iniyor && <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />}
                  {pdf ? "PDF'i aç" : "İndir"}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
