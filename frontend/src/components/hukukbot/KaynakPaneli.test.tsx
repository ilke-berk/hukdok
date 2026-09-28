// @vitest-environment jsdom
// Kaynak paneli (28.09): kart numaraları metindeki rozetlerle aynı, numara sırasıyla öne; anılmayan kart numarasız
// ve sonda; vurgu verilince o kart kısa süre vurgulanır; Kapat düğmesi `onKapat`.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { KaynakPaneli, type KaynakVurgusu } from "./KaynakPaneli";

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
  vi.useRealTimers();
});

const kaynak = (filename: string): HukukbotKaynak => ({ filename, file_display_name: filename, text_preview: "önizleme" });
const ICERIK = "A (Kaynak: BILIRKISI.pdf). B (Kaynak: KARAR_LEHE_048.pdf). C (Kaynak: BILIRKISI.pdf).";

function ciz(vurgu: KaynakVurgusu | null = null, onKapat = vi.fn()) {
  act(() =>
    kok.render(
      <KaynakPaneli
        mesaj={{
          anahtar: "m1",
          role: "model",
          content: ICERIK,
          sources: [kaynak("BASKA.pdf"), kaynak("KARAR_LEHE_048.pdf"), kaynak("BILIRKISI.pdf")],
        }}
        vurgu={vurgu}
        onKapat={onKapat}
        onIndir={() => {}}
      />,
    ),
  );
  return onKapat;
}

describe("KaynakPaneli", () => {
  it("kartlar rozet numarasıyla, numara sırasıyla; anılmayan numarasız ve sonda; başlıkta sayı", () => {
    ciz();
    expect(kap.textContent).toContain("Kaynaklar · 3");
    const kartlar = Array.from(kap.querySelectorAll("[data-testid='kaynak-karti']"));
    expect(kartlar.map((k) => k.getAttribute("data-atif"))).toEqual(["1", "2", null]);
    expect(kartlar[0].textContent).toContain("BILIRKISI.pdf");
    expect(kartlar[2].textContent).toContain("BASKA.pdf");
  });

  it("vurgu verilince o kart vurgulanır, kısa süre sonra söner; Kapat onKapat'ı çağırır", () => {
    vi.useFakeTimers();
    const kapat = ciz({ n: 2, tik: 1 });
    const kart = kap.querySelector("[data-testid='kaynak-karti'][data-atif='2']")!;
    expect(kart.className).toContain("border-[var(--brand)]");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(kart.className).not.toContain("border-[var(--brand)]");
    act(() => kap.querySelector<HTMLButtonElement>("[aria-label='Kaynak panelini kapat']")!.click());
    expect(kapat).toHaveBeenCalled();
  });
});
