import { describe, expect, it } from "vitest";

import {
  etkinHizmetler,
  hizmetEksikMesaji,
  hizmetsizMuvekkiller,
  ilkDoluKume,
  KATEGORI_ON_SECIM_HIZMETI,
  onSecimHizmetleri,
} from "./muvekkilHizmetleri";

// G253 — müvekkil başına hizmet seçiminin ortak saf kuralları (üç ekran bunları kullanır).

// Seed sırası (backend `seed_data.SERVICE_TYPES`) — bilinçli alfabetik DEĞİL.
const LISTE = [
  "Takip (doktor müvekkil)",
  "Lexis Rapor",
  "Vekaletsiz Takip",
  "Vekaletli Takip",
  "Vekalet Ücreti Alacağı",
  "Takip (hasta vekilliği)",
  "Takip (kurum vekilliği)",
  "Danışmanlık",
  "Takip (sağlık personeli)",
];

describe("KATEGORI_ON_SECIM_HIZMETI — ön seçim eşlemesi tek sabitte", () => {
  it("eşleme tam üç kategori taşır: Doktor, Hasta, Kurum", () => {
    expect(KATEGORI_ON_SECIM_HIZMETI).toEqual({
      doktor: "Takip (doktor müvekkil)",
      hasta: "Takip (hasta vekilliği)",
      kurum: "Takip (kurum vekilliği)",
    });
  });

  it("eşlemenin her hedefi seed hizmet listesinde var (yazım kayması bekçisi)", () => {
    for (const hedef of Object.values(KATEGORI_ON_SECIM_HIZMETI)) expect(LISTE).toContain(hedef);
  });
});

describe("onSecimHizmetleri", () => {
  it.each([
    ["Doktor", "Takip (doktor müvekkil)"],
    ["Hasta", "Takip (hasta vekilliği)"],
    ["Kurum", "Takip (kurum vekilliği)"],
  ])("%s → %s", (kategori, hizmet) => {
    expect(onSecimHizmetleri(kategori, LISTE)).toEqual([hizmet]);
  });

  it("kategori yazımı katlanarak eşleşir (büyük harf, boşluk)", () => {
    expect(onSecimHizmetleri("DOKTOR", LISTE)).toEqual(["Takip (doktor müvekkil)"]);
    expect(onSecimHizmetleri("  kurum ", LISTE)).toEqual(["Takip (kurum vekilliği)"]);
  });

  it.each([
    ["bilgi yok (undefined)", undefined],
    ["bilgi yok (null)", null],
    ["boş", ""],
    ["Özel Hastane ('hasta' içerir ama Hasta DEĞİL)", "Özel Hastane"],
    ["Sağlık Çalışanı", "Sağlık Çalışanı"],
    ["Sigorta Şirketi", "Sigorta Şirketi"],
    ["Bireysel", "Bireysel"],
    ["Diğer", "Diğer"],
  ])("ön seçim yok: %s", (_etiket, kategori) => {
    expect(onSecimHizmetleri(kategori, LISTE)).toEqual([]);
  });

  it("önerilen hizmet listede yoksa (ya da liste boşsa) ön seçim yapılmaz — listede olmayan ad 422'dir", () => {
    expect(onSecimHizmetleri("Doktor", ["Danışmanlık", "Lexis Rapor"])).toEqual([]);
    expect(onSecimHizmetleri("Doktor", [])).toEqual([]);
  });

  it("öneri LİSTEDEKİ yazımla döner (liste panelden yeniden adlandırılmış olabilir)", () => {
    expect(onSecimHizmetleri("Doktor", ["Danışmanlık", "Takip (Doktor Müvekkil)"]))
      .toEqual(["Takip (Doktor Müvekkil)"]);
  });
});

describe("etkinHizmetler — açık seçim ön seçimi ezer", () => {
  it("seçiciye dokunulmadıysa (undefined/null) kategoriye göre ön seçim döner", () => {
    expect(etkinHizmetler(undefined, "Hasta", LISTE)).toEqual(["Takip (hasta vekilliği)"]);
    expect(etkinHizmetler(null, "Hasta", LISTE)).toEqual(["Takip (hasta vekilliği)"]);
    expect(etkinHizmetler(undefined, undefined, LISTE)).toEqual([]);
  });

  it("kullanıcının seçimi kategoriye bakılmadan aynen döner", () => {
    expect(etkinHizmetler(["Danışmanlık", "Lexis Rapor"], "Doktor", LISTE)).toEqual(["Danışmanlık", "Lexis Rapor"]);
  });

  it("kullanıcı ön seçimi kaldırdıysa (boş dizi) ön seçim GERİ GELMEZ", () => {
    expect(etkinHizmetler([], "Doktor", LISTE)).toEqual([]);
  });

  it("dönen dizi girdinin kopyasıdır (state dizisi dışarıdan değişmez)", () => {
    const secim = ["Danışmanlık"];
    const sonuc = etkinHizmetler(secim, "Doktor", LISTE);
    expect(sonuc).toEqual(secim);
    expect(sonuc).not.toBe(secim);
  });
});

describe("ilkDoluKume — 'tüm müvekkillere uygula' kaynağı", () => {
  it("sırayla İLK dolu kümeyi (kopya olarak) verir", () => {
    const ikinci = ["Lexis Rapor"];
    const sonuc = ilkDoluKume([[], ikinci, ["Danışmanlık"]]);
    expect(sonuc).toEqual(["Lexis Rapor"]);
    expect(sonuc).not.toBe(ikinci);
  });

  it("hiçbiri dolu değilse null", () => {
    expect(ilkDoluKume([[], []])).toBeNull();
    expect(ilkDoluKume([])).toBeNull();
  });
});

describe("hizmetsizMuvekkiller — Kaydet kapısı (backend 422 kuralının ikizi)", () => {
  it("hizmeti olmayan müvekkilleri adıyla sayar", () => {
    expect(hizmetsizMuvekkiller([
      { name: "Dr. Ahmet Yılmaz", hizmetler: ["Takip (doktor müvekkil)"] },
      { name: " Ayşe Kaya ", hizmetler: [] },
      { name: "Özel Şifa Hastanesi", hizmetler: [] },
    ], LISTE)).toEqual(["Ayşe Kaya", "Özel Şifa Hastanesi"]);
  });

  it("adsız (boş) satır müvekkil sayılmaz", () => {
    expect(hizmetsizMuvekkiller([{ name: "  ", hizmetler: [] }], LISTE)).toEqual([]);
  });

  it("herkesin hizmeti varsa boş liste", () => {
    expect(hizmetsizMuvekkiller([{ name: "A", hizmetler: ["Danışmanlık"] }], LISTE)).toEqual([]);
  });

  it("hizmet listesi BOŞSA zorunluluk aranmaz (backend ile aynı: seçilecek hizmet yok)", () => {
    expect(hizmetsizMuvekkiller([{ name: "Ayşe Kaya", hizmetler: [] }], [])).toEqual([]);
  });
});

describe("hizmetEksikMesaji", () => {
  it("backend 422 metniyle aynı kalıpta, müvekkilleri adıyla sayar", () => {
    expect(hizmetEksikMesaji(["Ayşe Kaya", "Özel Şifa Hastanesi"])).toBe(
      'Hizmet türü seçilmemiş müvekkil var: "Ayşe Kaya", "Özel Şifa Hastanesi". '
      + "Her müvekkil için en az bir hizmet türü seçin.",
    );
  });
});
