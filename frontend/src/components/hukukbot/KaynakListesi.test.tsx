// @vitest-environment jsdom
// KaynakListesi atıf doğrulaması (hukbot `citation_check`, 28.09): aramada gelmeyen atıf → "Atıf doğrulanamadı"
// rozeti + üst uyarı; belgede bulunamayan alıntı işaretlenir; aramada gelip kullanılmayan kaynak "Cevapta
// kullanılmadı"; doğrulama alanları olmayan ESKİ mesajda rozet/uyarı yok, önizleme metni aynen görünür.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { KaynakListesi } from "./KaynakListesi";

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

function ciz(kaynaklar: HukukbotKaynak[]) {
  act(() => kok.render(<KaynakListesi kaynaklar={kaynaklar} onIndir={() => {}} />));
}

const kaynak = (ek: Partial<HukukbotKaynak>): HukukbotKaynak => ({
  file_display_name: "Karar",
  filename: "KARAR.pdf",
  text_preview: "önizleme metni",
  ...ek,
});

const say = (testId: string) => kap.querySelectorAll(`[data-testid="${testId}"]`).length;

describe("KaynakListesi atıf doğrulaması", () => {
  it("aramada getirilen, alıntısı doğrulanan kaynak: olumlu rozet, uyarı yok", () => {
    ciz([
      kaynak({
        aramada_getirildi: true,
        metinde_atif: true,
        alintilar: [{ metin: "davanın usulden reddine", dogrulandi: true }],
      }),
    ]);
    expect(say("kaynak-dogrulandi")).toBe(1);
    expect(say("hukukbot-dogrulama-uyarisi")).toBe(0);
    expect(kap.textContent).toContain("“davanın usulden reddine”");
    expect(kap.textContent).toContain("belgede var");
    // alıntı varsa önizleme yerine alıntı gösterilir
    expect(kap.textContent).not.toContain("önizleme metni");
  });

  it("aramada gelmeyen atıf ve bulunamayan alıntı işaretlenir, üstte sayılı uyarı", () => {
    ciz([
      kaynak({ filename: "UYDURMA.pdf", aramada_getirildi: false, metinde_atif: true }),
      kaynak({
        filename: "A.pdf",
        aramada_getirildi: true,
        metinde_atif: true,
        alintilar: [{ metin: "hiç yazılmamış cümle", dogrulandi: false, benzerlik: 0.1 }],
      }),
    ]);
    expect(say("kaynak-dogrulanamadi")).toBe(1);
    expect(say("alinti-bulunamadi")).toBe(1);
    const uyari = kap.querySelector('[data-testid="hukukbot-dogrulama-uyarisi"]');
    expect(uyari?.textContent).toContain("2 kaynakta");
  });

  it("aramada gelip cevapta kullanılmayan kaynak ayrı etiketlenir", () => {
    ciz([kaynak({ aramada_getirildi: true, metinde_atif: false })]);
    expect(say("kaynak-kullanilmadi")).toBe(1);
    expect(say("kaynak-dogrulandi")).toBe(0);
  });

  it("arama izi yoksa (null) hüküm verilmez: rozet ve uyarı yok", () => {
    ciz([kaynak({ aramada_getirildi: null, metinde_atif: true, alintilar: [{ metin: "x", dogrulandi: null }] })]);
    expect(say("kaynak-dogrulandi") + say("kaynak-dogrulanamadi") + say("hukukbot-dogrulama-uyarisi")).toBe(0);
  });

  it("doğrulama alanı olmayan eski mesaj: eskisi gibi ad + önizleme", () => {
    ciz([kaynak({})]);
    expect(kap.textContent).toContain("önizleme metni");
    expect(say("kaynak-dogrulandi") + say("kaynak-dogrulanamadi") + say("kaynak-kullanilmadi")).toBe(0);
    expect(say("hukukbot-dogrulama-uyarisi")).toBe(0);
  });
});
