/**
 * Kart alanı için hata bildirimi (02.10.2026; backend sözleşmesi `routes/hata_bildirimleri.py`).
 *
 * - `GET  /api/hata-bildirimleri?case_id|client_id&durum=acik|hepsi` → 200 `HataBildirimi[]` (en yeni üstte);
 *   hedefsiz çağrı = görünür tüm bildirimler (idari pano)
 * - `GET  /api/hata-bildirimleri/alicilar`                           → 200 `HataAliciAdayi[]` (alıcı seçicisi)
 * - `POST /api/hata-bildirimleri`                                    → 201 tek bildirim; doğru değer ya da
 *   açıklamadan en az biri zorunlu, `alicilar` aday listesinden olmalı, aksi 422
 * - `POST /api/hata-bildirimleri/{id}/kapat` `{sonuc, kapatma_notu}` → 200; zaten kapalı 409
 *
 * Tüm çağrılar `apiClient` üzerinden gider; başarısız yanıt Türkçe mesajlı `HataBildirimiError`
 * fırlatır (çağıran toast'lar / panelde gösterir).
 */
import { apiClient } from "@/lib/api";

export type HataDurumu = "ACIK" | "COZULDU" | "REDDEDILDI";
export type HataKapanisSonucu = Exclude<HataDurumu, "ACIK">;

export interface HataAlicisi {
    email: string;
    ad: string;
}

export type AliciGrubu = "IDARI" | "AVUKAT" | "YONETICI";

/** Alıcı seçicisinin satırı: idari personel + iç avukatlar + yönetici (istek sahibi hariç). */
export interface HataAliciAdayi extends HataAlicisi {
    grup: AliciGrubu;
    /** Yönetim panelinde "Hata bildirimi" işaretli — pencerede ön-seçili gelir. */
    varsayilan: boolean;
}

/** Pencerede grupların sırası ve başlıkları. */
export const ALICI_GRUPLARI: { grup: AliciGrubu; baslik: string }[] = [
    { grup: "IDARI", baslik: "İdari personel" },
    { grup: "AVUKAT", baslik: "Avukatlar" },
    { grup: "YONETICI", baslik: "Yönetici" },
];

export interface HataBildirimi {
    id: number;
    case_id: number | null;
    client_id: number | null;
    /** Dava künyesi (ofis no · esas no) ya da müvekkil adı. */
    hedef_etiketi: string | null;
    /** Uygulama içi yol — bildirim ve pano satırı buraya gider. */
    link: string;
    alan: string;
    alan_etiketi: string;
    mevcut_deger: string | null;
    dogru_deger: string | null;
    aciklama: string | null;
    durum: HataDurumu;
    /** Bildirimin gönderildiği kişiler (gönderim anındaki adlarıyla). */
    alicilar: HataAlicisi[];
    bildiren_ad: string | null;
    bildiren_email: string;
    /** ISO 8601, UTC. */
    created_at: string;
    kapatan_ad: string | null;
    kapatan_email: string | null;
    kapatma_notu: string | null;
    kapatildi_at: string | null;
}

/** Bildirimin hedefi: dava kartı ya da müvekkil kartı (yalnız biri). */
export type HataHedefi = { caseId: number; clientId?: undefined } | { clientId: number; caseId?: undefined };

export interface HataBildirimiTaslak {
    alan: string;
    alanEtiketi: string;
    mevcutDeger?: string | null;
    dogruDeger?: string;
    aciklama?: string;
    /** Seçilen alıcıların e-postaları; verilmezse sunucu varsayılan alıcılara yollar. */
    alicilar?: string[];
    /**
     * true: bildirim GÖNDERİLMEZ — `dogruDeger` karta doğrudan yazılır (yalnız dava kartı,
     * `dogrudanAlanlariGetir`in döndürdüğü alanlar; sunucu yetkiyi ve ekranın bayat olmadığını
     * yeniden denetler). Kayıt "düzeltildi" olarak kapalı doğar.
     */
    dogrudanDuzelt?: boolean;
}

/** Sunucu sınırlarıyla aynı (trim sonrası). */
export const HATA_DEGER_AZAMI = 1000;
export const HATA_ACIKLAMA_AZAMI = 2000;
/** Doğrudan düzeltmede karta yazılacak değerin tavanı (sunucuyla aynı). */
export const HATA_DOGRUDAN_DEGER_AZAMI = 200;

/** Karta özgü olmayan, alan seçilmeden yapılan bildirimin anahtarı. */
export const GENEL_ALAN = "genel";

export class HataBildirimiError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "HataBildirimiError";
        this.status = status;
    }
}

/** Gönder düğmesi: doğru değer ya da açıklamadan en az biri dolu, ikisi de sınırın içinde. */
export function taslakGecerliMi(dogruDeger: string, aciklama: string): boolean {
    const d = dogruDeger.trim();
    const a = aciklama.trim();
    if (!d && !a) return false;
    return d.length <= HATA_DEGER_AZAMI && a.length <= HATA_ACIKLAMA_AZAMI;
}

/** Bildiren/kapatan adı; yoksa (null/boş) e-posta. */
export function kisiEtiketi(ad: string | null | undefined, email: string | null | undefined): string {
    const temiz = ad?.trim();
    return temiz ? temiz : (email ?? "");
}

/**
 * Zilin bildirime tıklanınca gideceği yol. Yalnız uygulama içi mutlak yol kabul edilir
 * ("/cases/12?hata=5"); protokol-göreli ("//evil") ya da tam URL reddedilir → null.
 */
export function guvenliIcYol(link: string | null | undefined): string | null {
    if (!link || !link.startsWith("/") || link.startsWith("//") || link.includes("\\")) return null;
    return link;
}

/** "Nurten Meral, İlke" — şerit ve pano satırındaki "Kime" metni. */
export function alicilarMetni(alicilar: HataAlicisi[] | null | undefined): string {
    return (alicilar ?? []).map(a => a.ad?.trim() || a.email).join(", ");
}

/**
 * Son seçilen alıcılar bu tarayıcıda hatırlanır: avukat çoğunlukla aynı kişiye bildirir, her
 * seferinde yeniden işaretlemesin. Depo erişilemezse (gizli sekme, kota) sessizce yok sayılır.
 */
export const SON_ALICILAR_ANAHTARI = "hukdok:hata-bildirimi-alicilari";

export function sonAlicilariOku(): string[] {
    try {
        const ham: unknown = JSON.parse(window.localStorage.getItem(SON_ALICILAR_ANAHTARI) ?? "[]");
        return Array.isArray(ham) ? ham.filter((e): e is string => typeof e === "string") : [];
    } catch {
        return [];
    }
}

export function sonAlicilariYaz(emails: string[]): void {
    try {
        window.localStorage.setItem(SON_ALICILAR_ANAHTARI, JSON.stringify(emails));
    } catch {
        // hatırlama kolaylıktır; yazılamaması gönderimi etkilemez
    }
}

/**
 * Pencere açılışındaki ön-seçim: son seçimden HÂLÂ aday olanlar; hiçbiri kalmadıysa (ilk kullanım,
 * kişi listeden çıktı) yönetim panelinde işaretli varsayılan alıcılar.
 */
export function onSecim(adaylar: HataAliciAdayi[], sonSecim: string[]): string[] {
    const hatirlanan = adaylar.filter(a => sonSecim.includes(a.email)).map(a => a.email);
    return hatirlanan.length > 0 ? hatirlanan : adaylar.filter(a => a.varsayilan).map(a => a.email);
}

const KOK = "/api/hata-bildirimleri";

export async function alicilariGetir(): Promise<HataAliciAdayi[]> {
    const res = await apiClient.fetch(`${KOK}/alicilar`);
    if (!res.ok) throw new HataBildirimiError("Alıcı listesi alınamadı.", res.status);
    const data: unknown = await res.json();
    if (!Array.isArray(data)) throw new HataBildirimiError("Alıcı listesi alınamadı.", res.status);
    return data as HataAliciAdayi[];
}

export async function listele(hedef?: HataHedefi, durum: "acik" | "hepsi" = "acik"): Promise<HataBildirimi[]> {
    const q = new URLSearchParams();
    if (hedef?.caseId != null) q.set("case_id", String(hedef.caseId));
    if (hedef?.clientId != null) q.set("client_id", String(hedef.clientId));
    if (durum !== "acik") q.set("durum", durum);
    const sorgu = q.toString();
    const res = await apiClient.fetch(sorgu ? `${KOK}?${sorgu}` : KOK);
    if (!res.ok) throw new HataBildirimiError("Hata bildirimleri yüklenemedi.", res.status);
    const data: unknown = await res.json();
    // Beklenmedik gövde de hatadır — boş listeye ÇEVRİLMEZ (G002 dersi).
    if (!Array.isArray(data)) throw new HataBildirimiError("Hata bildirimleri yüklenemedi.", res.status);
    return data as HataBildirimi[];
}

export async function olustur(hedef: HataHedefi, taslak: HataBildirimiTaslak): Promise<HataBildirimi> {
    const res = await apiClient.fetch(KOK, {
        method: "POST",
        body: JSON.stringify({
            case_id: hedef.caseId ?? null,
            client_id: hedef.clientId ?? null,
            alan: taslak.alan,
            alan_etiketi: taslak.alanEtiketi,
            mevcut_deger: taslak.mevcutDeger ?? null,
            dogru_deger: taslak.dogruDeger?.trim() || null,
            aciklama: taslak.aciklama?.trim() || null,
            alicilar: taslak.alicilar && taslak.alicilar.length > 0 ? taslak.alicilar : null,
            dogrudan_duzelt: taslak.dogrudanDuzelt === true,
        }),
    });
    if (!res.ok) {
        // Doğrudan düzeltmenin retleri (yetki 403, bayat ekran 409, aynı değer 422) sunucunun
        // Türkçe `detail` metniyle gelir — kullanıcıya neyin olduğunu o söyler.
        const detay = taslak.dogrudanDuzelt ? await sunucuDetayi(res) : null;
        const mesaj =
            detay ? detay
            : taslak.dogrudanDuzelt ? "Düzeltme uygulanamadı."
            : res.status === 422 ? "Gönderilemedi: doğru değer ya da açıklama yazılmalı ve listeden en az bir alıcı seçilmeli."
            : res.status === 404 ? "Kayıt bulunamadı; silinmiş olabilir."
            : "Hata bildirimi gönderilemedi.";
        throw new HataBildirimiError(mesaj, res.status);
    }
    return (await res.json()) as HataBildirimi;
}

/** Hata yanıtının düz metin `detail`i (FastAPI); doğrulama listesi ya da bozuk gövde → null. */
async function sunucuDetayi(res: Response): Promise<string | null> {
    try {
        const govde: unknown = await res.json();
        const detay = (govde as { detail?: unknown } | null)?.detail;
        return typeof detay === "string" && detay.trim() ? detay : null;
    } catch {
        return null;
    }
}

/**
 * İstek sahibinin bu davada bildirim göndermeden KENDİSİ düzeltebileceği alan anahtarları
 * (davanın sorumlu avukatı ya da yönetici değilse boş). Alınamazsa boş: doğrudan düzeltme
 * kolaylıktır, yokluğunda bildirim yolu aynen çalışır.
 */
export async function dogrudanAlanlariGetir(caseId: number): Promise<string[]> {
    try {
        const res = await apiClient.fetch(`${KOK}/dogrudan?case_id=${encodeURIComponent(String(caseId))}`);
        if (!res.ok) return [];
        const alanlar = ((await res.json()) as { alanlar?: unknown } | null)?.alanlar;
        return Array.isArray(alanlar) ? alanlar.filter((a): a is string => typeof a === "string") : [];
    } catch {
        return [];
    }
}

export async function kapat(id: number, sonuc: HataKapanisSonucu, kapatmaNotu?: string): Promise<HataBildirimi> {
    const res = await apiClient.fetch(`${KOK}/${encodeURIComponent(String(id))}/kapat`, {
        method: "POST",
        body: JSON.stringify({ sonuc, kapatma_notu: kapatmaNotu?.trim() || null }),
    });
    if (!res.ok) {
        const mesaj =
            res.status === 409 ? "Bu hata bildirimi zaten kapatılmış."
            : res.status === 404 ? "Hata bildirimi bulunamadı."
            : "Hata bildirimi kapatılamadı.";
        throw new HataBildirimiError(mesaj, res.status);
    }
    return (await res.json()) as HataBildirimi;
}
