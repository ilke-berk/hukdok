import { createDraftStore } from "@/lib/formDraft";
import type { RaporTanimi } from "@/lib/reports";
import type { SohbetKaydi } from "@/lib/reportsChat";

// =====================================================================
// Rapor çalışması (28.09): /reports'tan başka sayfaya geçip dönünce sohbet ve
// rapor tanımı KAYBOLMASIN. Eskiden ikisi de bileşen state'indeydi; sayfa
// değişiminde bileşen söküldüğü için yanlışlıkla bütün çalışma gidiyordu.
//
// Genel taslak motoru (`formDraft.ts`) üzerine kurulu → sessionStorage:
// sayfa değişimi ve yenilemede yaşar, SEKME KAPANINCA ölür; çıkışta
// `clearAppStorage()` `hukdok.` önekiyle siler (önceki kullanıcıya sızmaz).
// Kullanıcı çalışmayı kendisi bitirir: sohbette "Sohbeti temizle", şeritte "Temizle".
//
// NE SAKLANIR: son geçerli rapor TANIMI (şerit katalog gelince `tanimdanDurum`
// ile yeniden kurulur — şerit öğe kimlikleri modül sayacından üretildiği için
// ham durum saklanmaz), seçili şablon, örnek boyu; sohbet kayıtları, yazılmakta
// olan girdi, konuşma alanının açıklığı, bekleyen (onay bekleyen) tanım.
//
// NE SAKLANMAZ: önizleme SATIRLARI (dönüşte taze çekilir; müvekkil verisi
// depoya gereksiz yere yazılmaz), "Geri al" adımı (tek adımlık, sayfa ömrü),
// süren asistan isteği (sayfadan çıkınca iptal edilir; sohbete not düşülür).
// =====================================================================

/** Bir çalışma günü: dünkü rapor sohbeti bugün diriltilmez. */
export const RAPOR_CALISMASI_MAX_AGE_MS = 10 * 60 * 60 * 1000; // 10 saat

export interface RaporSayfaCalismasi {
    tanim: RaporTanimi;
    seciliSablonId: number | null;
    ornekBoyu: number;
}

export interface RaporSohbetCalismasi {
    kayitlar: SohbetKaydi[];
    girdi: string;
    acik: boolean;
    sonUygulananId: number | null;
    bekleyenTanim: RaporTanimi | null;
}

export const raporSayfaCalismasi = createDraftStore<RaporSayfaCalismasi>({
    key: "hukdok.rapor-calismasi.sayfa.v1",
    version: 1,
    maxAgeMs: RAPOR_CALISMASI_MAX_AGE_MS,
    isValid: (v) => {
        const d = v as RaporSayfaCalismasi | null;
        return Boolean(d && d.tanim && typeof d.tanim.veri_kaynagi === "string" && Array.isArray(d.tanim.kolonlar)
            && typeof d.ornekBoyu === "number");
    },
});

export const raporSohbetCalismasi = createDraftStore<RaporSohbetCalismasi>({
    key: "hukdok.rapor-calismasi.sohbet.v1",
    version: 1,
    maxAgeMs: RAPOR_CALISMASI_MAX_AGE_MS,
    isValid: (v) => {
        const d = v as RaporSohbetCalismasi | null;
        return Boolean(d && Array.isArray(d.kayitlar) && typeof d.girdi === "string"
            && d.kayitlar.every(k => typeof k?.id === "number" && (k.rol === "user" || k.rol === "assistant")));
    },
});

/** Sayfadan çıkarken yanıtı beklenen istek iptal edildi — dönüşte sohbette görünen not. */
export const YARIM_ISTEK_NOTU = "Sayfadan ayrıldığınız için bu isteğin yanıtı alınamadı; tekrar gönderebilirsiniz.";
