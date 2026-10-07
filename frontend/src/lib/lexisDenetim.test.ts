// Kararlardan yazılan taslağın denetimi: maddenin dayanak alıntısı taslağın yazıldığı KARARLARDA da aranır; karardan
// yazılan özet paragrafı kendi kararına karşı denetlenir (alıntı + tutar / tarih / numara). Veriler uydurmadır.
import { describe, expect, it } from "vitest";
import { denetle, kararKaynakMetni } from "./lexisDenetim";
import { ORNEK_DOSYALAR, ORNEK_KARARLAR } from "./lexisOrnekVeri";
import type { LexisTaslak, OzetParagraf } from "@/types/lexis";

const KARAR = ORNEK_KARARLAR.find((k) => k.id === 7001)!;
const DOSYA = { ...ORNEK_DOSYALAR[9004], rapor_turu: "EK" as const, iskelet: "EK" as const };
const ALINTI = "omuz takılmasının doğumun öngörülemeyen bir komplikasyonu olduğu";

function taslak(ekInceleme: OzetParagraf[], dayanak: string | null = ALINTI): LexisTaslak {
  return {
    case_id: 9004,
    sirket: "AXA",
    rapor_turu: "EK",
    iskelet: "EK",
    etiketli: {},
    ozet: { ek_inceleme: ekInceleme },
    degerlendirme: {
      giris: "Dosyada mevcut belgeler göz önüne alınarak;",
      maddeler: [
        { metin: "Adli Tıp Kurumu raporunda gelişen durumun komplikasyon olduğunun bildirildiği,", tur: "TESPIT", dayanak_bolum: "yargi_sureci", dayanak_alinti: dayanak },
        { metin: "[…] tazminat tutarında muallak ayrılabileceği", tur: "KALIP", dayanak_bolum: null, dayanak_alinti: null },
      ],
      sulh_uygunluk: "",
      muallak_gerekcesi: "",
    },
    muallak: null,
    muallak_maddi: null,
    muallak_manevi: null,
    emsaller: [],
    kararlar: [7001],
  };
}

const paragraf = (metin: string, dayanak_alinti: string | null = "DAVANIN REDDİNE, 30.000,00 TL vekâlet ücretinin"): OzetParagraf => ({
  metin,
  kaynak_belge_id: null,
  kaynak_karar_id: 7001,
  dayanak_alinti,
});

const kodlar = (t: LexisTaslak, kaynakMetinleri?: Record<number, string>) =>
  denetle({ taslak: t, dosya: DOSYA, emsalMetinleri: [], kararBankasi: [], kaynakMetinleri }).map((u) => u.kod);

describe("kararlardan yazılan taslağın denetimi", () => {
  const temiz = taslak([paragraf("Adana 1. İdare Mahkemesi’nin 12.03.2025 tarihli, 2023/404 E., 2025/118 K. sayılı kararı ile davanın reddine karar verilmiştir.")]);

  it("maddenin alıntısı kararın metninde bulunur; karar metni yokken aynı madde 'alıntı bulunamadı' alır", () => {
    expect(kodlar(temiz, { 7001: kararKaynakMetni(KARAR) })).not.toContain("ALINTI_BULUNAMADI");
    expect(kodlar(temiz)).toContain("ALINTI_BULUNAMADI"); // karar metni verilmedi: dosya metninde yok
    expect(kodlar(taslak([], "kararda hiç geçmeyen uydurma bir dayanak cümlesi"), { 7001: kararKaynakMetni(KARAR) })).toContain("ALINTI_BULUNAMADI");
  });

  it("maddedeki esas / karar atfı dosyanın kendi kararındaysa doğrulanır", () => {
    const atifli = taslak([]);
    atifli.degerlendirme!.maddeler[0].metin = "Adana 1. İdare Mahkemesi’nin 2023/404 E., 2025/118 K. sayılı kararıyla davanın reddedildiği,";
    expect(kodlar(atifli, { 7001: kararKaynakMetni(KARAR) })).not.toContain("ATIF_DOGRULANAMADI");
    expect(kodlar(atifli)).toContain("ATIF_DOGRULANAMADI");
  });

  it("özet paragrafı kendi kararına karşı denetlenir: alıntı, tutar, tarih, numara", () => {
    const uyarilar = (p: OzetParagraf) => denetle({ taslak: taslak([p]), dosya: DOSYA, emsalMetinleri: [], kararBankasi: [], kaynakMetinleri: { 7001: kararKaynakMetni(KARAR) } }).filter((u) => u.bolum === "ek_inceleme");
    expect(uyarilar(temiz.ozet.ek_inceleme![0])).toEqual([]);
    expect(uyarilar(paragraf("Dava reddedilmiştir.", null)).map((u) => u.kod)).toEqual(["DAYANAKSIZ"]);
    expect(uyarilar(paragraf("Dava reddedilmiştir.", "kısa")).map((u) => u.kod)).toEqual(["ALINTI_KISA"]);
    expect(uyarilar(paragraf("Dava reddedilmiştir.", "kararda hiç geçmeyen uydurma bir alıntı")).map((u) => [u.kod, u.seviye])).toEqual([["ALINTI_BULUNAMADI", "HATA"]]);
    const olgu = uyarilar(paragraf("Mahkeme 13.03.2025 tarihinde 750.000,00 TL tazminata hükmetmiştir."));
    expect(olgu.map((u) => u.kod)).toEqual(["OLGU_KAYNAKTA_YOK", "OLGU_KAYNAKTA_YOK"]);
    expect(olgu.map((u) => u.metin)).toEqual(["Ek İnceleme, paragraf 1: kaynak kararda geçmiyor: 750.000,00", "Ek İnceleme, paragraf 1: kaynak kararda geçmiyor: 13.03.2025"]);
  });

  it("metni alınamayan kararın paragrafı denetlenmez (yanlış alarm yok); elle yazılan paragraf da", () => {
    const p = paragraf("Mahkeme 750.000,00 TL tazminata hükmetmiştir.", "uydurma alıntı metni burada");
    const bolum = (kaynak?: Record<number, string>, par = p) =>
      denetle({ taslak: taslak([par]), dosya: DOSYA, emsalMetinleri: [], kararBankasi: [], kaynakMetinleri: kaynak }).filter((u) => u.bolum === "ek_inceleme");
    expect(bolum()).toEqual([]);
    expect(bolum({ 7001: kararKaynakMetni(KARAR) }, { metin: "Elle yazılan 750.000,00 TL.", kaynak_belge_id: null })).toEqual([]);
  });
});
