// @vitest-environment jsdom
// Model mesajı (28.09): "(Kaynak: …pdf)" metinden kalkar, yerine numaralı rozet; `[Alıntı: "..."]` ayrı stilli
// alıntı (doğrulanamayan uyarılı); kaynak kartları metnin altında DEĞİL — yalnız "Kaynaklar · N" düğmesi; rozet ve
// düğme `onKaynakAc(anahtar, n)` ile paneli açar.
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
});

const kaynak = (filename: string, ek: Partial<HukukbotKaynak> = {}): HukukbotKaynak => ({
  filename,
  file_display_name: filename,
  text_preview: "önizleme",
  ...ek,
});

const ICERIK =
  "- **Sevk Sorumluluğu:** Asıl sorumluluk acil servis hekimindedir (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).\n" +
  '- **Doktorlu Ambulans:** [Alıntı: "sevk sırasında ambulansta doktor bulunmalıdır"] (Kaynak: KARAR_LEHE_048.pdf).\n' +
  "- **Sevk Gecikmeleri:** Gecikme hekime yüklenemez (Kaynak: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf).";

function ciz(sources: HukukbotKaynak[], onKaynakAc = vi.fn()) {
  act(() =>
    kok.render(
      <MesajBalonu mesaj={{ anahtar: "m1", role: "model", content: ICERIK, sources }} onKaynakAc={onKaynakAc} />,
    ),
  );
  return onKaynakAc;
}

describe("MesajBalonu atıf rozetleri ve alıntılar", () => {
  it("ham dosya adları metinden kalkar, rozetler ilk geçiş sırasıyla numaralı; ipucu belge adı", () => {
    ciz([kaynak("KARAR_LEHE_048.pdf"), kaynak("2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf")]);
    const yanit = kap.querySelector("[data-testid='hukukbot-yanit']")!;
    expect(yanit.textContent).not.toContain("Kaynak:");
    expect(yanit.textContent).not.toContain(".pdf");
    const rozetler = Array.from(yanit.querySelectorAll("[data-testid='atif-rozeti']"));
    expect(rozetler.map((r) => r.textContent)).toEqual(["1", "2", "1"]);
    expect(rozetler[1].getAttribute("title")).toBe("Kaynak 2: KARAR_LEHE_048.pdf");
  });

  it("alıntı ayrı stilde; hukbot doğrulayamadıysa işaretli", () => {
    ciz([
      kaynak("KARAR_LEHE_048.pdf", {
        alintilar: [{ metin: "sevk sırasında ambulansta doktor bulunmalıdır", dogrulandi: false }],
      }),
    ]);
    const alinti = kap.querySelector("[data-testid='alinti-metin']")!;
    expect(alinti.textContent).toBe("sevk sırasında ambulansta doktor bulunmalıdır");
    expect(alinti.getAttribute("data-dogrulandi")).toBe("false");
    expect(kap.querySelector("[data-testid='hukukbot-yanit']")!.textContent).not.toContain("Alıntı:");
  });

  it("kaynak kartları metnin altında yok; 'Kaynaklar · N' düğmesi ve rozet paneli açar", () => {
    const ac = ciz([kaynak("KARAR_LEHE_048.pdf"), kaynak("2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf")]);
    expect(kap.querySelector("[data-testid='hukukbot-kaynaklar']")).toBeNull();
    const dugme = kap.querySelector<HTMLButtonElement>("[data-testid='kaynaklari-goster']")!;
    expect(dugme.textContent).toContain("Kaynaklar · 2");
    act(() => dugme.click());
    expect(ac).toHaveBeenLastCalledWith("m1", null);
    act(() => kap.querySelector<HTMLButtonElement>("[data-testid='atif-rozeti'][data-atif='2']")!.click());
    expect(ac).toHaveBeenLastCalledWith("m1", 2);
  });

  it("kaynak listesi henüz gelmemişken (akış) rozet yine çıkar, düğme yok", () => {
    ciz([]);
    expect(kap.querySelector("[data-testid='atif-rozeti']")!.getAttribute("title")).toBe(
      "Kaynak 1: 2026-07-29_BILIRKISI-RPR_25-19_S.Durdu_vd.pdf",
    );
    expect(kap.querySelector("[data-testid='kaynaklari-goster']")).toBeNull();
  });
});
