// Lexis örnek adaptörü (`/lexis` önizlemesi) — sözleşmenin davranışı: akış olaylarının sırası ve SON olayı,
// denetimin dayanak kuralı (K13) uyarıları, emsal sıralaması, kart seçimi (K8) ve Word'ün gerçek servise devri.
import { beforeEach, describe, expect, it, vi } from "vitest";

// Word çağrısı ağa çıkar (`lexisWord.ts` → `apiClient`); burada yalnız adaptörün devri sınanır.
const wordMock = vi.hoisted(() => ({ wordIndir: vi.fn() }));
vi.mock("@/lib/lexisWord", () => wordMock);

import { LexisApiError, lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla } from "./lexisApi";
import { ORNEK_DOSYALAR, ORNEK_GECMIS, ornekSha } from "./lexisOrnekVeri";
import { ISKELET_BOLUMLERI, type LexisAkisOlayi, type LexisTaslak, type TaslakIstegi } from "@/types/lexis";

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
});

async function istekKur(caseId: number): Promise<TaslakIstegi> {
  const dosya = await lexisApi.dosyaGetir(caseId);
  const emsaller = await lexisApi.emsalOner({ case_id: caseId, sirket: dosya.sirket, rapor_turu: dosya.rapor_turu });
  return {
    case_id: caseId,
    sirket: dosya.sirket,
    rapor_turu: dosya.rapor_turu,
    iskelet: dosya.iskelet,
    belge_idleri: dosya.belgeler.map((b) => b.id),
    emsal_sha: emsaller.map((e) => e.kayit.okuma.sha256),
  };
}

async function akisiTopla(istek: TaslakIstegi): Promise<LexisAkisOlayi[]> {
  const olaylar: LexisAkisOlayi[] = [];
  for await (const olay of lexisApi.taslakYaz(istek)) olaylar.push(olay);
  return olaylar;
}

/** Akış olaylarından ekrandaki taslağı kurar (sayfanın yaptığının aynısı). */
function taslakKur(istek: TaslakIstegi, olaylar: LexisAkisOlayi[]): LexisTaslak {
  const taslak: LexisTaslak = {
    case_id: istek.case_id,
    sirket: istek.sirket,
    rapor_turu: istek.rapor_turu,
    iskelet: istek.iskelet,
    etiketli: {},
    ozet: {},
    degerlendirme: null,
    muallak: null,
    muallak_maddi: null,
    muallak_manevi: null,
    emsaller: istek.emsal_sha,
  };
  for (const olay of olaylar) {
    if (olay.status === "bolum") {
      if (olay.etiketli) taslak.etiketli[olay.bolum] = olay.etiketli;
      if (olay.ozet) taslak.ozet[olay.bolum] = olay.ozet;
      if (olay.degerlendirme) taslak.degerlendirme = olay.degerlendirme;
    } else if (olay.status === "muallak") {
      taslak.muallak = olay.oneri;
    }
  }
  return taslak;
}

describe("taslakYaz akışı", () => {
  it("iskeletin her bölümünü sırayla verir, muallaktan sonra complete ile biter", async () => {
    const istek = await istekKur(9001);
    const olaylar = await akisiTopla(istek);

    expect(olaylar.filter((o) => o.status === "bolum").map((o) => (o.status === "bolum" ? o.bolum : ""))).toEqual(
      ISKELET_BOLUMLERI.ANADOLU.map((b) => b.kod),
    );
    expect(olaylar.filter((o) => o.status === "info").map((o) => (o.status === "info" ? o.asama : ""))).toEqual([
      "olgular",
      "emsaller",
      "bolumler",
      "muallak",
      "denetim",
    ]);
    const son = olaylar[olaylar.length - 1];
    expect(son.status).toBe("complete");
    expect(olaylar.findIndex((o) => o.status === "muallak")).toBeLessThan(olaylar.length - 1);
  });

  it("biten koşu geçmişin başına düşer", async () => {
    const once = await lexisApi.gecmis();
    const olaylar = await akisiTopla(await istekKur(9002));
    const sonra = await lexisApi.gecmis();
    const son = olaylar[olaylar.length - 1];
    expect(sonra).toHaveLength(once.length + 1);
    expect(son.status === "complete" && son.kosu_id).toBe(sonra[0].id);
    expect(sonra[0].case_id).toBe(9002);
  });

  it("bilinmeyen davada failed SON olaydır ve error_kod taşır", async () => {
    const olaylar = await akisiTopla({ case_id: 1, sirket: "AXA", rapor_turu: "ANA", iskelet: "KISA", belge_idleri: [], emsal_sha: [] });
    expect(olaylar).toEqual([{ status: "failed", error_ozet: expect.any(String), error_kod: "analysis_error" }]);
  });

  it("iptal edilen akış AbortError fırlatır", async () => {
    ornekGecikmeAyarla(20);
    const ac = new AbortController();
    const akis = lexisApi.taslakYaz(await istekKur(9001), ac.signal);
    await akis.next();
    ac.abort();
    await expect(akis.next()).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("denetim (dayanak kuralı)", () => {
  it("9001: her madde kendi uyarısını alır — emsalden taşınma, dayanaksız + belge yokluğu, bulunamayan alıntı", async () => {
    const istek = await istekKur(9001);
    const olaylar = await akisiTopla(istek);
    const son = olaylar[olaylar.length - 1];
    if (son.status !== "complete") throw new Error("akış tamamlanmadı");
    const maddeKodlari = (n: number) => son.uyarilar.filter((u) => u.madde === n).map((u) => u.kod);

    expect(maddeKodlari(1)).toEqual([]);
    expect(maddeKodlari(2)).toEqual([]);
    expect(maddeKodlari(3)).toEqual(["EMSALDEN_TASINMA"]);
    expect(maddeKodlari(4)).toEqual(["DAYANAKSIZ", "BELGE_YOKLUGU"]);
    expect(maddeKodlari(5)).toEqual(["ALINTI_BULUNAMADI"]);
    expect(maddeKodlari(6)).toEqual([]);

    const kodlar = son.uyarilar.map((u) => u.kod);
    expect(kodlar).toContain("KART_BELGE_CELISKISI");
    expect(son.uyarilar.find((u) => u.kod === "ALAN_BOS")).toMatchObject({ bolum: "hasar", alan: "talep_tarihi" });
    expect(kodlar).not.toContain("EKSIK_BELGE");
  });

  it("9002: poliçe belgesi yok → eksik belge + boş bölüm; maddeler temiz", async () => {
    const olaylar = await akisiTopla(await istekKur(9002));
    const son = olaylar[olaylar.length - 1];
    if (son.status !== "complete") throw new Error("akış tamamlanmadı");
    expect(son.uyarilar.map((u) => u.kod).sort()).toEqual(["BOLUM_BOS", "EKSIK_BELGE"]);
  });

  it("9003: dayanaksız muallak ve doldurulmamış yer uyarılır", async () => {
    const olaylar = await akisiTopla(await istekKur(9003));
    const son = olaylar[olaylar.length - 1];
    if (son.status !== "complete") throw new Error("akış tamamlanmadı");
    const kodlar = son.uyarilar.map((u) => u.kod);
    expect(kodlar).toContain("MUALLAK_DAYANAK_YOK");
    expect(kodlar).toContain("DOLDURULMAMIS");
  });

  it("9004 (ek rapor) temizdir; alıntı düzeltilince uyarı kalkar, tutar talebi aşınca hata düşer", async () => {
    const istek = await istekKur(9004);
    const taslak = taslakKur(istek, await akisiTopla(istek));
    expect(await lexisApi.denetle(taslak)).toEqual([]);

    taslak.degerlendirme!.maddeler[0].dayanak_alinti = "dosyada hiç geçmeyen uzunca bir alıntı";
    expect((await lexisApi.denetle(taslak)).map((u) => u.kod)).toEqual(["ALINTI_BULUNAMADI"]);

    taslak.degerlendirme!.maddeler[0].dayanak_alinti = "uygulanan manevraların doğum kayıtlarına işlendiği";
    taslak.muallak_manevi = ORNEK_DOSYALAR[9004].talep_manevi! + 1;
    expect((await lexisApi.denetle(taslak)).map((u) => u.kod)).toEqual(["MUALLAK_TALEBI_ASIYOR"]);
  });

  it("9004: ek raporun künye satırları kendi bölümünde gelir; giriş kalıbı ek raporda \"Dosyada …\"dır", async () => {
    const istek = await istekKur(9004);
    const taslak = taslakKur(istek, await akisiTopla(istek));
    expect(ISKELET_BOLUMLERI.EK.map((b) => b.kod)).toEqual(["kunye", "ek_inceleme", "degerlendirme"]);
    // Alan kodları çekirdeğin EK düzenindeki künye satırlarıdır: Word'de bu üç satır `[…]` çıkmaz.
    expect(taslak.etiketli.kunye?.map((s) => s.alan)).toEqual(["konu", "sigortali", "police_no"]);

    taslak.degerlendirme!.giris = "Tarafımıza iletilen belgeler kapsamında yapılan inceleme neticesinde;";
    expect((await lexisApi.denetle(taslak)).map((u) => u.kod)).toEqual(["GIRIS_KALIBI"]);
  });
});

describe("emsaller", () => {
  it("puana göre sıralı, gerekçeli gelir; konu bağı olan rapor ilk sıradadır", async () => {
    const emsaller = await lexisApi.emsalOner({ case_id: 9001, sirket: "ANADOLU", rapor_turu: "ANA" });
    expect(emsaller).toHaveLength(3);
    expect(emsaller[0].kayit.okuma.sha256).toBe(ornekSha(1));
    expect(emsaller[0].gerekce).toContain("olay: Yanık");
    expect(emsaller[0].gerekce).toContain("aynı şirket");
    expect(emsaller.map((e) => e.puan)).toEqual([...emsaller.map((e) => e.puan)].sort((a, b) => b - a));
    for (const e of emsaller) {
      const toplam = e.bilesenler.reduce((t, b) => t + b.agirlik * b.benzerlik, 0);
      // Puan tek ondalığa yuvarlanır
      expect(Math.abs(e.puan - toplam)).toBeLessThan(0.06);
    }
  });

  it("dosyanın kendi eski raporu emsal olarak önerilmez", async () => {
    const emsaller = await lexisApi.emsalOner({ case_id: 9004, sirket: "AXA", rapor_turu: "EK", k: 10 });
    expect(emsaller.map((e) => e.kayit.okuma.sha256)).not.toContain(ORNEK_DOSYALAR[9004].onceki_rapor);
  });

  it("kütüphane filtreyle ve metinle aranır; karar bankası kararı geçtiği raporlarla verir", async () => {
    expect((await lexisApi.kutuphaneAra({ sirket: "AK" })).map((k) => k.okuma.sirket)).toEqual(["AK", "AK"]);
    expect((await lexisApi.kutuphaneAra({ metin: "gazlı bez" })).map((k) => k.okuma.sha256)).toEqual([ornekSha(8)]);
    const banka = await lexisApi.kararBankasi();
    expect(banka).toHaveLength(2);
    expect(banka[0].raporlar).toEqual([ornekSha(2)]);
  });
});

describe("kart bağı seçimi", () => {
  it("seçim birincil kartı doldurur, null geri alır; aday olmayan kart reddedilir", async () => {
    const [ilk] = await lexisApi.kartBaglari();
    expect(ilk.bag).toMatchObject({ durum: "COK_ADAY", birincil: null, insan_secimi: false });

    const secilen = await lexisApi.kartSec(ilk.rapor, ilk.bag.adaylar[1].kart.kart_id);
    expect(secilen.bag).toMatchObject({ birincil: ilk.bag.adaylar[1].kart.kart_id, insan_secimi: true });
    expect((await lexisApi.kartBaglari())[0].bag.birincil).toBe(ilk.bag.adaylar[1].kart.kart_id);

    const geriAlinan = await lexisApi.kartSec(ilk.rapor, null);
    expect(geriAlinan.bag).toMatchObject({ birincil: null, insan_secimi: false });

    await expect(lexisApi.kartSec(ilk.rapor, 1)).rejects.toBeInstanceOf(LexisApiError);
  });
});

describe("önizleme sınırı", () => {
  it("Word gerçek servise gider: taslak + dosyanın künyesi; inen koşu geçmişte işaretlenir", async () => {
    const istek = await istekKur(9004);
    const taslak = taslakKur(istek, await akisiTopla(istek));
    const dosya = ORNEK_DOSYALAR[9004];
    const sonuc = { dosya_adi: "Lexis_x_ANA_taslak.docx", uyari_sayisi: 1, uyarilar: ["alan boş: talep_tarihi"] };
    wordMock.wordIndir.mockResolvedValueOnce(sonuc);

    await expect(lexisApi.wordIndir(taslak)).resolves.toEqual(sonuc);

    expect(wordMock.wordIndir).toHaveBeenCalledWith(taslak, { hasar_no: dosya.hasar_no, rapor_no: dosya.dava.dosya_no }, undefined);
    const [sonKosu, ...eskiler] = await lexisApi.gecmis();
    expect(sonKosu.case_id).toBe(9004);
    expect(sonKosu.indirme_tarihi).not.toBeNull();
    // Aynı davanın eski koşularına dokunulmaz.
    expect(eskiler.filter((k) => k.case_id === 9004)).toEqual(ORNEK_GECMIS.filter((k) => k.case_id === 9004));
  });

  it("servis hatasında koşu 'indirildi' sayılmaz", async () => {
    const istek = await istekKur(9004);
    const taslak = taslakKur(istek, await akisiTopla(istek));
    wordMock.wordIndir.mockRejectedValueOnce(new LexisApiError(502, "Lexis servisine ulaşılamadı; Word üretilemedi."));
    await expect(lexisApi.wordIndir(taslak)).rejects.toBeInstanceOf(LexisApiError);
    expect((await lexisApi.gecmis())[0].indirme_tarihi).toBeNull();
  });

  it("profil kaydı listede görünür", async () => {
    const [profil] = await lexisApi.profiller();
    await lexisApi.profilKaydet({ ...profil, kriter_metni: "güncel metin" });
    expect((await lexisApi.profiller())[0].kriter_metni).toBe("güncel metin");
  });
});
