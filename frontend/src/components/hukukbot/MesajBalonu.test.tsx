// @vitest-environment jsdom
// Model mesajında atıf rozetleri (28.09): "(Kaynak: …pdf)" metinden kalkar, yerine numaralı rozet; kaynak kartı aynı
// numarayı taşır ve numara sırasıyla öne gelir (anılmayan kart numarasız, arkada); rozet tıklaması kartı vurgular.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { HukukbotKaynak } from "@/types/hukukbot";
import { MesajBalonu } from "./MesajBalonu";

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

const ICERIK =
  "- **Sevk Sorumluluğu:** Asıl sorumluluk acil servis hekimindedir (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).\n" +
  "- **Doktorlu Ambulans:** Sevkte doktor bulunmalıdır (Kaynak: KARAR_LEHE_048.pdf).\n" +
  "- **Sevk Gecikmeleri:** Gecikme hekime yüklenemez (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).";

function ciz(sources: HukukbotKaynak[]) {
  act(() =>
    kok.render(
      <MesajBalonu mesaj={{ anahtar: "m1", role: "model", content: ICERIK, sources }} onIndir={() => {}} />,
    ),
  );
}

describe("MesajBalonu atıf rozetleri", () => {
  it("ham dosya adları metinden kalkar, rozetler ilk geçiş sırasıyla numaralı", () => {
    ciz([kaynak("KARAR_LEHE_048.pdf"), kaynak("2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf"), kaynak("BASKA.pdf")]);
    const yanit = kap.querySelector("[data-testid='hukukbot-yanit']")!;
    expect(yanit.textContent).not.toContain("Kaynak:");
    expect(yanit.textContent).not.toContain(".pdf");
    const rozetler = Array.from(yanit.querySelectorAll("[data-testid='atif-rozeti']"));
    expect(rozetler.map((r) => r.textContent)).toEqual(["1", "2", "1"]);
    expect(rozetler[1].getAttribute("title")).toBe("Kaynak 2: KARAR_LEHE_048.pdf");
  });

  it("kartlar rozet numarasıyla, numara sırasıyla; anılmayan kart numarasız ve sonda", () => {
    ciz([kaynak("BASKA.pdf"), kaynak("KARAR_LEHE_048.pdf"), kaynak("2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf")]);
    const kartlar = Array.from(kap.querySelectorAll("[data-testid='kaynak-karti']"));
    expect(kartlar.map((k) => k.getAttribute("data-atif"))).toEqual(["1", "2", null]);
    expect(kartlar[0].textContent).toContain("BILIRKISI");
    expect(kartlar[2].textContent).toContain("BASKA.pdf");
  });

  it("rozet tıklaması aynı numaralı kartı vurgular, kısa süre sonra söner", () => {
    vi.useFakeTimers();
    ciz([kaynak("2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf"), kaynak("KARAR_LEHE_048.pdf")]);
    const rozet = kap.querySelector<HTMLButtonElement>("[data-testid='atif-rozeti'][data-atif='2']")!;
    act(() => rozet.click());
    const kart = kap.querySelector("[data-testid='kaynak-karti'][data-atif='2']")!;
    expect(kart.className).toContain("border-[var(--brand)]");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(kart.className).not.toContain("border-[var(--brand)]");
  });

  it("kaynak listesi henüz gelmemişken (akış) rozet yine çıkar, ipucu metindeki ad", () => {
    ciz([]);
    const rozet = kap.querySelector("[data-testid='atif-rozeti']")!;
    expect(rozet.getAttribute("title")).toBe("Kaynak 1: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf");
    expect(kap.querySelector("[data-testid='hukukbot-kaynaklar']")).toBeNull();
  });
});
