// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { EMPTY_NEW_CASE_FORM, type NewCaseFormValues } from "@/lib/newCaseDraft";
import { buildCasePayload, editModeFormValues, type CasePayloadInput } from "@/lib/newCasePayload";

// =====================================================================
// G020 — `service_type` kayıt yüküne giriyor mu?
//
// Canlı DB ölçümü (2026-08-11): `SELECT count(*), count(service_type) FROM cases`
// → 14.345 / 0. Kullanıcı hizmet türünü seçiyordu, zorunlu-alan denetimi onu
// görüyordu, ama POST/PUT gövdesine hiç konmuyordu; iki `as CaseData` cast'i
// derleyicinin uyarısını susturuyordu. Bu testler yükü doğrudan doğrular.
//
// G253 (test taşıma, 02.10 kullanıcı izni): hizmet artık 5'li maske değil, MÜVEKKİL
// BAŞINA kümedir — yük `parties[i].hizmet_turleri` taşır (backend G250). Eski maske
// (`service_type`) yeni kayıtta gövdeye girmez; düzenlemede yalnız kayıttaki değer
// korunmak üzere geri gider (backend PUT'ta alan yoksa kolonu boşaltıyor).
// =====================================================================

const form = (over: Partial<NewCaseFormValues> = {}): NewCaseFormValues => ({
  ...EMPTY_NEW_CASE_FORM,
  ...over,
});

const input = (over: Partial<CasePayloadInput> = {}): CasePayloadInput => ({
  // G237 (test taşıma): girdide ofis numarası (eski `trackingNo`) YOK — numarayı
  // sunucu verir; yeni kayıt girdisi yerine istek kimliği taşır.
  istekKimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a",
  status: "DERDEST",
  formData: form(),
  clients: [{ name: "", role: "Davacı" }],
  counterParties: [{ name: "", role: "Davalı" }],
  thirdParties: [],
  dbClients: [],
  lawyers: [],
  ...over,
});

describe("buildCasePayload — service_type", () => {
  // G253 taşıma: eski beklenti `formData.serviceType "00110"` → `payload.service_type "00110"`.
  it("seçilen hizmet türünü kayıt yüküne koyar", () => {
    const payload = buildCasePayload(input({
      clients: [{ name: "Ahmet Yılmaz", role: "Davacı", hizmet_turleri: ["Takip (doktor müvekkil)", "Danışmanlık"] }],
    }));

    expect(payload.parties[0].hizmet_turleri).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
  });

  // G253 taşıma: eski beklenti "hiç seçim yapılmasa da `service_type` '00000' gider, boş kalmaz"
  // (zorunlu alan sayılıyordu). `service_type` artık zorunlu alan DEĞİL (G250) ve hiçbir şeyi
  // beslemiyor → yeni kayıtta gövdeye hiç girmez; seçimsiz müvekkil boş kümeyle gider
  // (kullanıcı yolunda backend bunu 422'ler — ekran Kaydet'i zaten kapatır).
  it("hiç seçim yapılmasa eski maske gövdeye girmez; müvekkil boş hizmet kümesiyle gider", () => {
    const payload = buildCasePayload(input({
      clients: [{ name: "Ahmet Yılmaz", role: "Davacı", hizmet_turleri: [] }],
    }));

    expect(payload).not.toHaveProperty("service_type");
    expect(payload.parties[0].hizmet_turleri).toEqual([]);
  });

  // G253 taşıma: eski beklenti `loaded.serviceType "01001"` + `payload.service_type "01001"`.
  // Maske artık form değeri değil (düzenlenemez); kayıttaki değer `mevcutServiceType` ile
  // taşınır ve PUT gövdesine aynen girer — backend alan yoksa kolonu boşaltırdı.
  it("düzenleme modunda mevcut değer kaydetmede kaybolmaz", () => {
    // Düzenleme yolu: kayıt → forma yüklenir → forma dokunulmadan kaydedilir.
    const kayit = {
      tracking_no: "2026.00001.HUK.01.00100",
      status: "DERDEST",
      service_type: "01001",
    };
    const loaded = editModeFormValues(kayit);
    expect(loaded).not.toHaveProperty("serviceType");

    const payload = buildCasePayload(input({
      istekKimligi: undefined, formData: loaded, mevcutServiceType: kayit.service_type,
    }));
    expect(payload.service_type).toBe("01001");
  });

  // G253 taşıma: eski beklenti "boş maske forma '00000' olarak yüklenir" (ve her düzenleme
  // kolona '00000' yazardı). Artık boş maske için gövdeye hiçbir değer üretilmez.
  it("düzenlenen kayıtta hizmet türü boşsa gövdeye varsayılan maske YAZILMAZ", () => {
    const loaded = editModeFormValues({ tracking_no: "X", status: "DERDEST" });
    expect(loaded).not.toHaveProperty("serviceType");

    const payload = buildCasePayload(input({ istekKimligi: undefined, formData: loaded }));
    expect(payload).not.toHaveProperty("service_type");
  });
});

// G253: hizmet müvekkil başınadır — her müvekkil KENDİ kümesini taşır (muhasebe ayrımı).
describe("buildCasePayload — müvekkil başına hizmet (G253)", () => {
  it("iki müvekkilli kayıtta her müvekkil kendi hizmet kümesiyle gider", () => {
    const payload = buildCasePayload(input({
      clients: [
        { name: "Dr. Ahmet Yılmaz", role: "Davalı", hizmet_turleri: ["Takip (doktor müvekkil)"] },
        { name: "Özel Şifa Hastanesi", role: "Davalı", hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] },
      ],
      counterParties: [{ name: "Mehmet Kaya", role: "Davacı" }],
      thirdParties: [{ name: "Tanık Bir", role: "Tanık" }],
    }));

    expect(payload.parties).toEqual([
      { client_id: undefined, name: "Dr. Ahmet Yılmaz", role: "Davalı", party_type: "CLIENT", hizmet_turleri: ["Takip (doktor müvekkil)"] },
      { client_id: undefined, name: "Özel Şifa Hastanesi", role: "Davalı", party_type: "CLIENT", hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] },
      { name: "Mehmet Kaya", role: "Davacı", party_type: "COUNTER", tc_no: undefined },
      { name: "Tanık Bir", role: "Tanık", party_type: "THIRD", tc_no: undefined },
    ]);
  });

  it("hizmet yalnız müvekkil tarafında gider — karşı taraf / üçüncü kişi alanı HİÇ taşımaz (backend 422)", () => {
    const payload = buildCasePayload(input({
      clients: [{ name: "Ahmet Yılmaz", role: "Davacı", hizmet_turleri: ["Danışmanlık"] }],
      counterParties: [{ name: "Mehmet Kaya", role: "Davalı" }],
      thirdParties: [{ name: "Tanık Bir", role: "Tanık" }],
    }));

    const digerleri = payload.parties.filter(p => p.party_type !== "CLIENT");
    expect(digerleri).toHaveLength(2);
    for (const taraf of digerleri) expect(taraf).not.toHaveProperty("hizmet_turleri");
  });

  it("';' ile bölünen satırdaki her ad satırın kümesini alır (ayrı dizi kopyalarıyla)", () => {
    const payload = buildCasePayload(input({
      clients: [{ name: "Ahmet Yılmaz; Ayşe Yılmaz", role: "Davacı", hizmet_turleri: ["Vekaletli Takip"] }],
    }));

    expect(payload.parties.map(p => p.name)).toEqual(["Ahmet Yılmaz", "Ayşe Yılmaz"]);
    expect(payload.parties[0].hizmet_turleri).toEqual(["Vekaletli Takip"]);
    expect(payload.parties[1].hizmet_turleri).toEqual(["Vekaletli Takip"]);
    expect(payload.parties[0].hizmet_turleri).not.toBe(payload.parties[1].hizmet_turleri);
  });

  it("düzenlemede (satır hizmet taşımaz) müvekkil tarafı gövdeye hizmet_turleri KOYMAZ", () => {
    const payload = buildCasePayload(input({
      istekKimligi: undefined,
      clients: [{ name: "Ahmet Yılmaz", role: "Davacı" }],
    }));

    expect(payload.parties).toHaveLength(1);
    expect(payload.parties[0]).not.toHaveProperty("hizmet_turleri");
  });

  it("yeni kayıt gövdesinde eski 5'li maske (service_type) hiçbir girdide yoktur", () => {
    const payloads = [
      buildCasePayload(input()),
      buildCasePayload(input({ status: "DANIŞ", clients: [{ name: "Ahmet Yılmaz", role: "Davacı", hizmet_turleri: ["Danışmanlık"] }] })),
    ];
    for (const payload of payloads) expect(Object.keys(payload)).not.toContain("service_type");
  });
});

describe("buildCasePayload — gövdenin geri kalanı (refactor regresyonu)", () => {
  it("form alanlarını backend adlarıyla taşır", () => {
    const payload = buildCasePayload(input({
      status: "DANIŞ",
      formData: form({
        esasNo: "2026/123",
        fileType: "Hukuk",
        subType: "Asliye Hukuk",
        subject: "Tazminat",
        court: "İstanbul 1. Asliye Hukuk Mahkemesi",
        fileOpeningDate: "2026-01-05",
        lawyer: "Av. Ayşe Yılmaz",
        uyapLawyer: "Av. Ali Demir",
        maddiTazminat: "1500",
        maneviTazminat: "",
        judicialUnit: "Asliye",
        notes: "not",
      }),
    }));

    // G237 (test taşıma): eski beklenti `tracking_no: "2026.00001.HUK.01.00100"` idi —
    // numara artık gövdeye GİRMEZ; yerine istek kimliği gider.
    expect(payload).not.toHaveProperty("tracking_no");
    expect(payload).toMatchObject({
      istek_kimligi: "3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a",
      status: "DANIŞ",
      esas_no: "2026/123",
      file_type: "Hukuk",
      sub_type: "Asliye Hukuk",
      subject: "Tazminat",
      court: "İstanbul 1. Asliye Hukuk Mahkemesi",
      opening_date: "2026-01-05",
      responsible_lawyer_name: "Av. Ayşe Yılmaz",
      uyap_lawyer_name: "Av. Ali Demir",
      maddi_tazminat: 1500,
      manevi_tazminat: 0,
      judicial_unit: "Asliye",
      notes: "not",
    });
    // Boş metin alanları gövdeye "" olarak değil, hiç gitmez
    expect(payload.acceptance_date).toBeUndefined();
    expect(payload.bureau_type).toBeUndefined();
  });

  it("';' ile yazılan çoklu isimleri ayrı taraflara böler, kayıtlı müvekkili client_id ile bağlar", () => {
    const payload = buildCasePayload(input({
      clients: [{ name: "Ahmet Yılmaz; Ayşe Yılmaz", role: "Davacı" }],
      counterParties: [{ name: "Mehmet Kaya", role: "Davalı", tc_no: "12345678901" }],
      thirdParties: [{ name: "Tanık Bir; Tanık İki", role: "Tanık", tc_no: "98765432109" }],
      dbClients: [{ id: 7, name: "ayşe yılmaz" }],
    }));

    expect(payload.parties).toEqual([
      { client_id: undefined, name: "Ahmet Yılmaz", role: "Davacı", party_type: "CLIENT" },
      { client_id: 7, name: "Ayşe Yılmaz", role: "Davacı", party_type: "CLIENT" },
      { name: "Mehmet Kaya", role: "Davalı", party_type: "COUNTER", tc_no: "12345678901" },
      // Çoklu isimde TC kime ait belirsiz — düşürülür
      { name: "Tanık Bir", role: "Tanık", party_type: "THIRD", tc_no: undefined },
      { name: "Tanık İki", role: "Tanık", party_type: "THIRD", tc_no: undefined },
    ]);
  });

  it("boş taraf satırlarını yüke koymaz", () => {
    const payload = buildCasePayload(input());

    expect(payload.parties).toEqual([]);
  });
});

// G237: numarayı sunucu verir (karar 023) — istek gövdesi numara taşımaz, kimlik taşır.
describe("buildCasePayload — ofis numarası yok, istek kimliği var (G237)", () => {
  it("hiçbir girdide gövdeye tracking_no girmez", () => {
    const payloads = [
      buildCasePayload(input()),
      buildCasePayload(input({ status: "DANIŞ", clients: [{ name: "Ahmet Yılmaz", role: "Davacı" }] })),
      buildCasePayload(input({ istekKimligi: undefined })),
    ];
    for (const payload of payloads) {
      expect(Object.keys(payload)).not.toContain("tracking_no");
      expect(JSON.stringify(payload)).not.toContain("tracking_no");
    }
  });

  it("yeni kayıtta istek kimliği gövdeye aynen girer; aynı form aynı kimliği üretir", () => {
    const ilk = buildCasePayload(input());
    const tekrar = buildCasePayload(input());

    expect(ilk.istek_kimligi).toBe("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a");
    expect(tekrar.istek_kimligi).toBe(ilk.istek_kimligi);
  });

  it("düzenlemede (kimlik verilmez) alan gövdeye hiç girmez", () => {
    const payload = buildCasePayload(input({ istekKimligi: undefined }));

    expect(payload).not.toHaveProperty("istek_kimligi");
  });
});
