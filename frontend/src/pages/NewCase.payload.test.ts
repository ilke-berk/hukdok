// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { EMPTY_NEW_CASE_FORM, type NewCaseFormValues } from "@/lib/newCaseDraft";
import { buildCasePayload, editModeFormValues, type CasePayloadInput } from "./NewCase";

// =====================================================================
// G020 — `service_type` kayıt yüküne giriyor mu?
//
// Canlı DB ölçümü (2026-08-11): `SELECT count(*), count(service_type) FROM cases`
// → 14.345 / 0. Kullanıcı hizmet türünü seçiyordu, zorunlu-alan denetimi onu
// görüyordu, ama POST/PUT gövdesine hiç konmuyordu; iki `as CaseData` cast'i
// derleyicinin uyarısını susturuyordu. Bu testler yükü doğrudan doğrular.
// =====================================================================

const form = (over: Partial<NewCaseFormValues> = {}): NewCaseFormValues => ({
  ...EMPTY_NEW_CASE_FORM,
  ...over,
});

const input = (over: Partial<CasePayloadInput> = {}): CasePayloadInput => ({
  trackingNo: "2026.00001.HUK.01.00100",
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
  it("seçilen hizmet türünü kayıt yüküne koyar", () => {
    const payload = buildCasePayload(input({ formData: form({ serviceType: "00110" }) }));

    expect(payload.service_type).toBe("00110");
  });

  it("hiç seçim yapılmasa da alanı boş bırakmaz (backend 'eksik zorunlu alan' saymasın)", () => {
    // required_fields.py `_is_empty` boş/None'ı eksik sayar; "00000" (hiç kutu
    // işaretlenmedi) dolu kabul edilir — frontend'in getMissingRequired'ı ile aynı kural.
    const payload = buildCasePayload(input());

    expect(payload.service_type).toBe("00000");
    expect((payload.service_type ?? "").trim()).not.toBe("");
  });

  it("düzenleme modunda mevcut değer kaydetmede kaybolmaz", () => {
    // Düzenleme yolu: kayıt → forma yüklenir → forma dokunulmadan kaydedilir.
    const loaded = editModeFormValues({
      tracking_no: "2026.00001.HUK.01.00100",
      status: "DERDEST",
      service_type: "01001",
    });
    expect(loaded.serviceType).toBe("01001");

    const payload = buildCasePayload(input({ formData: loaded }));
    expect(payload.service_type).toBe("01001");
  });

  it("düzenlenen kayıtta hizmet türü boşsa varsayılana düşer", () => {
    const loaded = editModeFormValues({ tracking_no: "X", status: "DERDEST" });

    expect(loaded.serviceType).toBe("00000");
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

    expect(payload).toMatchObject({
      tracking_no: "2026.00001.HUK.01.00100",
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
