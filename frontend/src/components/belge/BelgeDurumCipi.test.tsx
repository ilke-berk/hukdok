// @vitest-environment jsdom
// BelgeDurumCipi (G283): durum/yön/kaynak etiketleri Türkçe `aria-label` ile; alanlar yoksa GELEN/BELGE_HATTI/KESIN;
// küçük harf / İ-ı katlaması; bilinmeyen değer varsayılana düşer.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BelgeDurumCipi } from "./BelgeDurumCipi";
import { KAYNAK_ETIKETLERI } from "@/types/belge";

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

async function ciz(doc: { yon?: string | null; kaynak?: string | null; durum?: string | null }) {
  await act(async () => {
    kok.render(<BelgeDurumCipi doc={doc} />);
  });
  const cip = kap.querySelector<HTMLSpanElement>('[data-testid="belge-durum-cipi"]')!;
  const etiketler = Array.from(cip.querySelectorAll('[role="img"]')).map((e) => e.getAttribute("aria-label"));
  return { cip, etiketler };
}

describe("BelgeDurumCipi", () => {
  it("taslak + giden + PDF tezgâhı", async () => {
    const { cip, etiketler } = await ciz({ yon: "GIDEN", kaynak: "PDF_ARACLARI", durum: "TASLAK" });
    expect(cip.dataset).toMatchObject({ yon: "GIDEN", kaynak: "PDF_ARACLARI", durum: "TASLAK" });
    expect(etiketler).toEqual(["Taslak", "Giden belge", `Kaynak: ${KAYNAK_ETIKETLERI.PDF_ARACLARI}`]);
    expect(cip.textContent).toContain("Taslak");
  });

  it("alanlar yoksa Kesin · Gelen · Belge hattı (eski yanıt kırılmaz)", async () => {
    const { cip, etiketler } = await ciz({});
    expect(cip.dataset).toMatchObject({ yon: "GELEN", kaynak: "BELGE_HATTI", durum: "KESIN" });
    expect(etiketler).toEqual(["Kesin", "Gelen belge", `Kaynak: ${KAYNAK_ETIKETLERI.BELGE_HATTI}`]);
  });

  it("küçük harf ve bilinmeyen değerler: 'giden'/'kesin' tanınır, 'x' varsayılana düşer", async () => {
    const a = await ciz({ yon: "giden", kaynak: "arsiv_aktarim", durum: "kesin" });
    expect(a.cip.dataset).toMatchObject({ yon: "GIDEN", kaynak: "ARSIV_AKTARIM", durum: "KESIN" });
    const b = await ciz({ yon: "x", kaynak: "y", durum: "z" });
    expect(b.cip.dataset).toMatchObject({ yon: "GELEN", kaynak: "BELGE_HATTI", durum: "KESIN" });
    for (const k of ["WORD", "TESLIM"] as const) {
      const c = await ciz({ kaynak: k });
      expect(c.etiketler[2]).toBe(`Kaynak: ${KAYNAK_ETIKETLERI[k]}`);
    }
  });
});
