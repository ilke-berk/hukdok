// @vitest-environment jsdom
// Belgeden künye önerileri (lexis-rapor Aşama 13): NDJSON olay çözücüsü, künye kartında alan başına öneri çipi
// (değer + belge adı, alıntı title'da, kabul / ret, kart değeri farklıysa yan yana — K34), kabul edilen değerin satıra
// "belgeden" diye girmesi, reddedilenin gizlenmesi; "Belgelerden doldur" gerçek kipte onay kutusu olmadan pasif (K4).
// Veriler UYDURMADIR.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { kunyeOlayCoz } from "@/lib/lexisAkis";
import { ORNEK_DOSYALAR } from "@/lib/lexisOrnekVeri";
import type { KunyeHatDurumu, KunyeOnerisi } from "@/types/lexis";
import { KunyeKarti } from "./KunyeKarti";
import { KunyeDoldur } from "./KunyeOneriCipi";

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

const oneri = (ek: Partial<KunyeOnerisi>): KunyeOnerisi => ({
  id: 1, case_id: 101, belge_id: 7, belge_sha256: "a".repeat(64), alan: "sigortali", deger: "Dr. Deneme Hekim", deger_sayi: null,
  alinti: "Acil Tıp Uzmanı Dr. Deneme Hekim'e tebliğ edilmiştir", kart_durumu: "kartta_bos", kart_degeri: null, model: "sahte",
  istem_surumu: "2026-10-08a", durum: "oneri", olusturma: null, karar_veren: null, karar_zamani: null, ...ek,
});

describe("kunyeOlayCoz", () => {
  it("dört olay türü ve bozuk satır", () => {
    expect(kunyeOlayCoz('{"status":"info","asama":"okuma","belge_id":7,"sira":1,"toplam":2}')).toEqual({ status: "info", asama: "okuma", belge_id: 7, sira: 1, toplam: 2 });
    expect(kunyeOlayCoz('{"status":"warning","asama":"metin","belge_id":9,"message":"Belge okunamadı"}')).toEqual({ status: "warning", asama: "metin", belge_id: 9, message: "Belge okunamadı" });
    const tamam = kunyeOlayCoz(JSON.stringify({ status: "complete", case_id: 101, model: "sahte", oneriler: [oneri({}), { bozuk: true }], okunamayanlar: [{ belge_id: 9, neden: "x" }], sayilar: { belge: 2, yazi: "x" } }));
    expect(tamam?.status === "complete" && [tamam.oneriler.length, tamam.okunamayanlar, tamam.sayilar]).toEqual([1, [{ belge_id: 9, neden: "x" }], { belge: 2 }]);
    expect(kunyeOlayCoz('{"status":"failed","error_kod":"metin_yok"}')).toMatchObject({ status: "failed", error_kod: "metin_yok", error_ozet: "Künye çıkarımı başlatılamadı." });
    expect(kunyeOlayCoz("{bozuk")).toBeNull();
    expect(kunyeOlayCoz('{"status":"baska"}')).toBeNull();
  });
});

describe("KunyeKarti — öneri çipleri", () => {
  const dosya = { ...ORNEK_DOSYALAR[Number(Object.keys(ORNEK_DOSYALAR)[0])], sigortali: "Dr. Kartta Kayıtlı", magdur: null };

  it("çip değer + belge adı taşır, alıntı title'da; kabul / ret çağrılır; kart değeri farklıysa yan yana", () => {
    const karar = vi.fn();
    const oneriler = [
      oneri({ id: 1, kart_durumu: "farkli", kart_degeri: "Dr. Kartta Kayıtlı" }),
      oneri({ id: 2, alan: "hasta", deger: "Deneme Kişi", alinti: "müteveffa Deneme Kişi'nin" }),
      oneri({ id: 3, alan: "hasta", deger: "Davacı Örnek", durum: "ret" }),
      oneri({ id: 4, alan: "olay_tarihi", deger: "03.02.2025", alinti: "03.02.2025 tarihinde" }),
    ];
    act(() => kok.render(<KunyeKarti dosya={dosya} onDegistir={() => undefined} oneriler={oneriler} onOneriKarar={karar} belgeAdi={(id) => `ust_yazi_${id}.pdf`} />));
    const cipler = [...kap.querySelectorAll("[data-testid=kunye-oneri]")];
    expect(cipler).toHaveLength(3); // reddedilen gizli
    expect(cipler[0].textContent).toContain("Dr. Deneme Hekim");
    expect(cipler[0].textContent).toContain("ust_yazi_7.pdf");
    expect(cipler[0].textContent).toContain("kartta: Dr. Kartta Kayıtlı");
    expect(cipler[0].getAttribute("title")).toContain("Alıntı: “Acil Tıp Uzmanı Dr. Deneme Hekim'e tebliğ edilmiştir”");
    expect(kap.textContent).not.toContain("Davacı Örnek");
    expect(kap.textContent).toContain("Olay tarihi"); // kartta olmayan alan önerisi varsa satır olur
    expect(kap.textContent).not.toContain("Davalı");
    act(() => (kap.querySelector("[aria-label='Deneme Kişi önerisini kabul et']") as HTMLButtonElement).click());
    expect(karar).toHaveBeenCalledWith(oneriler[1], "kabul");
    act(() => (kap.querySelector("[aria-label='Dr. Deneme Hekim önerisini reddet']") as HTMLButtonElement).click());
    expect(karar).toHaveBeenCalledWith(oneriler[0], "ret");
  });

  it("kabul edilen değer satıra 'belgeden' diye girer, kart değeri çipte kalır; geri alınabilir", () => {
    const karar = vi.fn();
    const kabul = oneri({ id: 1, durum: "kabul", kart_durumu: "farkli", kart_degeri: "Dr. Kartta Kayıtlı" });
    act(() => kok.render(<KunyeKarti dosya={dosya} onDegistir={() => undefined} oneriler={[kabul]} onOneriKarar={karar} />));
    const satir = [...kap.querySelectorAll("dd")].find((dd) => dd.textContent?.includes("belgeden"));
    expect(satir?.textContent).toContain("Dr. Deneme Hekim");
    act(() => (kap.querySelector("[aria-label='Dr. Deneme Hekim kabulünü geri al']") as HTMLButtonElement).click());
    expect(karar).toHaveBeenCalledWith(kabul, "oneri");
  });

  it("öneri yoksa kart eskisi gibi", () => {
    act(() => kok.render(<KunyeKarti dosya={dosya} onDegistir={() => undefined} />));
    expect(kap.querySelectorAll("[data-testid=kunye-oneri]")).toHaveLength(0);
    expect(kap.textContent).toContain("Dr. Kartta Kayıtlı");
  });
});

describe("KunyeDoldur", () => {
  const hat = (ek: Partial<KunyeHatDurumu>): KunyeHatDurumu => ({ acik: true, kip: "sahte", model: "sahte", neden: null, onay_gerekir: false, istem_surumu: "x", belge_tavani: 30, ...ek });
  const ortak = { calisiyor: false, ilerleme: null, uyarilar: [], hata: null, siniflar: [], belgeAdi: (id: number) => `b${id}`, onKarar: () => undefined };

  it("gerçek kipte onay kutusu işaretlenmeden düğme pasif; onay koşudan sonra sıfırlanır", () => {
    const doldur = vi.fn();
    act(() => kok.render(<KunyeDoldur {...ortak} hat={hat({ kip: "gemini", model: "gemini-3.8-flash", onay_gerekir: true })} onDoldur={doldur} />));
    const dugme = [...kap.querySelectorAll("button")].find((b) => b.textContent === "Belgelerden doldur") as HTMLButtonElement;
    expect(dugme.disabled).toBe(true);
    expect(kap.textContent).toContain("maskesiz gönderilecek");
    const kutu = kap.querySelector("input[type=checkbox]") as HTMLInputElement;
    act(() => kutu.click());
    expect(dugme.disabled).toBe(false);
    act(() => dugme.click());
    expect(doldur).toHaveBeenCalledWith(true);
    expect((kap.querySelector("input[type=checkbox]") as HTMLInputElement).checked).toBe(false);
    expect(dugme.disabled).toBe(true);
  });

  it("sahte kipte onay istemez; örnek kipte ve hat yokken çizilmez; belge türü önerisi gösterilir", () => {
    const doldur = vi.fn();
    const sinif = oneri({ id: 9, alan: "belge_sinifi", deger: "UST_YAZI", alinti: "Konu: Bilgi ve belge istemi" });
    act(() => kok.render(<KunyeDoldur {...ortak} siniflar={[sinif]} hat={hat({})} onDoldur={doldur} />));
    expect(kap.textContent).toContain("sahte üretici");
    expect(kap.textContent).toContain("İdare üst yazısı");
    act(() => ([...kap.querySelectorAll("button")].find((b) => b.textContent === "Belgelerden doldur") as HTMLButtonElement).click());
    expect(doldur).toHaveBeenCalledWith(false);
    act(() => kok.render(<KunyeDoldur {...ortak} hat={hat({ acik: false, neden: "ornek" })} onDoldur={doldur} />));
    expect(kap.textContent).toBe("");
    act(() => kok.render(<KunyeDoldur {...ortak} hat={null} onDoldur={doldur} />));
    expect(kap.textContent).toBe("");
  });
});
