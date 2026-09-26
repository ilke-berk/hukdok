/**
 * Sohbet kutularına mikrofon (G217): bas → konuş → tekrar bas → "yazıya çevriliyor…" → metin kutuya düşer.
 *
 * Durum makinesi: `bosta → izin_isteniyor → kayitta → cevriliyor → bosta` (başarısızlıkta `hata`; `hata`dan
 * yeniden `baslat` edilebilir). Kayıt `getUserMedia({audio:true})` + `MediaRecorder`; tür
 * `MediaRecorder.isTypeSupported` ile webm/opus → ogg → mp4 sırasıyla seçilir (hiçbiri yoksa tarayıcı
 * varsayılanı). `AZAMI_KAYIT_SN` (60 sn) dolunca kayıt kendiliğinden durur ve çevrilir.
 *
 * Metin OTOMATİK GÖNDERİLMEZ: `onMetin` yalnız kutuya ekleme içindir (hukuki terim/isim hatası riski —
 * kullanıcı okuyup düzeltir, kendisi gönderir). `onMetin` her başarılı çeviride trim'li metinle çağrılır —
 * konuşma yoksa `""` ile (çağıran odağı kutuya döndürür) ve `uyari` "Ses anlaşılamadı" olur.
 *
 * Temizlik: iptal ve bileşen kalkışı tüm `MediaStreamTrack`'leri `stop()` eder (mikrofon ışığı söner),
 * zamanlayıcıları siler ve bekleyen çeviri isteğini abort eder.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { sesiYaziyaCevir } from "@/lib/transcribe";

export type SesDurumu = "bosta" | "izin_isteniyor" | "kayitta" | "cevriliyor" | "hata";

export const AZAMI_KAYIT_SN = 60;
export const IZIN_REDDI_MESAJI = "Mikrofon izni verilmedi";
export const SES_ANLASILAMADI_MESAJI = "Ses anlaşılamadı";

/** Tercih sırası (kabul kriteri): webm/opus → ogg → mp4. */
export const KAYIT_TURLERI = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
] as const;

/** Tarayıcı ses kaydını destekliyor mu (`navigator.mediaDevices.getUserMedia` + `MediaRecorder`). */
export function sesDestekleniyor(): boolean {
    return (
        typeof navigator !== "undefined" &&
        typeof navigator.mediaDevices?.getUserMedia === "function" &&
        typeof globalThis.MediaRecorder === "function"
    );
}

/** Desteklenen ilk kayıt türü; hiçbiri yoksa (ya da `isTypeSupported` yoksa) "" — tarayıcı seçer. */
export function kayitTuruSec(): string {
    const mr = globalThis.MediaRecorder as typeof MediaRecorder | undefined;
    if (typeof mr?.isTypeSupported !== "function") return "";
    return KAYIT_TURLERI.find(t => mr.isTypeSupported(t)) ?? "";
}

/** Yeni metni mevcut metnin SONUNA ekler (arada tek boşluk); boş yeni metin mevcut metni değiştirmez. */
export function metneEkle(mevcut: string, yeni: string): string {
    const y = yeni.trim();
    if (!y) return mevcut;
    if (mevcut.trim() === "") return y;
    return /\s$/.test(mevcut) ? mevcut + y : `${mevcut} ${y}`;
}

/** `0:12` biçimi. */
export function sureEtiketi(sn: number): string {
    const s = Math.max(0, Math.floor(sn));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function izinReddiMi(err: unknown): boolean {
    const ad = (err as { name?: string } | null)?.name;
    return ad === "NotAllowedError" || ad === "SecurityError" || ad === "PermissionDeniedError";
}

function abortMu(err: unknown): boolean {
    return (err as { name?: string } | null)?.name === "AbortError";
}

export type VoiceInput = {
    destekleniyor: boolean;
    durum: SesDurumu;
    /** Kayıtta geçen süre (saniye). */
    gecenSn: number;
    /** Kutunun altında gösterilecek uyarı/bilgi (izin reddi, sunucu hatası, "Ses anlaşılamadı"); yoksa null. */
    uyari: string | null;
    baslat: () => Promise<void>;
    /** Kaydı durdurur ve çeviriyi başlatır. */
    durdur: () => void;
    /** Kaydı/çeviriyi çöpe atar: track'ler durur, istek abort edilir, durum `bosta`. */
    iptal: () => void;
};

type Secenekler = {
    /** Başarılı çeviri (trim'li; konuşma yoksa ""). Gönderim TETİKLENMEZ — yalnız kutuya ekleme. */
    onMetin: (metin: string) => void;
};

export function useVoiceInput({ onMetin }: Secenekler): VoiceInput {
    const [destekleniyor] = useState(sesDestekleniyor);
    const [durum, setDurum] = useState<SesDurumu>("bosta");
    const [gecenSn, setGecenSn] = useState(0);
    const [uyari, setUyari] = useState<string | null>(null);

    const onMetinRef = useRef(onMetin);
    useEffect(() => {
        onMetinRef.current = onMetin;
    }, [onMetin]);

    const durumRef = useRef<SesDurumu>("bosta");
    const streamRef = useRef<MediaStream | null>(null);
    const recorderRef = useRef<MediaRecorder | null>(null);
    const sayacRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const iptalRef = useRef<AbortController | null>(null);
    /** Her başlat/iptal/unmount'ta artar — eski oturumun geç gelen olayları yok sayılır. */
    const oturumRef = useRef(0);
    const bagliRef = useRef(true);

    const durumYaz = useCallback((d: SesDurumu) => {
        durumRef.current = d;
        if (bagliRef.current) setDurum(d);
    }, []);

    const sayaciDurdur = useCallback(() => {
        if (sayacRef.current !== null) {
            clearInterval(sayacRef.current);
            sayacRef.current = null;
        }
    }, []);

    const trackleriDurdur = useCallback(() => {
        streamRef.current?.getTracks().forEach(t => t.stop());
        streamRef.current = null;
    }, []);

    /** Kayıt, sayaç, track ve istek — hepsini bırakır; oturumu geçersizler. */
    const hepsiniBirak = useCallback(() => {
        oturumRef.current += 1;
        sayaciDurdur();
        const rec = recorderRef.current;
        recorderRef.current = null;
        if (rec && rec.state !== "inactive") {
            try {
                rec.stop();
            } catch {
                /* zaten durmuş */
            }
        }
        trackleriDurdur();
        iptalRef.current?.abort();
        iptalRef.current = null;
    }, [sayaciDurdur, trackleriDurdur]);

    useEffect(() => {
        bagliRef.current = true;
        return () => {
            bagliRef.current = false;
            hepsiniBirak();
        };
    }, [hepsiniBirak]);

    const cevir = useCallback(async (blob: Blob, oturum: number) => {
        if (blob.size === 0) {
            if (bagliRef.current) setUyari(SES_ANLASILAMADI_MESAJI);
            durumYaz("bosta");
            return;
        }
        durumYaz("cevriliyor");
        const ctrl = new AbortController();
        iptalRef.current = ctrl;
        try {
            const metin = await sesiYaziyaCevir(blob, ctrl.signal);
            if (oturum !== oturumRef.current || ctrl.signal.aborted) return;
            iptalRef.current = null;
            if (bagliRef.current) setUyari(metin ? null : SES_ANLASILAMADI_MESAJI);
            durumYaz("bosta");
            onMetinRef.current(metin);
        } catch (err) {
            if (oturum !== oturumRef.current || ctrl.signal.aborted || abortMu(err)) return;
            iptalRef.current = null;
            if (bagliRef.current) setUyari(err instanceof Error && err.message ? err.message : "Ses yazıya çevrilemedi.");
            durumYaz("hata");
        }
    }, [durumYaz]);

    const durdur = useCallback(() => {
        const rec = recorderRef.current;
        if (durumRef.current !== "kayitta" || !rec) return;
        sayaciDurdur();
        if (rec.state !== "inactive") rec.stop();
    }, [sayaciDurdur]);

    const baslat = useCallback(async () => {
        if (!destekleniyor) return;
        const d = durumRef.current;
        if (d === "izin_isteniyor" || d === "kayitta" || d === "cevriliyor") return;
        hepsiniBirak();
        const oturum = oturumRef.current;
        setUyari(null);
        setGecenSn(0);
        durumYaz("izin_isteniyor");

        let stream: MediaStream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            if (oturum !== oturumRef.current) return;
            if (bagliRef.current) setUyari(izinReddiMi(err) ? IZIN_REDDI_MESAJI : "Mikrofon açılamadı.");
            durumYaz("hata");
            return;
        }
        // İzin beklenirken iptal/unmount: gelen akışı hemen kapat (mikrofon ışığı yanık kalmasın).
        if (oturum !== oturumRef.current || !bagliRef.current) {
            stream.getTracks().forEach(t => t.stop());
            return;
        }
        streamRef.current = stream;

        const tur = kayitTuruSec();
        let rec: MediaRecorder;
        try {
            rec = tur ? new MediaRecorder(stream, { mimeType: tur }) : new MediaRecorder(stream);
        } catch {
            trackleriDurdur();
            setUyari("Ses kaydı başlatılamadı.");
            durumYaz("hata");
            return;
        }
        recorderRef.current = rec;
        const parcalar: Blob[] = [];
        rec.ondataavailable = (e: BlobEvent) => {
            if (e.data && e.data.size > 0) parcalar.push(e.data);
        };
        rec.onstop = () => {
            // İptal/unmount'ta oturum değişmiştir — parçalar çöpe.
            if (oturum !== oturumRef.current) return;
            recorderRef.current = null;
            sayaciDurdur();
            trackleriDurdur();
            const blobTuru = rec.mimeType || tur || parcalar[0]?.type || "";
            void cevir(new Blob(parcalar, blobTuru ? { type: blobTuru } : undefined), oturum);
        };
        rec.start();
        durumYaz("kayitta");

        let sn = 0;
        sayacRef.current = setInterval(() => {
            sn += 1;
            if (bagliRef.current) setGecenSn(sn);
            if (sn >= AZAMI_KAYIT_SN) durdur();
        }, 1000);
    }, [destekleniyor, hepsiniBirak, durumYaz, trackleriDurdur, sayaciDurdur, cevir, durdur]);

    const iptal = useCallback(() => {
        hepsiniBirak();
        setGecenSn(0);
        durumYaz("bosta");
    }, [hepsiniBirak, durumYaz]);

    return { destekleniyor, durum, gecenSn, uyari, baslat, durdur, iptal };
}
