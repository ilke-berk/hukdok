import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Model yanıtı için markdown (G205) — `react-markdown` + `remark-gfm` (tablo, üstü çizili, görev listesi).
 * Ham HTML RENDER EDİLMEZ: `rehype-raw` yok; üstelik markdown içindeki ham HTML düğümleri (`raw`)
 * `hamHtmlMetne` eklentisiyle DÜZ METNE çevrilir → `<script>` vb. ekranda metin olarak görünür, DOM'a
 * etiket olarak girmez (sessizce kaybolmaz da: kullanıcı modelin ne yazdığını görür).
 * Link şemaları react-markdown'ın varsayılan `urlTransform`'undan geçer (javascript: vb. düşer).
 * Tipografi eklentisi yapılandırılı değil → öğe biçimleri tema token'larıyla burada verilir.
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

const BILESENLER: Components = {
  p: ({ node: _node, ...p }) => <p className="my-2 first:mt-0 last:mb-0 leading-[1.65]" {...p} />,
  a: ({ node: _node, ...p }) => (
    <a
      {...p}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[var(--brand)] underline underline-offset-2 break-words hover:opacity-80"
    />
  ),
  ul: ({ node: _node, ...p }) => <ul className="my-2 pl-5 list-disc space-y-1" {...p} />,
  ol: ({ node: _node, ...p }) => <ol className="my-2 pl-5 list-decimal space-y-1" {...p} />,
  h1: ({ node: _node, ...p }) => <h3 className="mt-4 mb-2 font-display text-[18px] font-medium" {...p} />,
  h2: ({ node: _node, ...p }) => <h4 className="mt-4 mb-2 font-display text-[16px] font-medium" {...p} />,
  h3: ({ node: _node, ...p }) => <h5 className="mt-3 mb-1.5 text-[14px] font-semibold" {...p} />,
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

export function HukukbotMarkdown({ metin }: { metin: string }) {
  return (
    <div className="hukukbot-markdown text-[13.5px] text-[var(--fg)] break-words min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[hamHtmlMetne]} components={BILESENLER}>
        {metin}
      </ReactMarkdown>
    </div>
  );
}
