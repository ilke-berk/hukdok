// @vitest-environment jsdom
// Tezgah — "Rapor yaz" akışı örnek adaptörle uçtan uca: dava seç → künye/belge/emsal gelir → onaylı yazım →
// bölümler ve madde rozetleri (dayanak kuralı) → düzenle → alandan çıkınca yeniden denetim → dayanak vurgusu →
// muallak sınırı → Word (önizlemede bilgi). Taslağı silen eylemler onay ister.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const confirmMock = vi.hoisted(() => ({ fn: vi.fn(async (_opts: unknown) => true) }));
vi.mock("@/hooks/useConfirm", () => ({ useConfirm: () => confirmMock.fn }));

import { Tezgah } from "./Tezgah";
import { LEXIS_WORD_ORNEK_MESAJI, ornekDurumuSifirla, ornekGecikmeAyarla } from "@/lib/lexisApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;

async function bekle(tur = 12) {
  for (let i = 0; i < tur; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

async function ciz() {
  await act(async () => {
    kok.render(
      <MemoryRouter>
        <Tezgah />
      </MemoryRouter>,
    );
  });
  await bekle();
}

function dugme(etiket: string, kok_: ParentNode = document.body): HTMLButtonElement {
  const d = Array.from(kok_.querySelectorAll<HTMLButtonElement>("button")).find(
    (b) => b.getAttribute("aria-label") === etiket || b.textContent?.trim() === etiket,
  );
  if (!d) throw new Error(`düğme yok: ${etiket}`);
  return d;
}

async function tikla(el: HTMLElement) {
  await act(async () => {
    el.click();
  });
  await bekle();
}

/** React kontrollü alanına değer yazar (native setter + input olayı). */
async function yaz(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, deger: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

async function cik(el: HTMLElement) {
  await act(async () => {
    el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  });
  await bekle();
}

const test = <T extends HTMLElement = HTMLElement>(id: string) => kap.querySelector<T>(`[data-testid="${id}"]`);
const maddeler = () => Array.from(kap.querySelectorAll<HTMLElement>('[data-testid="lexis-madde"]'));
const rozetler = (madde: HTMLElement) =>
  Array.from(madde.querySelectorAll('[data-testid="lexis-madde-rozetleri"] > span')).map((s) => s.textContent);
const alan = <T extends HTMLElement>(etiket: string) => kap.querySelector<T>(`[aria-label="${etiket}"]`)!;

async function davaSec(ofisNo: string) {
  const sonuc = Array.from(test("lexis-dava-sonuclari")!.querySelectorAll("button")).find((b) => b.textContent?.includes(ofisNo))!;
  await tikla(sonuc);
}

async function taslakYaz(ofisNo: string) {
  await davaSec(ofisNo);
  await tikla(dugme("Taslağı yaz"));
}

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  confirmMock.fn.mockReset();
  confirmMock.fn.mockResolvedValue(true);
  Object.values(toastMocks).forEach((m) => m.mockReset());
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("Tezgah — dosya bölgesi", () => {
  it("dava seçilmeden boş durum ve dava listesi görünür", async () => {
    await ciz();
    expect(kap.textContent).toContain("Rapor yazılacak davayı seçin");
    expect(test("lexis-dava-sonuclari")!.querySelectorAll("button")).toHaveLength(4);
    expect(test("lexis-kunye")).toBeNull();
  });

  it("dava seçilince künye, belgeler ve puanlı emsaller gelir; taslak henüz yok", async () => {
    await ciz();
    await davaSec("ANADOLU-9001");
    expect(test("lexis-secili-dava")!.textContent).toContain("ANADOLU-9001-DR.ORNEK1-HUK");
    expect(test("lexis-kunye")!.textContent).toContain("Ankara 5. Tüketici Mahkemesi");
    // Kart ↔ belge çelişkisi sessizce çözülmez
    expect(test("lexis-kunye")!.textContent).toContain("kartta 150.000,00 TL, belgede 200.000,00 TL");
    expect(test("lexis-belgeler")!.textContent).toContain("4/4 seçili");
    const emsaller = test("lexis-emsaller")!.querySelectorAll("li");
    expect(emsaller).toHaveLength(3);
    expect(emsaller[0].textContent).toContain("olay: Yanık");
    expect(test("lexis-hazirlik")).not.toBeNull();
    expect(test("lexis-taslak-basligi")!.textContent).toBe("ANADOLU-9001-DR.ORNEK1-HUK");
  });

  it("eksik belge uyarılır ve HukuDok yüklemesine bağlanır; emsal çıkarılabilir", async () => {
    await ciz();
    await davaSec("AK-9002");
    const eksik = test("lexis-eksik-belgeler")!;
    expect(eksik.textContent).toContain("Poliçe");
    expect(eksik.querySelector("a")!.getAttribute("href")).toBe("/upload");

    const ilk = test("lexis-emsaller")!.querySelector("li")!;
    await tikla(dugme("Emsali çıkar: 9.2005", ilk));
    expect(test("lexis-emsaller")!.querySelectorAll("li")).toHaveLength(2);
  });
});

describe("Tezgah — taslak yazımı", () => {
  it("yazımdan önce modele ne gideceği onaylatılır; vazgeçilirse yazılmaz", async () => {
    confirmMock.fn.mockResolvedValue(false);
    await ciz();
    await taslakYaz("ANADOLU-9001");
    expect(confirmMock.fn).toHaveBeenCalledTimes(1);
    const secenekler = confirmMock.fn.mock.calls[0][0] as { title: string; details: { label: string; value: string }[] };
    expect(secenekler.title).toBe("Taslak yazılacak");
    expect(secenekler.details[0].value).toContain("4 belge");
    expect(secenekler.details[1].value).toBe("3 rapor (maskeli)");
    expect(maddeler()).toHaveLength(0);
    expect(test("lexis-hazirlik")).not.toBeNull();
  });

  it("iskeletin bölümleri yazılır; her madde dayanak rozetini alır", async () => {
    await ciz();
    await taslakYaz("ANADOLU-9001");

    expect(test("lexis-uretim-seridi")).toBeNull();
    expect(test("lexis-bolum-gezgini")!.querySelectorAll("button")).toHaveLength(8);
    expect(test("lexis-bolum-hasar")!.querySelectorAll("input")).toHaveLength(13);
    expect(test("lexis-bolum-iddia")!.querySelectorAll("textarea")).toHaveLength(2);
    expect(test("lexis-bolum-iddia")!.textContent).toContain("Kaynak: Dava dilekçesi");

    const m = maddeler();
    expect(m).toHaveLength(6);
    expect(rozetler(m[0])).toEqual(["Doğrulandı"]);
    expect(rozetler(m[2])).toEqual(["Emsalden taşınma"]);
    expect(rozetler(m[3])).toEqual(["Dayanaksız", "Belge yokluğu iddiası"]);
    expect(rozetler(m[4])).toEqual(["Alıntı dosyada yok"]);
    expect(rozetler(m[5])).toEqual(["Kalıp"]);

    // Uyarı paneli ve çıktı çubuğu denetim sonucunu taşır
    expect(test("lexis-uyarilar")!.textContent).toContain("Düzeltilmeli · 3");
    expect(test("lexis-cikti-cubugu")!.textContent).toContain("3 düzeltilmeli");
    // Gezginde değerlendirme bölümünün uyarı sayısı
    expect(test("lexis-bolum-gezgini")!.textContent).toContain("!4");
  });

  it("madde düzenlenince 'denetlenmedi' olur; alandan çıkınca yeniden denetlenir", async () => {
    await ciz();
    await taslakYaz("ANADOLU-9001");
    const alinti = alan<HTMLTextAreaElement>("Madde 5 dayanak alıntısı");
    await yaz(alinti, "tedavinin zamanında başlatıldığı ifade edilmiştir");
    expect(rozetler(maddeler()[4])).toEqual(["Denetlenmedi"]);
    expect(test("lexis-cikti-cubugu")!.textContent).toContain("Taslak değişti");

    await cik(alinti);
    expect(rozetler(maddeler()[4])).toEqual(["Doğrulandı"]);
    expect(test("lexis-uyarilar")!.textContent).toContain("Düzeltilmeli · 2");
  });

  it("madde silinince sıra ve uyarılar hemen güncellenir", async () => {
    await ciz();
    await taslakYaz("ANADOLU-9001");
    await tikla(dugme("Madde 4: sil"));
    const m = maddeler();
    expect(m).toHaveLength(5);
    expect(rozetler(m[3])).toEqual(["Alıntı dosyada yok"]);
    expect(test("lexis-uyarilar")!.textContent).not.toContain("belgenin bulunmadığı");
  });

  it("'Kaynakta göster' alıntıyı kaynak paragrafta vurgular", async () => {
    await ciz();
    await taslakYaz("ANADOLU-9001");
    await tikla(dugme("Kaynakta göster", maddeler()[1]));
    const dayanak = test("lexis-dayanak")!;
    expect(dayanak.querySelector("mark")!.textContent).toBe("uygulamada tıbbi hata saptanmadığı");
    expect(dayanak.textContent).toContain("Tıbbi Görüş · paragraf 2");
    expect(maddeler()[1].getAttribute("data-secili")).toBe("1");
  });

  it("muallak önerisi dayanağıyla gösterilir; talebi aşan kesin tutar hata verir", async () => {
    await ciz();
    await taslakYaz("ANADOLU-9001");
    const muallak = test("lexis-muallak")!;
    expect(muallak.textContent).toContain("Emsal raporlar");
    expect(muallak.textContent).toContain("120.000,00 TL");
    expect(test("lexis-muallak-dayanak")!.querySelectorAll("tbody tr")).toHaveLength(2);

    const manevi = Array.from(muallak.querySelectorAll("input"))[1];
    await yaz(manevi, "250.000");
    await cik(manevi);
    expect(test("lexis-uyarilar")!.textContent).toContain("Muallak manevi talebi aşıyor");

    await tikla(dugme("Öneriye dön", muallak));
    expect(test("lexis-uyarilar")!.textContent).not.toContain("talebi aşıyor");
  });

  it("Word indir önizlemede bilgi verir, hata saymaz", async () => {
    await ciz();
    await taslakYaz("AXA-9004");
    expect(test("lexis-cikti-cubugu")!.textContent).toContain("Denetim temiz");
    await tikla(dugme("Word indir"));
    expect(toastMocks.info).toHaveBeenCalledWith(LEXIS_WORD_ORNEK_MESAJI);
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("taslak varken künye değişimi onay ister; reddedilirse taslak kalır, kabul edilirse silinir", async () => {
    await ciz();
    await taslakYaz("AK-9002");
    expect(maddeler()).toHaveLength(4);
    const iskelet = Array.from(test("lexis-kunye")!.querySelectorAll("select"))[2];

    confirmMock.fn.mockResolvedValueOnce(false);
    await yaz(iskelet, "KISA");
    await bekle();
    expect((confirmMock.fn.mock.calls.at(-1)![0] as { title: string }).title).toBe("Taslak silinecek");
    expect(maddeler()).toHaveLength(4);

    await yaz(iskelet, "KISA");
    await bekle();
    expect(maddeler()).toHaveLength(0);
    expect(test("lexis-bolum-gezgini")!.querySelectorAll("button")).toHaveLength(4);
    expect(dugme("Taslağı yaz")).toBeDefined();
  });

  it("'Durdur' akışı keser; yazılmamış bölümler boş kalır", async () => {
    ornekGecikmeAyarla(15);
    await ciz();
    await bekle(30);
    await davaSec("ANADOLU-9001");
    await bekle(30);
    await act(async () => dugme("Taslağı yaz").click());
    await bekle(3);
    expect(test("lexis-uretim-seridi")).not.toBeNull();
    await tikla(dugme("Durdur"));
    expect(test("lexis-uretim-seridi")).toBeNull();
    expect(maddeler()).toHaveLength(0);
    expect(test("lexis-akis-hatasi")).toBeNull();
    expect(dugme("Yeniden yaz")).toBeDefined();
  });
});
