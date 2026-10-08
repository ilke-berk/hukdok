// @vitest-environment jsdom
// Tezgah — "Rapor yaz" akışı örnek adaptörle uçtan uca: dava seç → künye/belge/emsal gelir → onaylı yazım →
// bölümler ve madde rozetleri (dayanak kuralı) → düzenle → alandan çıkınca yeniden denetim → dayanak vurgusu →
// muallak sınırı → Word (gerçek servise devir). Taslağı silen eylemler onay ister.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const confirmMock = vi.hoisted(() => ({ fn: vi.fn(async (_opts: unknown) => true) }));
vi.mock("@/hooks/useConfirm", () => ({ useConfirm: () => confirmMock.fn }));

// Word çağrısı gerçek servise gider (`lexisWord.ts` → `apiClient`); tezgâh testinde sahtedir.
const wordMock = vi.hoisted(() => ({ wordIndir: vi.fn() }));
vi.mock("@/lib/lexisWord", () => wordMock);

// Gerçek dava kipinde dosya bölgesi servise gider (`lexisServis.ts` → `apiClient`); burada sahtedir.
const servisMock = vi.hoisted(() => ({
  davaAra: vi.fn(),
  dosyaGetir: vi.fn(),
  emsalOner: vi.fn(),
  iskelet: vi.fn(),
  muallakOner: vi.fn(),
  kararBankasi: vi.fn(),
  kutuphaneAra: vi.fn(),
  raporGetir: vi.fn(),
  emsalPuanla: vi.fn(),
  taslakGetir: vi.fn(),
  taslakKaydet: vi.fn(),
  taslakSil: vi.fn(),
  kartKararlari: vi.fn(),
  kararGetir: vi.fn(),
  yaz: vi.fn(),
  // Emsal ajan hattı (G264)
  emsalBelgeKarttan: vi.fn(),
  emsalBelgeYukle: vi.fn(),
  emsalDurum: vi.fn(),
  emsalAra: vi.fn(),
  emsalSonuc: vi.fn(),
  emsalIndir: vi.fn(),
}));
vi.mock("@/lib/lexisServis", () => servisMock);

/** Kararsız dava, yazım kapalı — servisin varsayılan yanıtı. */
const KARARSIZ = { kararlar: [], yazim: { acik: false, neden: "kapali", model: null } };

import { Tezgah } from "./Tezgah";
import { KAYIT_GECIKMESI, kayitGecikmesiAyarla } from "./useTezgah";
import { GERCEK_ISKELET_NOTU, GERCEK_YAZIM_NOTU, LexisApiError, ORNEK_EMSAL_DURUMU, lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, veriKipiAyarla } from "@/lib/lexisApi";
import type { DosyaGirdisi, Emsal, EmsalAkisOlayi, EmsalOnerisi, KayitliTaslak, LexisTaslak, RafKarari } from "@/types/lexis";

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
  Object.values(servisMock).forEach((m) => m.mockReset());
  servisMock.kartKararlari.mockResolvedValue(KARARSIZ);
  wordMock.wordIndir.mockReset();
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
  veriKipiAyarla("ornek");
});

describe("Tezgah — gerçek dava kipi", () => {
  it("dava, künye ve emsaller servisten gelir; taslak iskelettir, sınıf seçilir, Word iner", async () => {
    // Servis yanıtları örnek adaptörün ürettiği biçimdedir (sözleşme aynı); kimlikler gerçek karta aittir.
    const dosya = { ...(await lexisApi.dosyaGetir(9003)), onceki_rapor: null };
    const emsaller = await lexisApi.emsalOner({ case_id: 9003, sirket: dosya.sirket, rapor_turu: dosya.rapor_turu });
    const dava = { ...dosya.dava, case_id: 501, ofis_no: "QUICK-0501-DR.GERCEK-HUK" };
    servisMock.davaAra.mockResolvedValue([dava]);
    servisMock.dosyaGetir.mockResolvedValue({ ...dosya, dava });
    servisMock.emsalOner.mockResolvedValue(emsaller);
    const yeni = (await lexisApi.kutuphaneAra({})).find((k) => !emsaller.some((e) => e.kayit.okuma.sha256 === k.okuma.sha256))!;
    servisMock.kutuphaneAra.mockResolvedValue([yeni]);
    servisMock.emsalPuanla.mockResolvedValue({ kayit: yeni, puan: 1, bilesenler: [], gerekce: "elle eklendi" });
    servisMock.taslakGetir.mockResolvedValue(null);

    veriKipiAyarla("gercek");
    await ciz();
    await davaSec("QUICK-0501");

    expect(servisMock.dosyaGetir.mock.calls[0][0]).toBe(501);
    expect(servisMock.emsalOner.mock.calls[0][0]).toMatchObject({ case_id: 501, sirket: "QUICK" });
    expect(test("lexis-kunye")!.textContent).toContain("Bursa 1. Tüketici Mahkemesi");
    expect(test("lexis-emsaller")!.querySelectorAll("li").length).toBe(emsaller.length);
    expect(test("lexis-iskelet-notu")!.textContent).toBe(GERCEK_ISKELET_NOTU);

    // Kütüphaneden elle emsal: liste ve puan servisten gelir, puanlama dosyanın şirketi ve rapor türüyle istenir.
    await tikla(dugme("Kütüphaneden emsal ekle"));
    const diyalog = document.querySelector<HTMLElement>('[data-testid="lexis-emsal-ekle"]')!;
    await tikla(diyalog.querySelector<HTMLButtonElement>("li button")!);
    expect(servisMock.emsalPuanla.mock.calls[0][0]).toEqual({ case_id: 501, sha256: yeni.okuma.sha256, sirket: "QUICK", rapor_turu: "ANA" });
    expect(test("lexis-emsaller")!.querySelectorAll("li").length).toBe(emsaller.length + 1);

    // "Taslağı yaz" iskelet üretir: künye karttan dolu, özet boş; onay kutusu modele gönderim listesi taşımaz.
    const ornek = { ...dosya, dava };
    const hasar = [{ alan: "sigortali", etiket: "Sigortalı", deger: ornek.sigortali, zorunlu: true, kaynak: "KART" as const }];
    const muallak = { maddi: null, manevi: null, dayanak: "YOK" as const, dayanak_satirlari: [], kusur_tespiti: "BELIRSIZ" as const, risk_duzeyi: "BELIRSIZ" as const, teminat: "BELIRSIZ" as const, uyarilar: [] };
    servisMock.iskelet.mockResolvedValue({
      etiketli: { hasar },
      ozet: {},
      degerlendirme: { giris: "Tarafımıza iletilen belge ve bilgiler ile yapılan inceleme neticesinde;", maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
      muallak,
    });
    servisMock.kararBankasi.mockResolvedValue([]);
    await tikla(dugme("Taslağı yaz"));
    const onay = confirmMock.fn.mock.calls[0][0] as { body: string; details: { label: string }[] };
    expect(onay.body).toContain(GERCEK_ISKELET_NOTU);
    expect(onay.details.map((d) => d.label)).toEqual(["Rapor"]);
    expect(servisMock.iskelet.mock.calls[0][0]).toMatchObject({ case_id: 501, iskelet: "KISA" });
    expect(test("lexis-bolum-hasar")!.querySelectorAll("input")).toHaveLength(1);
    expect(test("lexis-uyarilar")!.textContent).toContain("Bölüm boş");

    // Sınıf seçilince öneri yeniden hesaplatılır; Word gerçek dosyanın künyesiyle iner.
    servisMock.muallakOner.mockResolvedValue({ ...muallak, manevi: 40000, dayanak: "EMSAL", kusur_tespiti: "KOMPLIKASYON", risk_duzeyi: "RISKLI", teminat: "ICINDE" });
    await yaz(alan<HTMLSelectElement>("Risk düzeyi"), "RISKLI");
    await bekle();
    expect(servisMock.muallakOner.mock.calls[0][0]).toMatchObject({ case_id: 501, risk_duzeyi: "RISKLI", kusur_tespiti: "BELIRSIZ" });
    expect(test("lexis-muallak")!.textContent).toContain("40.000,00");

    wordMock.wordIndir.mockResolvedValueOnce({ dosya_adi: "Lexis_x.docx", uyari_sayisi: 0, uyarilar: [] });
    await tikla(dugme("Word indir"));
    expect(wordMock.wordIndir.mock.calls[0][1]).toEqual({ hasar_no: ornek.hasar_no, hukuk_no: ornek.hukuk_no, rapor_no: dava.dosya_no });
  });
});

describe("Tezgah — kalıcılık (gerçek dava kipi)", () => {
  const MUALLAK = { maddi: null, manevi: null, dayanak: "YOK" as const, dayanak_satirlari: [], kusur_tespiti: "BELIRSIZ" as const, risk_duzeyi: "BELIRSIZ" as const, teminat: "BELIRSIZ" as const, uyarilar: [] };
  const GIRIS = "Tarafımıza iletilen belge ve bilgiler ile yapılan inceleme neticesinde;";
  let dosya: DosyaGirdisi;
  let emsaller: Emsal[];

  const GECIKME = 40;

  /** Otomatik kaydın gecikmesi kadar bekler. */
  async function kaydiBekle() {
    await act(async () => {
      await new Promise((r) => setTimeout(r, GECIKME + 60));
    });
    await bekle();
  }

  afterEach(() => kayitGecikmesiAyarla(KAYIT_GECIKMESI));

  beforeEach(async () => {
    kayitGecikmesiAyarla(GECIKME);
    const ornek = await lexisApi.dosyaGetir(9003);
    emsaller = await lexisApi.emsalOner({ case_id: 9003, sirket: ornek.sirket, rapor_turu: ornek.rapor_turu });
    const dava = { ...ornek.dava, case_id: 501, ofis_no: "QUICK-0501-DR.GERCEK-HUK" };
    dosya = { ...ornek, dava, onceki_rapor: null };
    servisMock.davaAra.mockResolvedValue([dava, { ...dava, case_id: 502, ofis_no: "QUICK-0502-DR.IKINCI-HUK" }]);
    servisMock.dosyaGetir.mockImplementation(async (caseId: number) => ({ ...dosya, dava: { ...dava, case_id: caseId } }));
    servisMock.emsalOner.mockResolvedValue(emsaller);
    servisMock.kararBankasi.mockResolvedValue([]);
    servisMock.taslakGetir.mockResolvedValue(null);
    servisMock.iskelet.mockResolvedValue({
      etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: dosya.sigortali, zorunlu: true, kaynak: "KART" }] },
      ozet: {},
      degerlendirme: { giris: GIRIS, maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
      muallak: MUALLAK,
      kosu_id: 77,
    });
    veriKipiAyarla("gercek");
  });

  it("taslak yazıldıktan sonra kendiliğinden kaydedilir; sonraki kayıt okunan sürümle gider", async () => {
    servisMock.taslakKaydet.mockResolvedValueOnce({ surum: 1, guncelleme: "2026-10-04T20:00:00+00:00", guncelleyen: "siz" });
    await ciz();
    await taslakYaz("QUICK-0501");
    await kaydiBekle();

    // Akış boyunca (bölümler tek tek gelirken) yazılmaz: bittikten sonra TEK kayıt.
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(1);
    const [caseId, ilk] = servisMock.taslakKaydet.mock.calls[0] as [number, { taslak: LexisTaslak; surum: number | null; kosu_id: number | null; uyari_sayisi: number; ekran: { secili_belgeler: number[] } }];
    expect(caseId).toBe(501);
    expect(ilk).toMatchObject({ surum: null, kosu_id: 77, taslak: { case_id: 501, iskelet: "KISA" } });
    expect(ilk.uyari_sayisi).toBeGreaterThan(0);
    expect(ilk.ekran.secili_belgeler).toEqual(dosya.belgeler.map((b) => b.id));
    expect(test("lexis-kayit-durumu")!.textContent).toContain("Kaydedildi");

    // Değişiklik yokken yeniden yazılmaz; düzenleme okunan sürümle (1) kaydedilir.
    await kaydiBekle();
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(1);
    servisMock.taslakKaydet.mockResolvedValueOnce({ surum: 2, guncelleme: "2026-10-04T20:01:00+00:00", guncelleyen: "siz" });
    await yaz(alan<HTMLTextAreaElement>("Giriş cümlesi"), "Tarafımıza iletilen belgeler incelendi;");
    await kaydiBekle();
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(2);
    expect(servisMock.taslakKaydet.mock.calls[1][1]).toMatchObject({ surum: 1, taslak: { degerlendirme: { giris: "Tarafımıza iletilen belgeler incelendi;" } } });
  });

  it("dava değişimi taslağı silmez: bekleyen kayıt hemen gider, onay istenmez; künye değişimi kayıtlı taslağı siler", async () => {
    servisMock.taslakKaydet.mockResolvedValue({ surum: 1, guncelleme: "2026-10-04T20:00:00+00:00", guncelleyen: "siz" });
    servisMock.taslakSil.mockResolvedValue(undefined);
    await ciz();
    await taslakYaz("QUICK-0501");
    confirmMock.fn.mockClear();

    await tikla(dugme("Davayı değiştir"));
    expect(confirmMock.fn).not.toHaveBeenCalled();
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(1); // gecikme beklenmedi
    expect(servisMock.taslakKaydet.mock.calls[0][0]).toBe(501);

    await davaSec("QUICK-0502");
    await tikla(dugme("Taslağı yaz"));
    await kaydiBekle();
    expect(servisMock.taslakKaydet.mock.calls.at(-1)![0]).toBe(502);
    confirmMock.fn.mockClear();
    const iskelet = Array.from(test("lexis-kunye")!.querySelectorAll("select"))[2];
    await yaz(iskelet, "ALTILI");
    await bekle();
    expect((confirmMock.fn.mock.calls.at(-1)![0] as { title: string }).title).toBe("Taslak silinecek");
    expect(servisMock.taslakSil).toHaveBeenCalledTimes(1);
    expect(servisMock.taslakSil.mock.calls[0][0]).toBe(502);
    expect(maddeler()).toHaveLength(0);
  });

  it("kayıtlı taslak dava seçilince künyesi, emsalleri ve bölüm durumlarıyla geri açılır; açmak yeni sürüm yazmaz", async () => {
    const taslak: LexisTaslak = {
      case_id: 501,
      sirket: "QUICK",
      rapor_turu: "ANA",
      iskelet: "ALTILI", // kart QUICK → KISA önerir; kayıtlı taslağın seçimi geçerlidir
      etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: "Dr. Kayıtlı Hekim", zorunlu: true, kaynak: "ELLE" }] },
      ozet: { iddia: [{ metin: "Kaydedilmiş iddia özeti.", kaynak_belge_id: null }] },
      degerlendirme: { giris: GIRIS, maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
      muallak: MUALLAK,
      muallak_maddi: null,
      muallak_manevi: 55000,
      emsaller: [emsaller[0].kayit.okuma.sha256],
    };
    const kayitli: KayitliTaslak = {
      taslak,
      ekran: { bolum_durumlari: { iddia: "duzenlendi" }, secili_belgeler: [dosya.belgeler[0].id] },
      surum: 4,
      kosu_id: 41,
      guncelleyen: "ikinci@ornek.test",
      guncelleme: "2026-10-04T17:30:00+00:00",
    };
    servisMock.taslakGetir.mockResolvedValue(kayitli);
    servisMock.emsalPuanla.mockResolvedValue(emsaller[0]);
    servisMock.taslakKaydet.mockResolvedValue({ surum: 5, guncelleme: "2026-10-04T20:00:00+00:00", guncelleyen: "siz" });
    await ciz();
    await davaSec("QUICK-0501");

    expect(servisMock.taslakGetir.mock.calls[0][0]).toBe(501);
    expect(toastMocks.info).toHaveBeenCalledWith("Kayıtlı taslak açıldı", { description: "Son kayıt: ikinci@ornek.test · 04.10.2026 20:30" });
    expect(test("lexis-bolum-gezgini")!.querySelectorAll("button")).toHaveLength(6); // ALTILI
    expect(test("lexis-bolum-hasar")!.querySelector("input")!.value).toBe("Dr. Kayıtlı Hekim");
    expect(test("lexis-bolum-iddia")!.querySelector("textarea")!.value).toBe("Kaydedilmiş iddia özeti.");
    expect(test("lexis-emsaller")!.querySelectorAll("li")).toHaveLength(1); // öneri değil, taslağın baktığı rapor
    expect(servisMock.emsalOner).not.toHaveBeenCalled();
    expect(test("lexis-belgeler")!.textContent).toContain(`1/${dosya.belgeler.length} seçili`);
    expect(test("lexis-kayit-durumu")!.textContent).toBe("Kaydedildi · 04.10.2026 20:30");
    expect(dugme("Yeniden yaz")).toBeDefined();

    await kaydiBekle();
    expect(servisMock.taslakKaydet).not.toHaveBeenCalled(); // yalnız açmak "son güncelleyen"i değiştirmez

    // Düzenleme kayıtlı sürümle (4) ve kayıtlı taslağın koşusuyla (41) yazılır; Word aynı koşuyu işaretler.
    await yaz(test("lexis-bolum-iddia")!.querySelector("textarea")!, "Düzeltilmiş iddia özeti.");
    await kaydiBekle();
    expect(servisMock.taslakKaydet.mock.calls[0][1]).toMatchObject({ surum: 4, kosu_id: 41 });
    wordMock.wordIndir.mockResolvedValueOnce({ dosya_adi: "Lexis_x.docx", uyari_sayisi: 0, uyarilar: [] });
    await tikla(dugme("Word indir"));
    expect(wordMock.wordIndir.mock.calls[0][1]).toMatchObject({ kosu_id: 41 });
  });

  it("başka oturum yazmışsa (409) uyarı görünür ve bu oturum o taslağa artık yazmaz; ağ hatasında yeniden denenir", async () => {
    const cakisma = "Bu davanın taslağı başka bir oturumda değişmiş. Davayı yeniden seçip kayıtlı taslağı açın; buradaki değişiklikler kaydedilmedi.";
    servisMock.taslakKaydet.mockRejectedValueOnce(new LexisApiError(503, "Lexis veritabanına ulaşılamadı; biraz sonra tekrar deneyin."));
    await ciz();
    await taslakYaz("QUICK-0501");
    await kaydiBekle();
    expect(test("lexis-kayit-hatasi")!.textContent).toContain("Taslak kaydedilemedi: Lexis veritabanına ulaşılamadı");

    servisMock.taslakKaydet.mockRejectedValueOnce(new LexisApiError(409, cakisma));
    await tikla(dugme("Yeniden dene"));
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(2);
    expect(test("lexis-kayit-hatasi")!.textContent).toBe(cakisma);

    await yaz(alan<HTMLTextAreaElement>("Giriş cümlesi"), "Tarafımıza iletilen belgeler incelendi;");
    await kaydiBekle();
    expect(servisMock.taslakKaydet).toHaveBeenCalledTimes(2); // kilitli: üzerine yazma denenmez

    // Kaydedilemeyen taslakla başka davaya geçiş onay ister.
    confirmMock.fn.mockClear();
    confirmMock.fn.mockResolvedValueOnce(false);
    await tikla(dugme("Davayı değiştir"));
    expect((confirmMock.fn.mock.calls[0][0] as { title: string }).title).toBe("Kaydedilmemiş değişiklik var");
    expect(test("lexis-kayit-hatasi")).not.toBeNull();
  });

  it("kayıtlı taslak okunamazsa dosya yine açılır, hata görünür", async () => {
    servisMock.taslakGetir.mockRejectedValue(new LexisApiError(503, "Lexis veritabanına ulaşılamadı; biraz sonra tekrar deneyin."));
    await ciz();
    await davaSec("QUICK-0501");
    expect(test("lexis-kunye")).not.toBeNull();
    expect(test("lexis-emsaller")!.querySelectorAll("li")).toHaveLength(emsaller.length);
    expect(test("lexis-kayit-hatasi")!.textContent).toContain("Kayıtlı taslak okunamadı: Lexis veritabanına ulaşılamadı");
  });

  // --- kararlardan yazım ---
  const KARAR_METNI = "Bilirkişi raporunda hekime atfı kabil kusur bulunmadığı bildirilmiştir. HÜKÜM: Davanın REDDİNE 05.05.2021 tarihinde karar verildi.";
  const karar = (id: number, p: Partial<RafKarari> = {}): RafKarari => ({
    id, belge_turu: "karar", mahkeme: "Örnekköy 2. İdare Mahkemesi", derece: "YEREL", esas_no: "2019/123", karar_no: "2021/456", karar_tarihi: "2021-05-05",
    uzmanlik: null, kart_id: 501, kart_bagi: "TEK_KART", asamaya_bagli: true, metin_uzunluk: KARAR_METNI.length, hukum_sinifi: "RED_ESASTAN", hukum_yonleri: ["RED"],
    sonuc_muvekkil: "RED_ESASTAN", sonuc_iliskisi: "AYNI", hukmedilen_maddi: [], hukmedilen_manevi: [], hukmedilen_birlesik: [], talep_maddi: [], talep_manevi: [],
    olay: null, maluliyet_orani: [], kusur_orani: [], dayanak_kurul: [], faiz: [], konular: {}, ...p,
  });
  const KARARLAR = [karar(72, { mahkeme: "Örnek BAM 3. İdari Dava Dairesi", derece: "ISTINAF", esas_no: "2021/900", karar_no: "2022/15", karar_tarihi: "2022-02-01", hukum_sinifi: "BASVURU_RET", sonuc_muvekkil: "BASVURU_RET" }), karar(71)];
  const ayrinti = (k: RafKarari) => ({ ...k, kunye_kaynak: {}, vekalet_ucreti: [], yargilama_gideri: [], hukum_kaynagi: null, yas: [], davaci_sayisi: null, parcalar: { hukum: null, iddia: [], savunma: [], gerekce: [] }, metin: KARAR_METNI });
  const YAZIM = {
    ozet: { iddia: [{ metin: "Davacı, ameliyat sonrası zarar gördüğünü ileri sürmüştür.", kaynak_belge_id: null, kaynak_karar_id: 71, dayanak_alinti: "hekime atfı kabil kusur bulunmadığı bildirilmiştir" }] },
    degerlendirme: {
      giris: GIRIS,
      maddeler: [
        { metin: "Bilirkişi raporunda sigortalı hekime atfı kabil kusur bulunmadığının bildirildiği,", tur: "TESPIT" as const, dayanak_bolum: "yargi_sureci" as const, dayanak_alinti: "hekime atfı kabil kusur bulunmadığı bildirilmiştir" },
        { metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP" as const, dayanak_bolum: null, dayanak_alinti: null },
      ],
      sulh_uygunluk: "",
      muallak_gerekcesi: "",
    },
    muallak: { ...MUALLAK, kusur_tespiti: "HATA_YOK" as const, risk_duzeyi: "DUSUK" as const },
    kararlar: [71],
    uyarilar: [],
    model: "gemini-test",
    maske: { bilinen: 2, kalip: 1, ogrenilen: 0 },
    gonderilen_karakter: 140,
  };

  it("yazım açıkken seçili kararlar onayda gösterilir ve taslak kararlardan yazılır; paragraf ve madde kaynak kararını taşır", async () => {
    servisMock.kartKararlari.mockResolvedValue({ kararlar: KARARLAR, yazim: { acik: true, neden: null, model: "gemini-test" } });
    servisMock.kararGetir.mockImplementation(async (id: number) => ayrinti(KARARLAR.find((k) => k.id === id)!));
    servisMock.yaz.mockResolvedValue(YAZIM);
    servisMock.taslakKaydet.mockResolvedValue({ surum: 1, guncelleme: "2026-10-05T20:00:00+00:00", guncelleyen: "siz" });
    await ciz();
    await davaSec("QUICK-0501");

    // Kararlar karar rafından gelir; yazım açık olduğu için mahkeme kararlarının hepsi seçili gelir.
    const liste = test("lexis-kararlar")!;
    expect(servisMock.kartKararlari.mock.calls[0][0]).toBe(501);
    expect(liste.querySelectorAll("li")).toHaveLength(2);
    expect(liste.textContent).toContain("2/2 seçili");
    expect(liste.textContent).toContain("Başvuru reddi");
    expect(test("lexis-yazim-notu")!.textContent).toContain("Seçili 2 karar maskelenerek modele gönderilir");
    expect(test("lexis-iskelet-notu")).toBeNull();
    await tikla(liste.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[0]); // istinaf kararı yazım dışı
    expect(liste.textContent).toContain("1/2 seçili");

    // Gönderim onayı modele ne gideceğini söyler (K4): kararlar künyeleriyle, emsaller, model.
    await tikla(dugme("Taslağı yaz"));
    const onay = confirmMock.fn.mock.calls[0][0] as { body: string; confirmLabel: string; details: { label: string; value: string }[] };
    expect(onay.body).toContain(GERCEK_YAZIM_NOTU);
    expect(onay.confirmLabel).toBe("Gönder ve yaz");
    expect(onay.details.map((d) => d.label)).toEqual(["Modele gidecek kararlar", "Emsal raporlar", "Model", "Rapor"]);
    expect(onay.details[0].value).toBe("1 karar (maskeli) — Örnekköy 2. İdare Mahkemesi · 2019/123 E., 2021/456 K. · 05.05.2021");
    expect(onay.details[2].value).toBe("gemini-test");

    // Servise yalnız kimlikler gider; metni servis kendi veritabanından okuyup maskeler.
    expect(servisMock.yaz.mock.calls[0][0]).toMatchObject({ case_id: 501, iskelet: "KISA", karar_idleri: [71], emsal_sha: emsaller.map((e) => e.kayit.okuma.sha256) });
    const iddia = test("lexis-bolum-iddia")!;
    expect(iddia.querySelector("textarea")!.value).toBe("Davacı, ameliyat sonrası zarar gördüğünü ileri sürmüştür.");
    expect(iddia.textContent).toContain("Kaynak karar: Örnekköy 2. İdare Mahkemesi · 2019/123 E., 2021/456 K. · 05.05.2021");
    // Denetim alıntıyı kararın metninde bulur: madde "Doğrulandı", paragrafta uyarı yok.
    expect(maddeler()).toHaveLength(2);
    expect(rozetler(maddeler()[0])).toEqual(["Doğrulandı"]);
    expect(servisMock.kararGetir.mock.calls.map((c) => c[0])).toEqual([71]); // yalnız yazılan kararın metni istenir
    expect(test("lexis-uyarilar")!.textContent).not.toContain("dayanak alıntısı");
    expect(test("lexis-akis-hatasi")).toBeNull();

    // "Kaynakta göster" alıntıyı kararın metninde vurgular; künye kararı okuyucuda açar.
    await tikla(dugme("Kaynakta göster", maddeler()[0]));
    const dayanak = test("lexis-dayanak-karar")!;
    expect(dayanak.querySelector("mark")!.textContent).toBe("hekime atfı kabil kusur bulunmadığı bildirilmiştir");
    expect(dayanak.textContent).toContain("Karar: Örnekköy 2. İdare Mahkemesi · 2019/123 E., 2021/456 K. · 05.05.2021");
    await tikla(dayanak.querySelector("button")!);
    expect(document.querySelector('[data-testid="lexis-karar-okuyucu"]')!.textContent).toContain("2019/123 E., 2021/456 K.");

    // Taslak yazıldığı kararları ve karar seçimini taşır: yeniden açılınca denetim aynı kararlarda arar.
    await kaydiBekle();
    const kayit = servisMock.taslakKaydet.mock.calls[0][1] as { taslak: LexisTaslak; ekran: { secili_kararlar: number[] } };
    expect(kayit.taslak.kararlar).toEqual([71]);
    expect(kayit.ekran.secili_kararlar).toEqual([71]);
  });

  it("yazım kapalıyken kararlar yalnız okunur, taslak iskelettir; servis yazamazsa iskelet kalır ve uyarı görünür", async () => {
    servisMock.kartKararlari.mockResolvedValue({ kararlar: KARARLAR, yazim: { acik: false, neden: "kapali", model: null } });
    await ciz();
    await davaSec("QUICK-0501");
    const liste = test("lexis-kararlar")!;
    expect(liste.querySelectorAll("li")).toHaveLength(2);
    expect(liste.querySelector('input[type="checkbox"]')).toBeNull();
    expect(test("lexis-yazim-kapali")!.textContent).toContain("Kararlardan yazım bu kurulumda kapalı");
    expect(test("lexis-iskelet-notu")!.textContent).toBe(GERCEK_ISKELET_NOTU);
    await tikla(dugme("Taslağı yaz"));
    expect((confirmMock.fn.mock.calls[0][0] as { details: { label: string }[] }).details.map((d) => d.label)).toEqual(["Rapor"]);
    expect(servisMock.yaz).not.toHaveBeenCalled();
    expect(servisMock.iskelet).toHaveBeenCalledTimes(1);

    // Yazım açık ama servis yazamadı (model hatası): akış kesilmez, iskelet ekrandadır, neden görünür.
    servisMock.kartKararlari.mockResolvedValue({ kararlar: KARARLAR, yazim: { acik: true, neden: null, model: "gemini-test" } });
    servisMock.kararGetir.mockImplementation(async (id: number) => ayrinti(KARARLAR.find((k) => k.id === id)!));
    servisMock.yaz.mockRejectedValue(new LexisApiError(502, "Model yanıtı kullanılamadı; yeniden deneyin."));
    await tikla(dugme("Davayı değiştir"));
    await davaSec("QUICK-0502");
    await tikla(dugme("Taslağı yaz"));
    expect(servisMock.yaz).toHaveBeenCalledTimes(1);
    expect(test("lexis-akis-hatasi")!.textContent).toBe("Kararlardan yazım yapılamadı: Model yanıtı kullanılamadı; yeniden deneyin. Taslak iskelet olarak bırakıldı.");
    expect(maddeler()).toHaveLength(1); // iskeletin son (muallak) maddesi
    expect(test("lexis-bolum-hasar")!.querySelectorAll("input")).toHaveLength(1);
  });
});

describe("Tezgah — dosya bölgesi", () => {
  it("örnek kipte davanın kararları listelenir ve okuyucuda açılır; yazım seçimi yoktur", async () => {
    await ciz();
    await davaSec("AXA-9004");
    const liste = test("lexis-kararlar")!;
    expect(liste.querySelectorAll("li")).toHaveLength(2);
    expect(liste.textContent).toContain("Adana 1. İdare Mahkemesi");
    expect(liste.textContent).toContain("2023/404 E., 2025/118 K. · 12.03.2025");
    expect(liste.querySelector('input[type="checkbox"]')).toBeNull();
    await tikla(dugme("Adana 1. İdare Mahkemesi", liste));
    expect(document.querySelector('[data-testid="lexis-karar-okuyucu"]')!.querySelector('[aria-label="Hüküm"]')!.textContent).toContain("DAVANIN REDDİNE");

    await tikla(dugme("Davayı değiştir"));
    await davaSec("ANADOLU-9001");
    expect(test("lexis-kararlar")!.textContent).toContain("Bu dava kartına bağlı karar yok.");
  });

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

  it("eksik belge uyarılır ve HUKDOK yüklemesine bağlanır; emsal çıkarılabilir", async () => {
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
    expect(test("lexis-bolum-degerlendirme")!.textContent).toContain("Sulhe Uygunluk Durumu");
  });

  it("ek raporda künye ayrı bölümdür; sulh satırı yalnız Anadolu biçiminde vardır", async () => {
    await ciz();
    await taslakYaz("AXA-9004");

    expect(test("lexis-bolum-gezgini")!.querySelectorAll("button")).toHaveLength(3);
    expect(test("lexis-bolum-kunye")!.querySelectorAll("input")).toHaveLength(3);        // Konu, Sigortalı, Poliçe No
    expect(test("lexis-bolum-degerlendirme")!.textContent).not.toContain("Sulhe Uygunluk Durumu");
    expect(test("lexis-kunye")!.textContent).toContain("Ek rapor (2 bölüm)");           // künye raporun bölümü sayılmaz
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

  it("Word indir taslağı servise gönderir; başarıda uyarı özetini, hatada servisin metnini gösterir", async () => {
    await ciz();
    await taslakYaz("AXA-9004");
    expect(test("lexis-cikti-cubugu")!.textContent).toContain("Denetim temiz");

    wordMock.wordIndir.mockResolvedValueOnce({ dosya_adi: "Lexis_x_ANA_taslak.docx", uyari_sayisi: 4, uyarilar: ["alan boş: talep_tarihi", "bölüm boş: beyan"] });
    await tikla(dugme("Word indir"));
    expect((wordMock.wordIndir.mock.calls[0][0] as { case_id: number }).case_id).toBe(9004);
    expect(toastMocks.success).toHaveBeenCalledWith("Word indirildi", { description: "4 uyarı: alan boş: talep_tarihi · bölüm boş: beyan" });
    expect(toastMocks.error).not.toHaveBeenCalled();

    wordMock.wordIndir.mockResolvedValueOnce({ dosya_adi: "Lexis_x_ANA_taslak.docx", uyari_sayisi: 0, uyarilar: [] });
    await tikla(dugme("Word indir"));
    expect(toastMocks.success).toHaveBeenLastCalledWith("Word indirildi", { description: "Lexis_x_ANA_taslak.docx" });

    wordMock.wordIndir.mockRejectedValueOnce(new LexisApiError(422, "Word çıktısı şimdilik yalnız Anadolu biçiminde üretiliyor."));
    await tikla(dugme("Word indir"));
    expect(toastMocks.error).toHaveBeenCalledWith("Word indirilemedi", { description: "Word çıktısı şimdilik yalnız Anadolu biçiminde üretiliyor." });
    expect(dugme("Word indir").disabled).toBe(false);

    // PDF indir: aynı uç, `bicim: "pdf"` (servis LibreOffice'le çevirir)
    wordMock.wordIndir.mockResolvedValueOnce({ dosya_adi: "Lexis_x_ANA_taslak.pdf", uyari_sayisi: 0, uyarilar: [] });
    await tikla(dugme("PDF indir"));
    expect(wordMock.wordIndir.mock.calls.at(-1)?.[3]).toBe("pdf"); // lexisWord.wordIndir(taslak, künye, signal, bicim)
    expect(toastMocks.success).toHaveBeenLastCalledWith("PDF indirildi", { description: "Lexis_x_ANA_taslak.pdf" });
    wordMock.wordIndir.mockRejectedValueOnce(new LexisApiError(503, "PDF üretici sunucuda kurulu değil; Word indirip Word'den PDF'e aktarın."));
    await tikla(dugme("PDF indir"));
    expect(toastMocks.error).toHaveBeenLastCalledWith("PDF indirilemedi", { description: "PDF üretici sunucuda kurulu değil; Word indirip Word'den PDF'e aktarın." });
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

// --- emsal ajanı: "Bu dosyaya emsal bul" → taslak `emsal_kararlar` (K27 / K28; G264) ---
describe("Tezgah — emsal kararlar", () => {
  const emsalListesi = () => test("lexis-emsal-kararlar")!;
  const oneriler = () => Array.from(document.querySelectorAll<HTMLElement>('[data-testid="lexis-emsal-oneri"]'));
  const diyalog = () => document.querySelector<HTMLElement>('[data-testid="lexis-emsal-bul"]');

  it("örnek kip: belge satırından ajan açılır; onaylananlar 'Emsal kararlar' listesine biner, kararlar listesine dokunmaz; yeniden aramada kilitli, kaldırılabilir, okuyucuda açılır", async () => {
    await ciz();
    await davaSec("AXA-9004");
    expect(emsalListesi().textContent).toContain("Emsal karar seçilmedi");
    expect(test("lexis-belgeler")!.querySelectorAll('[aria-label^="Bu belgeye emsal bul"]')).toHaveLength(ORNEK_SAYILAR.belge);

    await tikla(dugme("Bu belgeye emsal bul: Dava dilekçesi"));
    expect(diyalog()!.querySelector<HTMLInputElement>('input[type="radio"]:checked')!.closest("label")!.textContent).toContain("Dava dilekçesi");
    await tikla(dugme("Belgeyi hazırla"));
    await tikla(dugme("Ara"));
    await bekle(24);
    expect(oneriler()).toHaveLength(5);
    await tikla(oneriler()[1].querySelector<HTMLInputElement>('input[type="checkbox"]')!);
    await tikla(oneriler()[2].querySelector<HTMLInputElement>('input[type="checkbox"]')!);
    await tikla(dugme("Taslağa ekle (2)"));
    expect(diyalog()).toBeNull();
    expect(toastMocks.success).toHaveBeenCalledWith("2 emsal karar taslağa eklendi", expect.anything());

    const satirlar = emsalListesi().querySelectorAll("li");
    expect(satirlar).toHaveLength(2);
    expect(satirlar[0].textContent).toContain("Mersin 2. İdare Mahkemesi · 2022/310 E., 2024/455 K. · 14.05.2024");
    expect(satirlar[1].textContent).toContain("Ankara 12. Asliye Hukuk Mahkemesi");
    expect(test("lexis-kararlar")!.querySelectorAll("li")).toHaveLength(2); // kartın kararları (yazım girdisi) değişmedi

    // Rafta olmayan uydurma emsal karar da okuyucuda açılır.
    await tikla(dugme("Mersin 2. İdare Mahkemesi · 2022/310 E., 2024/455 K. · 14.05.2024", emsalListesi()));
    const okuyucu = document.querySelector<HTMLElement>('[data-testid="lexis-karar-okuyucu"]')!;
    expect(okuyucu.textContent).toContain("2022/310 E., 2024/455 K.");
    await tikla(dugme("Close", okuyucu));

    // Taslak yazılınca emsal kararlar korunur; yeni aramada taslaktakiler kilitli gelir.
    await tikla(dugme("Taslağı yaz"));
    expect(emsalListesi().querySelectorAll("li")).toHaveLength(2);
    await tikla(dugme("Bu dosyaya emsal bul"));
    await tikla(diyalog()!.querySelector<HTMLInputElement>('input[type="radio"]')!);
    await tikla(dugme("Belgeyi hazırla"));
    await tikla(dugme("Ara"));
    await bekle(24);
    const kutu = oneriler()[1].querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(kutu.checked).toBe(true);
    expect(kutu.disabled).toBe(true);
    expect(oneriler()[1].textContent).toContain("taslakta");
    expect(dugme("Taslağa ekle").disabled).toBe(true);
    await tikla(dugme("Close", diyalog()!));

    await tikla(dugme("Emsal kararı çıkar: Mersin 2. İdare Mahkemesi · 2022/310 E., 2024/455 K. · 14.05.2024"));
    expect(emsalListesi().querySelectorAll("li")).toHaveLength(1);
  });

  describe("gerçek dava kipi", () => {
    const GECIKME = 40;
    const MUALLAK = { maddi: null, manevi: null, dayanak: "YOK" as const, dayanak_satirlari: [], kusur_tespiti: "BELIRSIZ" as const, risk_duzeyi: "BELIRSIZ" as const, teminat: "BELIRSIZ" as const, uyarilar: [] };
    const GIRIS = "Tarafımıza iletilen belge ve bilgiler ile yapılan inceleme neticesinde;";
    const KARAR_METNI = "Bilirkişi raporunda hekime atfı kabil kusur bulunmadığı bildirilmiştir. HÜKÜM: Davanın REDDİNE 05.05.2021 tarihinde karar verildi.";
    const karar = (id: number, p: Partial<RafKarari> = {}): RafKarari => ({
      id, belge_turu: "karar", mahkeme: "Örnekköy 2. İdare Mahkemesi", derece: "YEREL", esas_no: "2019/123", karar_no: "2021/456", karar_tarihi: "2021-05-05",
      uzmanlik: null, kart_id: 501, kart_bagi: "TEK_KART", asamaya_bagli: true, metin_uzunluk: KARAR_METNI.length, hukum_sinifi: "RED_ESASTAN", hukum_yonleri: ["RED"],
      sonuc_muvekkil: "RED_ESASTAN", sonuc_iliskisi: "AYNI", hukmedilen_maddi: [], hukmedilen_manevi: [], hukmedilen_birlesik: [], talep_maddi: [], talep_manevi: [],
      olay: null, maluliyet_orani: [], kusur_orani: [], dayanak_kurul: [], faiz: [], konular: {}, ...p,
    });
    const KARARLAR = [karar(72, { mahkeme: "Örnek BAM 3. İdari Dava Dairesi", derece: "ISTINAF", esas_no: "2021/900", karar_no: "2022/15", karar_tarihi: "2022-02-01", hukum_sinifi: "BASVURU_RET", sonuc_muvekkil: "BASVURU_RET" }), karar(71)];
    // Başka kartın kararı: ajanın önerisi (yazım girdisi DEĞİL).
    const EMSAL = karar(73, { mahkeme: "Örnekköy 4. İdare Mahkemesi", esas_no: "2020/55", karar_no: "2022/301", karar_tarihi: "2022-06-15", kart_id: 777 });
    const ayrinti = (k: RafKarari) => ({ ...k, kunye_kaynak: {}, vekalet_ucreti: [], yargilama_gideri: [], hukum_kaynagi: null, yas: [], davaci_sayisi: null, parcalar: { hukum: null, iddia: [], savunma: [], gerekce: [] }, metin: KARAR_METNI });
    const ONERI: EmsalOnerisi = { ...EMSAL, puan: 88, gerekce: "Aynı olay.", alinti: "hekime atfı kabil kusur bulunmadığı bildirilmiştir", fark: "Başka kart.", ayni_kart: false, kaynak: "model", fts_sira: 1, denetim_uyarilari: [], bilesenler: [] };
    const SHA = "c".repeat(64);
    const TAMAM: EmsalAkisOlayi = { status: "complete", sha256: SHA, kunye: { uzmanlik: null, tibbi_islem: null, iddia: "", taraf_turu: null, yargi_yolu: "IDARE", sorgular: [] }, model: "sahte", sorgu_modeli: "sahte", oneriler: [ONERI], sayilar: { aday: 1, okunan: 1, dusen: 0, onbellek: 0, model_cagrisi: 2, token: 0, saniye: 0.3 } };
    let dosya: DosyaGirdisi;

    async function kaydiBekle() {
      await act(async () => {
        await new Promise((r) => setTimeout(r, GECIKME + 60));
      });
      await bekle();
    }

    beforeEach(async () => {
      kayitGecikmesiAyarla(GECIKME);
      const ornek = await lexisApi.dosyaGetir(9003);
      const dava = { ...ornek.dava, case_id: 501, ofis_no: "QUICK-0501-DR.GERCEK-HUK" };
      dosya = { ...ornek, dava, onceki_rapor: null };
      servisMock.davaAra.mockResolvedValue([dava]);
      servisMock.dosyaGetir.mockResolvedValue(dosya);
      servisMock.emsalOner.mockResolvedValue([]);
      servisMock.kararBankasi.mockResolvedValue([]);
      servisMock.taslakGetir.mockResolvedValue(null);
      servisMock.iskelet.mockResolvedValue({
        etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: dosya.sigortali, zorunlu: true, kaynak: "KART" }] },
        ozet: {},
        degerlendirme: { giris: GIRIS, maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
        muallak: MUALLAK,
        kosu_id: 77,
      });
      servisMock.kararGetir.mockImplementation(async (id: number) => {
        const k = [...KARARLAR, EMSAL].find((x) => x.id === id);
        if (!k) throw new LexisApiError(404, "Karar rafta bulunamadı.");
        return ayrinti(k);
      });
      servisMock.taslakKaydet.mockResolvedValue({ surum: 1, guncelleme: "2026-10-07T20:00:00+00:00", guncelleyen: "siz" });
      servisMock.emsalDurum.mockResolvedValue(ORNEK_EMSAL_DURUMU);
      servisMock.emsalBelgeKarttan.mockResolvedValue({ sha256: SHA, kaynak: "kart", bicim: "pdf", boyut: 90_000, sayfa: 5, metin_uzunluk: 7_000, bolumler: [], maske_dokumu: { bilinen: 2, kalip: 0, ogrenilen: 0 }, case_id: 501, hukdok_belge_id: dosya.belgeler[0].id, yukleme: "2026-10-07T20:00:00+00:00", mevcut: false, arsiv: "gerekmiyor", sharepoint_url: null });
      servisMock.emsalAra.mockImplementation(async function* () {
        yield TAMAM;
      });
      veriKipiAyarla("gercek");
    });

    afterEach(() => kayitGecikmesiAyarla(KAYIT_GECIKMESI));

    it("emsal karar yazıma GİTMEZ: /yaz yalnız seçili kararları alır, kayıt emsal_kararlar'ı taşır; kaldırınca boş listeyle kaydedilir", async () => {
      servisMock.kartKararlari.mockResolvedValue({ kararlar: KARARLAR, yazim: { acik: true, neden: null, model: "gemini-test" } });
      servisMock.yaz.mockResolvedValue({
        ozet: {},
        degerlendirme: { giris: GIRIS, maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
        muallak: MUALLAK,
        kararlar: [72, 71],
        uyarilar: [],
        model: "gemini-test",
        maske: { bilinen: 2, kalip: 0, ogrenilen: 0 },
        gonderilen_karakter: 100,
      });
      await ciz();
      await davaSec("QUICK-0501");
      expect(test("lexis-kararlar")!.textContent).toContain("2/2 seçili");

      await tikla(dugme(`Bu belgeye emsal bul: ${dosya.belgeler[0].ad}`));
      await tikla(dugme("Belgeyi hazırla"));
      expect(servisMock.emsalBelgeKarttan.mock.calls[0].slice(0, 2)).toEqual([501, dosya.belgeler[0].id]);
      await tikla(dugme("Ara"));
      await bekle(8);
      expect(servisMock.emsalAra.mock.calls[0][0]).toBe(SHA);
      await tikla(oneriler()[0].querySelector<HTMLInputElement>('input[type="checkbox"]')!);
      await tikla(dugme("Taslağa ekle (1)"));
      expect(emsalListesi().textContent).toContain("Örnekköy 4. İdare Mahkemesi · 2020/55 E., 2022/301 K. · 15.06.2022");
      expect(test("lexis-kararlar")!.textContent).toContain("2/2 seçili"); // yazım seçimi değişmedi
      expect(test("lexis-yazim-notu")!.textContent).toContain("Seçili 2 karar");

      await tikla(dugme("Taslağı yaz"));
      const yazIstegi = servisMock.yaz.mock.calls[0][0] as { karar_idleri: number[] };
      expect(yazIstegi.karar_idleri).toEqual([72, 71]);
      expect(yazIstegi.karar_idleri).not.toContain(73);
      expect(emsalListesi().querySelectorAll("li")).toHaveLength(1);
      await kaydiBekle();
      const kayit = servisMock.taslakKaydet.mock.calls[0][1] as { taslak: LexisTaslak; ekran: { secili_kararlar: number[] } };
      expect(kayit.taslak.emsal_kararlar).toEqual([73]);
      expect(kayit.taslak.kararlar).toEqual([72, 71]);
      expect(kayit.ekran.secili_kararlar).toEqual([71, 72]);
      // Denetim emsal kararı aramaz: yalnız yazılan kararların metni istenir (K28).
      expect(servisMock.kararGetir.mock.calls.map((c) => c[0])).not.toContain(73);

      await tikla(dugme("Emsal kararı çıkar: Örnekköy 4. İdare Mahkemesi · 2020/55 E., 2022/301 K. · 15.06.2022"));
      expect(emsalListesi().textContent).toContain("Emsal karar seçilmedi");
      await kaydiBekle();
      expect((servisMock.taslakKaydet.mock.calls.at(-1)![1] as { taslak: LexisTaslak }).taslak.emsal_kararlar).toEqual([]);
    });

    it("kayıtlı taslağın emsal kararları raftan künyesiyle geri açılır; alınamayan karar uyarı düşer, açmak yazmaz", async () => {
      const taslak: LexisTaslak = {
        case_id: 501, sirket: "QUICK", rapor_turu: "ANA", iskelet: "KISA",
        etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: "Dr. Kayıtlı", zorunlu: true, kaynak: "ELLE" }] },
        ozet: {},
        degerlendirme: { giris: GIRIS, maddeler: [{ metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null }], sulh_uygunluk: "", muallak_gerekcesi: "" },
        muallak: MUALLAK, muallak_maddi: null, muallak_manevi: null, emsaller: [], emsal_kararlar: [73, 999],
      };
      const kayitli: KayitliTaslak = { taslak, ekran: {}, surum: 2, kosu_id: 41, guncelleyen: "ikinci@ornek.test", guncelleme: "2026-10-07T17:30:00+00:00" };
      servisMock.taslakGetir.mockResolvedValue(kayitli);
      await ciz();
      await davaSec("QUICK-0501");
      expect(emsalListesi().querySelectorAll("li")).toHaveLength(1);
      expect(emsalListesi().textContent).toContain("Örnekköy 4. İdare Mahkemesi · 2020/55 E., 2022/301 K. · 15.06.2022");
      expect(emsalListesi().textContent).toContain("1 emsal kararı raftan alınamadı");
      expect(servisMock.kararGetir.mock.calls.map((c) => c[0]).sort()).toEqual([73, 999]);
      await kaydiBekle();
      expect(servisMock.taslakKaydet).not.toHaveBeenCalled();
    });
  });
});

/** Örnek kipte AXA-9004 kartının belge sayısı (hepsi uzantısız: emsal düğmesi her satırda). */
const ORNEK_SAYILAR = { belge: 5 };
