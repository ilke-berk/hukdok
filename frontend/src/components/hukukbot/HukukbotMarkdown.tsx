import { useMemo, type ComponentProps } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { ALINTI_HREF_ONEKI, ATIF_HREF_ONEKI } from "./atiflar";

/**
 * Model yanıtı için markdown (G205) — `react-markdown` + `remark-gfm` (tablo, üstü çizili, görev listesi).
 * Ham HTML RENDER EDİLMEZ: `rehype-raw` yok; üstelik markdown içindeki ham HTML düğümleri (`raw`)
 * `hamHtmlMetne` eklentisiyle DÜZ METNE çevrilir → `<script>` vb. ekranda metin olarak görünür, DOM'a
 * etiket olarak girmez (sessizce kaybolmaz da: kullanıcı modelin ne yazdığını görür).
 * Link şemaları react-markdown'ın varsayılan `urlTransform`'undan geçer (javascript: vb. düşer).
 * Tipografi eklentisi yapılandırılı değil → öğe biçimleri tema token'larıyla burada verilir.
 * Atıf rozeti (28.09): `atiflariNumarala`'nın ürettiği `[n](#atif-n)` bağlantısı link değil küçük numaralı
 * düğme olarak çizilir; tıklama `onAtif(n)` (kaynak kartına kaydırır), üzerine gelince belge adı.
 * Alıntı (28.09): `[metin](#alinti-i)` belgeden birebir alınan cümledir — tırnaklı, italik, açık zeminli; hukbot
 * belgede bulamadıysa (`alintiDurumu(i) === false`) turuncu dalgalı alt çizgi + ipucu.
 * Okunurluk (28.09): gövde 15 px / 1.7 satır aralığı, paragraf ve madde arası açıldı.
 */

type HastDugumu = { type: string; value?: string; children?: HastDugumu[] };

/** rehype eklentisi: `raw` (ham HTML) düğümlerini aynı metinli `text` düğümüne çevirir. */
function hamHtmlMetne() {
  const gez = (dugum: HastDugumu) => {
    if (dugum.type === "raw") {
      dugum.type = "text";
      return;
    }
    dugum.children?.forEach(gez);
  };
  return (agac: HastDugumu) => {
    gez(agac);
  };
}

function DisBaglanti(p: ComponentProps<"a">) {
  return (
    <a
      {...p}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[var(--brand)] underline underline-offset-2 break-words hover:opacity-80"
    />
  );
}

const BILESENLER: Components = {
  p: ({ node: _node, ...p }) => <p className="my-3 first:mt-0 last:mb-0" {...p} />,
  ul: ({ node: _node, ...p }) => <ul className="my-3 pl-5 list-disc space-y-2.5 marker:text-[var(--fg-subtle)]" {...p} />,
  ol: ({ node: _node, ...p }) => <ol className="my-3 pl-5 list-decimal space-y-2.5 marker:text-[var(--fg-subtle)]" {...p} />,
  h1: ({ node: _node, ...p }) => <h3 className="mt-5 mb-2 font-display text-[20px] font-medium" {...p} />,
  h2: ({ node: _node, ...p }) => <h4 className="mt-5 mb-2 font-display text-[17px] font-medium" {...p} />,
  h3: ({ node: _node, ...p }) => <h5 className="mt-4 mb-1.5 text-[15px] font-semibold" {...p} />,
  blockquote: ({ node: _node, ...p }) => (
    <blockquote className="my-2 border-l-2 border-[var(--brand)] pl-3 text-[var(--fg-muted)]" {...p} />
  ),
  code: ({ node: _node, className, ...p }) => (
    <code
      className={[
        "font-mono text-[12.5px] bg-[var(--bg-sunken)] px-1 py-0.5 rounded-[3px]",
        className ?? "",
      ].join(" ")}
      {...p}
    />
  ),
  pre: ({ node: _node, ...p }) => (
    <pre
      className="my-2 overflow-x-auto p-3 bg-[var(--bg-sunken)] border border-[var(--border)] rounded-[3px] text-[12.5px] [&>code]:bg-transparent [&>code]:p-0"
      {...p}
    />
  ),
  // Geniş tablo sayfayı değil kendi kutusunu kaydırır (375 px kuralı).
  table: ({ node: _node, ...p }) => (
    <div className="my-3 max-w-full overflow-x-auto" data-testid="hukukbot-tablo-kutusu">
      <table className="w-full border-collapse text-[12.5px]" {...p} />
    </div>
  ),
  th: ({ node: _node, ...p }) => (
    <th
      className="border border-[var(--border)] bg-[var(--bg-sunken)] px-2 py-1.5 text-left font-semibold align-top"
      {...p}
    />
  ),
  td: ({ node: _node, ...p }) => <td className="border border-[var(--border)] px-2 py-1.5 align-top" {...p} />,
  hr: ({ node: _node, ...p }) => <hr className="my-3 border-[var(--border)]" {...p} />,
};

type HukukbotMarkdownProps = {
  metin: string;
  /** Atıf rozetine tıklanınca (n = 1'den atıf numarası). */
  onAtif?: (n: number) => void;
  /** Rozetin ipucu metni (belge adı). */
  atifEtiketi?: (n: number) => string | undefined;
  /** i. alıntının doğrulama sonucu (true/false; bilinmiyorsa null). */
  alintiDurumu?: (i: number) => boolean | null;
};

export function HukukbotMarkdown({ metin, onAtif, atifEtiketi, alintiDurumu }: HukukbotMarkdownProps) {
  const bilesenler = useMemo<Components>(() => ({
    ...BILESENLER,
    a: ({ node: _node, href, ...p }) => {
      if (href?.startsWith(ATIF_HREF_ONEKI)) {
        const n = Number(href.slice(ATIF_HREF_ONEKI.length));
        const etiket = atifEtiketi?.(n);
        return (
          <button
            type="button"
            data-testid="atif-rozeti"
            data-atif={n}
            onClick={() => onAtif?.(n)}
            title={etiket ? `Kaynak ${n}: ${etiket}` : `Kaynak ${n}`}
            aria-label={etiket ? `Kaynak ${n}: ${etiket}` : `Kaynak ${n}`}
            className="relative -top-[0.4em] ml-0.5 inline-grid place-items-center min-w-[1.35em] h-[1.35em] px-[0.3em] rounded-full bg-[var(--brand-soft)] border border-[var(--border)] text-[10px] leading-none font-semibold tabular-nums text-[var(--brand)] hover:border-[var(--brand)] transition-colors align-baseline"
          >
            {n}
          </button>
        );
      }
      if (href?.startsWith(ALINTI_HREF_ONEKI)) {
        const durum = alintiDurumu?.(Number(href.slice(ALINTI_HREF_ONEKI.length))) ?? null;
        return (
          <q
            data-testid="alinti-metin"
            data-dogrulandi={durum === null ? undefined : String(durum)}
            title={
              durum === false
                ? "Bu alıntı belge metninde birebir bulunamadı; belgeyi açıp kontrol edin."
                : durum === true
                  ? "Alıntı belge metninde birebir bulundu."
                  : undefined
            }
            className={`italic px-1 rounded-[3px] bg-[var(--bg-sunken)] text-[var(--fg)] ${
              durum === false ? "underline decoration-wavy decoration-tone-caution underline-offset-4" : ""
            }`}
          >
            {p.children}
          </q>
        );
      }
      return <DisBaglanti href={href} {...p} />;
    },
  }), [onAtif, atifEtiketi, alintiDurumu]);

  return (
    <div className="hukukbot-markdown text-[15px] leading-[1.7] text-[var(--fg)] break-words min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[hamHtmlMetne]} components={bilesenler}>
        {metin}
      </ReactMarkdown>
    </div>
  );
}
