// @vitest-environment jsdom
// HukukbotMarkdown (G205) — model yanıtı react-markdown + remark-gfm: GFM tablosu gerçek <table> olur ve
// kaydırma kutusuna sarılır; ham HTML (rehype-raw YOK) DOM'a etiket olarak GİRMEZ, metin olarak görünür;
// javascript: linki düşer; linkler yeni sekmede noopener ile açılır.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { HukukbotMarkdown } from "./HukukbotMarkdown";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;

beforeEach(() => {
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

function ciz(metin: string) {
  act(() => kok.render(<HukukbotMarkdown metin={metin} />));
}

describe("HukukbotMarkdown", () => {
  it("GFM tablosunu <table> olarak çizer, kaydırma kutusuna sarar", () => {
    ciz("| Madde | Süre |\n| --- | --- |\n| HMK 345 | 2 hafta |\n| HMK 361 | 2 hafta |");
    const tablo = kap.querySelector("table");
    expect(tablo).not.toBeNull();
    expect(tablo?.closest("[data-testid='hukukbot-tablo-kutusu']")).not.toBeNull();
    const basliklar = Array.from(kap.querySelectorAll("th")).map((th) => th.textContent);
    expect(basliklar).toEqual(["Madde", "Süre"]);
    const hucreler = Array.from(kap.querySelectorAll("tbody td")).map((td) => td.textContent);
    expect(hucreler).toEqual(["HMK 345", "2 hafta", "HMK 361", "2 hafta"]);
  });

  it("ham <script> etiket olarak DOM'a girmez, metin olarak kalır", () => {
    ciz('Önce <script>alert("x")</script> sonra');
    expect(kap.querySelector("script")).toBeNull();
    expect(kap.textContent).toContain('<script>alert("x")</script>');
  });

  it("blok düzeyi ham HTML de metin kalır (etiket üretmez)", () => {
    ciz('<div onclick="alert(1)">tıkla</div>\n\n<img src=x onerror="alert(1)">');
    expect(kap.querySelector("img")).toBeNull();
    expect(kap.querySelector("[onclick]")).toBeNull();
    expect(kap.textContent).toContain('<div onclick="alert(1)">');
    expect(kap.textContent).toContain("<img src=x onerror=");
  });

  it("javascript: linki temizlenir; normal link yeni sekmede noopener ile açılır", () => {
    ciz("[kötü](javascript:alert(1)) ve [iyi](https://www.mevzuat.gov.tr)");
    const linkler = Array.from(kap.querySelectorAll("a"));
    const kotu = linkler.find((a) => a.textContent === "kötü");
    const iyi = linkler.find((a) => a.textContent === "iyi");
    expect(kotu?.getAttribute("href") ?? "").not.toMatch(/javascript:/i);
    expect(iyi?.getAttribute("href")).toBe("https://www.mevzuat.gov.tr");
    expect(iyi?.getAttribute("target")).toBe("_blank");
    expect(iyi?.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("kalın, liste ve satır içi kod markdown olarak çizilir", () => {
    ciz("**önemli**\n\n- bir\n- iki\n\n`HMK 1`");
    expect(kap.querySelector("strong")?.textContent).toBe("önemli");
    expect(kap.querySelectorAll("ul li")).toHaveLength(2);
    expect(kap.querySelector("code")?.textContent).toBe("HMK 1");
  });
});
