// @vitest-environment jsdom
// HukukbotPage (G205) — `/hukukbot` sohbet sayfası. `hukukbotApi` nesnesi sahte (hata sınıfları GERÇEK):
// liste sabitlenenler üstte + sabitle/çöz sırayı değiştirir; silme ONAY ister (hayır → çağrı yok);
// `?s=<id>` o sohbeti açar, seçim URL'ye yazılır; yeni sohbette ilk soru önce oturum açar (URL'ye yazar),
// sonra `/ask` akışının parçaları ekrana kademeli düşer, kutu kilitli, kaynak "PDF'i aç" → `indir(filename)`;
// Enter gönderir / Shift+Enter göndermez / boş gönderilmez; "Durdur" akışı keser; 429 Türkçe mesaj;
// model yanıtında markdown tablo çizilir, ham `<script>` metin kalır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";
import type { HukukbotAkisOlayi, HukukbotOturum, HukukbotOturumOzeti, HukukbotSoru } from "@/types/hukukbot";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

// lib/api → msalConfig yüklenmesin (hukukbotApi nesnesi zaten sahte).
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

const confirmMock = vi.hoisted(() => ({ fn: vi.fn(async (_opts: unknown) => true) }));
vi.mock("@/hooks/useConfirm", async () => {
  const React = await import("react");
  return {
    ConfirmContext: React.createContext({ confirm: (opts: unknown) => confirmMock.fn(opts) }),
    useConfirm: () => confirmMock.fn,
  };
});

const apiMock = vi.hoisted(() => ({
  oturumlariListele: vi.fn(),
  oturumGetir: vi.fn(),
  oturumOlustur: vi.fn(),
  oturumGuncelle: vi.fn(),
  oturumSil: vi.fn(),
  ask: vi.fn(),
  indir: vi.fn(),
  hukudokBelgesiniAc: vi.fn(),
}));
vi.mock("@/lib/hukukbotApi", async (importOriginal) => {
  const gercek = await importOriginal<typeof import("@/lib/hukukbotApi")>();
  return { ...gercek, hukukbotApi: apiMock };
});

import HukukbotPage from "./HukukbotPage";
import { OdakModuContext } from "@/hooks/useOdakModu";
import { HUKUKBOT_HIZ_MESAJI, HukukbotApiError, HukukbotHizSiniriError } from "@/lib/hukukbotApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LISTE: HukukbotOturumOzeti[] = [
  // Bilerek sırasız: sayfa kendisi sıralar.
  { id: "o-yeni", title: "Kira tespit", created_at: "2026-09-20T10:00:00Z", is_pinned: false, preview: "son" },
  { id: "o-sabit", title: "Tazminat hesabı", created_at: "2026-08-01T10:00:00Z", is_pinned: true, preview: null },
  { id: "o-eski", title: "İş davası", created_at: "2026-09-01T10:00:00Z", is_pinned: false, preview: null },
];

let kap: HTMLDivElement;
let kok: Root;
let konum = "";

function KonumIzleyici() {
  const l = useLocation();
  konum = `${l.pathname}${l.search}`;
  return null;
}

async function bekle(tur = 5) {
  for (let i = 0; i < tur; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

async function ciz(adres = "/hukukbot") {
  await act(async () => {
    kok.render(
      <MemoryRouter initialEntries={[adres]}>
        <KonumIzleyici />
        <HukukbotPage />
      </MemoryRouter>,
    );
  });
  await bekle();
}

const basliklar = () =>
  Array.from(kap.querySelectorAll("aside [data-testid='hukukbot-oturum-baslik']")).map((e) => e.textContent);

function dugme(etiket: string): HTMLButtonElement {
  const d = Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find(
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

/** Satır eylemleri "⋯" menüsündedir (28.09): önce o satırın menüsü açılır, sonra eylem tıklanır. */
async function eylem(etiket: string) {
  const baslik = etiket.slice(etiket.indexOf(": ") + 2);
  await tikla(dugme(`Sohbet eylemleri: ${baslik}`));
  await tikla(dugme(etiket));
}

const soruKutusu = () => kap.querySelector<HTMLTextAreaElement>("[data-testid='hukukbot-soru']")!;

async function yaz(metin: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  await act(async () => {
    setter.call(soruKutusu(), metin);
    soruKutusu().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function enter(shiftKey = false) {
  await act(async () => {
    soruKutusu().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey, bubbles: true, cancelable: true }));
  });
  await bekle();
}

/** Test elle besler: `ver(olay)` bir olay yollar, `bitir()` akışı kapatır; iptalde AbortError fırlar. */
function kontrolluAkis() {
  const kuyruk: HukukbotAkisOlayi[] = [];
  let uyandir: (() => void) | null = null;
  let bitti = false;
  const durt = () => {
    uyandir?.();
    uyandir = null;
  };
  async function* uret(_soru: HukukbotSoru, secenek: { signal?: AbortSignal } = {}) {
    while (true) {
      if (secenek.signal?.aborted) throw new DOMException("iptal", "AbortError");
      const olay = kuyruk.shift();
      if (olay) {
        yield olay;
        continue;
      }
      if (bitti) return;
      await new Promise<void>((r) => {
        uyandir = r;
        secenek.signal?.addEventListener("abort", () => r(), { once: true });
      });
    }
  }
  return {
    uret,
    ver: async (olay: HukukbotAkisOlayi) => {
      kuyruk.push(olay);
      durt();
      await bekle();
    },
    bitir: async () => {
      bitti = true;
      durt();
      await bekle();
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  confirmMock.fn.mockImplementation(async () => true);
  apiMock.oturumlariListele.mockResolvedValue(LISTE.map((o) => ({ ...o })));
  apiMock.oturumGuncelle.mockImplementation(async (id: string, d: Partial<HukukbotOturum>) => ({
    id,
    title: d.title ?? "x",
    created_at: "2026-09-01T10:00:00Z",
    is_pinned: d.is_pinned ?? false,
    messages: [],
  }));
  apiMock.oturumSil.mockResolvedValue(undefined);
  apiMock.indir.mockResolvedValue(undefined);
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("HukukbotPage — sohbet listesi", () => {
  it("lazy import'a uygun default export", () => {
    expect(typeof HukukbotPage).toBe("function");
  });

  it("sabitlenenler üstte, sonra en yeni; sabitle/çöz sırayı değiştirir ve kaydeder", async () => {
    await ciz();
    expect(basliklar()).toEqual(["Tazminat hesabı", "Kira tespit", "İş davası"]);

    await eylem("Sabitle: İş davası");
    expect(apiMock.oturumGuncelle).toHaveBeenCalledWith("o-eski", { is_pinned: true });
    // İki sabit: en yeni (09-01) önce, sonra 08-01; ardından sabitsiz.
    expect(basliklar()).toEqual(["İş davası", "Tazminat hesabı", "Kira tespit"]);

    await eylem("Sabitlemeyi kaldır: Tazminat hesabı");
    expect(apiMock.oturumGuncelle).toHaveBeenCalledWith("o-sabit", { is_pinned: false });
    expect(basliklar()).toEqual(["İş davası", "Kira tespit", "Tazminat hesabı"]);
  });

  it("sabitleme kaydedilemezse sıra geri döner ve hata bildirilir", async () => {
    apiMock.oturumGuncelle.mockRejectedValueOnce(new Error("ağ"));
    await ciz();
    await eylem("Sabitle: Kira tespit");
    expect(basliklar()).toEqual(["Tazminat hesabı", "Kira tespit", "İş davası"]);
    expect(toastMocks.error).toHaveBeenCalled();
  });

  it("silme ONAY ister: vazgeçilirse silinmez; onaylanırsa silinir", async () => {
    await ciz();
    confirmMock.fn.mockImplementationOnce(async () => false);
    await eylem("Sil: Kira tespit");
    expect(confirmMock.fn).toHaveBeenCalledTimes(1);
    expect(confirmMock.fn.mock.calls[0][0]).toMatchObject({ tone: "destructive", irreversible: true });
    expect(apiMock.oturumSil).not.toHaveBeenCalled();
    expect(basliklar()).toContain("Kira tespit");

    await eylem("Sil: Kira tespit");
    expect(apiMock.oturumSil).toHaveBeenCalledWith("o-yeni");
    expect(basliklar()).toEqual(["Tazminat hesabı", "İş davası"]);
    expect(toastMocks.success).toHaveBeenCalled();
  });

  it("başlık satır içinde düzenlenir, Enter kaydeder", async () => {
    await ciz();
    await eylem("Başlığı düzenle: İş davası");
    const girdi = kap.querySelector<HTMLInputElement>("input[aria-label='Sohbet başlığı']")!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => {
      setter.call(girdi, "İşe iade davası");
      girdi.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      girdi.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
    });
    await bekle();
    expect(apiMock.oturumGuncelle).toHaveBeenCalledWith("o-eski", { title: "İşe iade davası" });
    expect(basliklar()).toContain("İşe iade davası");
  });
});

describe("HukukbotPage — yeniden tasarım (28.09)", () => {
  it("kabuğu odak moduna alır; ☰ HUKDOK menüsünü açar; ayrılınca odak biter", async () => {
    const setOdak = vi.fn();
    const menuyuAc = vi.fn();
    await act(async () => {
      kok.render(
        <OdakModuContext.Provider value={{ odak: true, setOdak, menuyuAc }}>
          <MemoryRouter initialEntries={["/hukukbot"]}>
            <HukukbotPage />
          </MemoryRouter>
        </OdakModuContext.Provider>,
      );
    });
    await bekle();
    expect(setOdak).toHaveBeenLastCalledWith(true);
    const menuDugmeleri = Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).filter(
      (b) => b.getAttribute("aria-label") === "HUKDOK menüsünü aç",
    );
    expect(menuDugmeleri.length).toBeGreaterThan(0);
    await tikla(menuDugmeleri[0]);
    expect(menuyuAc).toHaveBeenCalledTimes(1);
    act(() => kok.unmount());
    expect(setOdak).toHaveBeenLastCalledWith(false);
    kok = createRoot(kap);
  });

  it("geçmiş raya daralır, tercih saklanır ve yeniden açılışta korunur", async () => {
    await ciz();
    await tikla(dugme("Sohbet geçmişini daralt"));
    expect(kap.querySelector("aside[aria-label='Sohbet listesi']")?.getAttribute("data-daraltilmis")).toBe("1");
    expect(basliklar()).toEqual([]);
    expect(window.localStorage.getItem("hukdok.hukukbot.gecmisDaraltilmis")).toBe("1");

    act(() => kok.unmount());
    kok = createRoot(kap);
    await ciz();
    expect(kap.querySelector("[data-testid='hukukbot-ray']")).not.toBeNull();
    await tikla(dugme("Sohbet geçmişini aç"));
    expect(basliklar()).toEqual(["Tazminat hesabı", "Kira tespit", "İş davası"]);
    expect(window.localStorage.getItem("hukdok.hukukbot.gecmisDaraltilmis")).toBe("0");
  });

  it("liste araması başlıkta Türkçe harf duyarsız süzer; eşleşme yoksa bilgi verir", async () => {
    await ciz();
    const arama = kap.querySelector<HTMLInputElement>("[data-testid='hukukbot-oturum-arama']")!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    const ara = async (t: string) => {
      await act(async () => {
        setter.call(arama, t);
        arama.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };
    await ara("IS DAV");
    expect(basliklar()).toEqual(["İş davası"]);
    await ara("yok-böyle-bir-şey");
    expect(basliklar()).toEqual([]);
    expect(kap.querySelector("[data-testid='hukukbot-arama-bos']")).not.toBeNull();
  });

  it("örnek soru kutuyu doldurur ama GÖNDERMEZ", async () => {
    await ciz();
    const ornek = kap.querySelector<HTMLButtonElement>("[data-testid='hukukbot-ornekler'] button")!;
    await tikla(ornek);
    expect(soruKutusu().value).toBe(ornek.textContent);
    expect(apiMock.oturumOlustur).not.toHaveBeenCalled();
    expect(apiMock.ask).not.toHaveBeenCalled();
  });
});

describe("HukukbotPage — URL ve mesajlar", () => {
  it("?s=<id> o sohbeti açar; model yanıtı markdown tablo çizer, ham <script> metin kalır", async () => {
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni",
      title: "Kira tespit",
      created_at: "2026-09-20T10:00:00Z",
      is_pinned: false,
      messages: [
        { role: "user", content: "Süreler?" },
        { role: "model", content: "| Yol | Süre |\n| --- | --- |\n| İstinaf | 2 hafta |\n\n<script>alert(1)</script>" },
      ],
    } satisfies HukukbotOturum);
    await ciz("/hukukbot?s=o-yeni");
    expect(apiMock.oturumGetir).toHaveBeenCalledWith("o-yeni", expect.any(AbortSignal));
    expect(kap.querySelector("[data-testid='hukukbot-aktif-baslik']")?.textContent).toBe("Kira tespit");
    const yanit = kap.querySelector("[data-testid='hukukbot-mesaj-model']")!;
    expect(yanit.querySelector("table td")?.textContent).toBe("İstinaf");
    expect(yanit.querySelector("script")).toBeNull();
    expect(yanit.textContent).toContain("<script>alert(1)</script>");
  });

  it("listeden seçim URL'ye yazılır ve o sohbet yüklenir", async () => {
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-eski",
      title: "İş davası",
      created_at: "2026-09-01T10:00:00Z",
      is_pinned: false,
      messages: [{ role: "user", content: "kıdem tazminatı" }],
    } satisfies HukukbotOturum);
    await ciz();
    const satir = Array.from(kap.querySelectorAll<HTMLButtonElement>("aside li button")).find(
      (b) => b.textContent?.includes("İş davası"),
    )!;
    await tikla(satir);
    expect(konum).toBe("/hukukbot?s=o-eski");
    expect(apiMock.oturumGetir).toHaveBeenCalledWith("o-eski", expect.any(AbortSignal));
    expect(kap.querySelector("[data-testid='hukukbot-mesaj-kullanici']")?.textContent).toBe("kıdem tazminatı");
  });
});

describe("HukukbotPage — soru gönderme ve akış", () => {
  it("yeni sohbet: önce oturum açılır (URL'ye yazılır), akış parçaları kademeli düşer, kaynak PDF'i indir() ile açılır", async () => {
    const akis = kontrolluAkis();
    apiMock.ask.mockImplementation(akis.uret);
    apiMock.oturumOlustur.mockResolvedValue({
      id: "o-taze",
      title: "Kira artış oranı nedir?",
      created_at: "2026-09-26T10:00:00Z",
      is_pinned: false,
      messages: [],
    } satisfies HukukbotOturum);
    await ciz();

    await yaz("  Kira artış oranı nedir?  ");
    await enter();

    expect(apiMock.oturumOlustur).toHaveBeenCalledWith("Kira artış oranı nedir?");
    expect(konum).toBe("/hukukbot?s=o-taze");
    expect(apiMock.oturumGetir).not.toHaveBeenCalled(); // kendi açtığımız oturum yeniden çekilmez
    expect(apiMock.ask).toHaveBeenCalledTimes(1);
    const [soru, secenek] = apiMock.ask.mock.calls[0];
    expect(soru).toEqual({ question: "Kira artış oranı nedir?", history: null });
    expect(secenek.sessionId).toBe("o-taze");
    expect(secenek.signal).toBeInstanceOf(AbortSignal);
    expect(kap.querySelector("[data-testid='hukukbot-mesaj-kullanici']")?.textContent).toBe("Kira artış oranı nedir?");
    expect(soruKutusu().disabled).toBe(true);
    expect(soruKutusu().value).toBe("");
    expect(basliklar()[1]).toBe("Kira artış oranı nedir?"); // sabitin altında, en yeni

    await akis.ver({ type: "content", data: "Kira artışı " });
    expect(kap.querySelector("[data-testid='hukukbot-yanit']")?.textContent).toContain("Kira artışı");
    await akis.ver({ type: "content", data: "**TÜFE** ile sınırlıdır." });
    const yanit = kap.querySelector("[data-testid='hukukbot-yanit']")!;
    expect(yanit.textContent).toContain("Kira artışı TÜFE ile sınırlıdır.");
    expect(yanit.querySelector("strong")?.textContent).toBe("TÜFE");
    expect(soruKutusu().disabled).toBe(true);

    await akis.ver({
      type: "sources",
      data: [{ file_display_name: "TBK 344", filename: "tbk_344.pdf", text_preview: "Kira bedelinin belirlenmesi" }],
    });
    await akis.bitir();
    expect(soruKutusu().disabled).toBe(false);
    expect(kap.querySelector("[data-testid='hukukbot-kaynaklar']")?.textContent).toContain("TBK 344");

    await tikla(dugme("PDF'i aç: TBK 344"));
    expect(apiMock.indir).toHaveBeenCalledWith("tbk_344.pdf");
  });

  it("arama sürerken status olayları 'yazıyor' yerine gösterilir; ilk metinle kaybolur, hata sayılmaz", async () => {
    const akis = kontrolluAkis();
    apiMock.ask.mockImplementation(akis.uret);
    apiMock.oturumOlustur.mockResolvedValue({
      id: "o-durum",
      title: "Menenjit",
      created_at: "2026-09-28T10:00:00Z",
      is_pinned: false,
      messages: [],
    } satisfies HukukbotOturum);
    await ciz();
    await yaz("Menenjit davası var mı?");
    await enter();

    const durum = () => kap.querySelector("[data-testid='hukukbot-durum']")?.textContent;
    expect(durum()).toBe("Hukukbot yazıyor...");
    await akis.ver({ type: "status", data: "Arşiv taranıyor: menenjit geç tanı" });
    expect(durum()).toBe("Arşiv taranıyor: menenjit geç tanı");
    await akis.ver({ type: "status", data: "4 belgeden 9 bölüm bulundu, cevap yazılıyor…" });
    expect(durum()).toBe("4 belgeden 9 bölüm bulundu, cevap yazılıyor…");

    await akis.ver({ type: "content", data: "Karar bulundu." });
    expect(durum()).toBeUndefined();
    expect(kap.querySelector("[data-testid='hukukbot-yanit']")?.textContent).toContain("Karar bulundu.");
    await akis.bitir();
    expect(kap.querySelector("[data-testid='hukukbot-hata']")).toBeNull();
  });

  it("mevcut sohbette ikinci soru geçmişle ve oturum kimliğiyle gider; yeni oturum açılmaz", async () => {
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni",
      title: "Kira tespit",
      created_at: "2026-09-20T10:00:00Z",
      is_pinned: false,
      messages: [
        { role: "user", content: "ilk" },
        { role: "model", content: "cevap" },
      ],
    } satisfies HukukbotOturum);
    const akis = kontrolluAkis();
    apiMock.ask.mockImplementation(akis.uret);
    await ciz("/hukukbot?s=o-yeni");
    await yaz("ikinci");
    await tikla(dugme("Gönder"));
    expect(apiMock.oturumOlustur).not.toHaveBeenCalled();
    const [soru, secenek] = apiMock.ask.mock.calls[0];
    expect(soru).toEqual({
      question: "ikinci",
      history: [
        { role: "user", content: "ilk" },
        { role: "model", content: "cevap" },
      ],
    });
    expect(secenek.sessionId).toBe("o-yeni");
    await akis.bitir();
  });

  it("Shift+Enter göndermez; boş/boşluk soru gönderilmez", async () => {
    await ciz();
    await yaz("satır 1");
    await enter(true);
    await yaz("   ");
    await enter();
    expect(dugme("Gönder").disabled).toBe(true);
    await tikla(dugme("Gönder"));
    expect(apiMock.oturumOlustur).not.toHaveBeenCalled();
    expect(apiMock.ask).not.toHaveBeenCalled();
  });

  it("Durdur akışı keser: yanıt yarım kalır, kutu açılır", async () => {
    const akis = kontrolluAkis();
    apiMock.ask.mockImplementation(akis.uret);
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni", title: "Kira tespit", created_at: "2026-09-20T10:00:00Z", is_pinned: false, messages: [],
    } satisfies HukukbotOturum);
    await ciz("/hukukbot?s=o-yeni");
    await yaz("uzun soru");
    await enter();
    await akis.ver({ type: "content", data: "Yarım" });
    const signal = apiMock.ask.mock.calls[0][1].signal as AbortSignal;
    await tikla(dugme("Durdur"));
    expect(signal.aborted).toBe(true);
    expect(kap.textContent).toContain("Yanıt durduruldu");
    expect(kap.querySelector("[data-testid='hukukbot-yanit']")?.textContent).toContain("Yarım");
    expect(soruKutusu().disabled).toBe(false);
  });

  it("429 → Türkçe hız sınırı mesajı (sunucu metni İngilizce olsa bile)", async () => {
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni", title: "Kira tespit", created_at: "2026-09-20T10:00:00Z", is_pinned: false, messages: [],
    } satisfies HukukbotOturum);
    // `ask` gerçekte HTTP 429'u akış başlamadan ilk `next()`te fırlatır.
    apiMock.ask.mockImplementation(() => ({
      [Symbol.asyncIterator]() {
        return { next: () => Promise.reject(new HukukbotHizSiniriError("Rate limit exceeded")) };
      },
    }));
    await ciz("/hukukbot?s=o-yeni");
    await yaz("soru");
    await enter();
    const hata = kap.querySelector("[data-testid='hukukbot-hata']");
    expect(hata?.textContent).toBe(HUKUKBOT_HIZ_MESAJI);
    expect(hata?.textContent).not.toContain("Rate limit");
    expect(soruKutusu().disabled).toBe(false);
  });

  it("akış `error` olayıyla biterse Türkçe hata gösterilir, ham sunucu metni gösterilmez", async () => {
    const uyari = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni", title: "Kira tespit", created_at: "2026-09-20T10:00:00Z", is_pinned: false, messages: [],
    } satisfies HukukbotOturum);
    const akis = kontrolluAkis();
    apiMock.ask.mockImplementation(akis.uret);
    await ciz("/hukukbot?s=o-yeni");
    await yaz("soru");
    await enter();
    await akis.ver({ type: "error", data: "Traceback: KeyError 'x'" });
    await akis.bitir();
    const hata = kap.querySelector("[data-testid='hukukbot-hata']");
    expect(hata?.textContent).toMatch(/hata oluştu/);
    expect(hata?.textContent).not.toContain("Traceback");
    uyari.mockRestore();
  });

  it("kaynak indirme hatası toast ile bildirilir", async () => {
    apiMock.indir.mockRejectedValueOnce(new HukukbotHizSiniriError());
    apiMock.oturumGetir.mockResolvedValue({
      id: "o-yeni",
      title: "Kira tespit",
      created_at: "2026-09-20T10:00:00Z",
      is_pinned: false,
      messages: [
        { role: "user", content: "s" },
        { role: "model", content: "c", sources: [{ file_display_name: "Karar", filename: "karar.pdf", text_preview: "" }] },
      ],
    } satisfies HukukbotOturum);
    await ciz("/hukukbot?s=o-yeni");
    await tikla(dugme("PDF'i aç: Karar"));
    expect(apiMock.indir).toHaveBeenCalledWith("karar.pdf");
    expect(toastMocks.error).toHaveBeenCalledWith(expect.stringContaining(HUKUKBOT_HIZ_MESAJI));
  });

  const hukudokKaynakliOturum = (kaynak: Record<string, unknown>) =>
    ({
      id: "o-hd",
      title: "Tebligat",
      created_at: "2026-09-26T10:00:00Z",
      is_pinned: false,
      messages: [
        { role: "user", content: "s" },
        { role: "model", content: "c", sources: [{ file_display_name: "Tebligat", filename: "t.pdf", text_preview: "", ...kaynak }] },
      ],
    }) as HukukbotOturum;

  it("HUKDOK'tan aktarılmış kaynak HUKDOK arşivinden açılır: sekme tıklamada açılır, Hukukbot /download'a gidilmez", async () => {
    const sekme = { close: vi.fn(), location: { href: "" } } as unknown as Window;
    const ac = vi.spyOn(window, "open").mockReturnValue(sekme);
    apiMock.hukudokBelgesiniAc.mockResolvedValueOnce(undefined);
    apiMock.oturumGetir.mockResolvedValue(hukudokKaynakliOturum({ hukdok_id: 14743 }));
    await ciz("/hukukbot?s=o-hd");
    await tikla(dugme("PDF'i aç: Tebligat"));
    expect(ac).toHaveBeenCalledWith("", "_blank");
    expect(apiMock.hukudokBelgesiniAc).toHaveBeenCalledWith(14743, sekme);
    expect(apiMock.indir).not.toHaveBeenCalled();
    ac.mockRestore();
  });

  it("alan eklenmeden önceki mesaj: metadata.hukdok_id'den açılır", async () => {
    const ac = vi.spyOn(window, "open").mockReturnValue(null);
    apiMock.hukudokBelgesiniAc.mockResolvedValueOnce(undefined);
    apiMock.oturumGetir.mockResolvedValue(hukudokKaynakliOturum({ metadata: { hukdok_id: "501" } }));
    await ciz("/hukukbot?s=o-hd");
    await tikla(dugme("PDF'i aç: Tebligat"));
    expect(apiMock.hukudokBelgesiniAc).toHaveBeenCalledWith(501, null);
    ac.mockRestore();
  });

  it("HUKDOK açma hatasında boş sekme kapanır, Türkçe toast", async () => {
    const sekme = { close: vi.fn(), location: { href: "" } } as unknown as Window;
    const ac = vi.spyOn(window, "open").mockReturnValue(sekme);
    apiMock.hukudokBelgesiniAc.mockRejectedValueOnce(new HukukbotApiError(404, "Belge bulunamadı"));
    apiMock.oturumGetir.mockResolvedValue(hukudokKaynakliOturum({ hukdok_id: 9 }));
    await ciz("/hukukbot?s=o-hd");
    await tikla(dugme("PDF'i aç: Tebligat"));
    expect(sekme.close).toHaveBeenCalled();
    expect(toastMocks.error).toHaveBeenCalledWith(expect.stringContaining("HUKDOK arşivinden açılamadı"));
    ac.mockRestore();
  });
});
