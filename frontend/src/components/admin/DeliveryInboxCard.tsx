// Yönetim paneli "Veri Teslimleri" sekmesi — veri ekibinin teslim defteri.
// Yönetici teslimleri listeler, xlsx yükler, SharePoint taraması tetikler,
// kuru koşu başlatıp raporlarını indirir ve `inceleme_bekliyor`/`kuru_kosuldu`
// teslimi bilinçli onayla uygular. API sözleşmesi G108'de donduruldu
// (gorevler/gorev/G111.md "SÖZLEŞME"); bu kart yalnız o uçlara bağlanır.
// `apiClient.fetch` istisna fırlatmaz — her yanıtta `Response.ok` denetlenir.
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export type TeslimDurum =
    | "alindi"
    | "yinelenen"
    | "reddedildi"
    | "dogrulandi"
    | "kuru_kosuldu"
    | "inceleme_bekliyor"
    | "uygulaniyor"
    | "uygulandi"
    | "basarisiz";

export type KapiKarari = "otomatik" | "inceleme" | null;

export interface Teslim {
    id: number;
    dosya_adi: string;
    sha256: string;
    kaynak: "sharepoint" | "yukleme";
    durum: TeslimDurum;
    onceki_teslim_adi: string | null;
    zincir_tamam: boolean | null;
    okunan: number | null;
    islenen: number | null;
    atlanan: number | null;
    hata_sayisi: number | null;
    alan_degisikligi: number | null;
    kart_degisen: number | null;
    envanter_denk: boolean | null;
    kapi_karari: KapiKarari;
    kapi_gerekcesi: string | null;
    cevap_yuklendi: boolean | null;
    uygulayan: string | null;
    hata_mesaji: string | null;
    created_at: string;
    updated_at: string | null;
    done_at: string | null;
}

export interface Esikler {
    hata_orani: number;
    eslesmeyen_orani: number;
    alan_degisikligi: number;
}

interface RaporDosyasi {
    ad: string;
    boyut: number;
}

const BASE = "/api/admin/aktarim";

const DURUM_ETIKET: Record<TeslimDurum, string> = {
    alindi: "Alındı",
    yinelenen: "Yinelenen",
    reddedildi: "Reddedildi",
    dogrulandi: "Doğrulandı",
    kuru_kosuldu: "Kuru koşuldu",
    inceleme_bekliyor: "İnceleme bekliyor",
    uygulaniyor: "Uygulanıyor",
    uygulandi: "Uygulandı",
    basarisiz: "Başarısız",
};

type Ton = "green" | "amber" | "red" | "neutral";

const DURUM_TON: Record<TeslimDurum, Ton> = {
    alindi: "neutral",
    yinelenen: "neutral",
    reddedildi: "red",
    dogrulandi: "neutral",
    kuru_kosuldu: "neutral",
    inceleme_bekliyor: "amber",
    uygulaniyor: "neutral",
    uygulandi: "green",
    basarisiz: "red",
};

const TON_SINIF: Record<Ton, string> = {
    green: "bg-emerald-100 text-emerald-800 border-emerald-200",
    amber: "bg-amber-100 text-amber-800 border-amber-200",
    red: "bg-red-100 text-red-800 border-red-200",
    neutral: "bg-[var(--bg-elevated)] text-[var(--fg-muted)] border-[var(--border)]",
};

const KAYNAK_ETIKET: Record<Teslim["kaynak"], string> = {
    sharepoint: "SharePoint",
    yukleme: "Yükleme",
};

const KAPI_ETIKET: Record<Exclude<KapiKarari, null>, string> = {
    otomatik: "Otomatik",
    inceleme: "İnceleme",
};

// "Uygula" yalnız kuru koşusu bitmiş teslimde anlamlı; diğer durumlarda buton
// hiç çizilmez (backend 409 basar, ama yöneticiyi oraya götürmeyiz).
const UYGULA_IZINLI: ReadonlySet<TeslimDurum> = new Set(["inceleme_bekliyor", "kuru_kosuldu"]);

// Kuru koşu tekrar edilebilir: doğrulanmış/koşulmuş/incelemede/başarısız teslimde
// serbest. Yinelenen ve reddedilen teslimde girdi yok; uygulanan/uygulanıyor
// teslimde ise koşunun anlamı kalmadı.
const KURU_KOS_IZINLI: ReadonlySet<TeslimDurum> = new Set([
    "alindi",
    "dogrulandi",
    "kuru_kosuldu",
    "inceleme_bekliyor",
    "basarisiz",
]);

// Mesai saati kontrolü Türkiye saatine göre (09:00–18:00). Tarayıcının yerel
// saati hangi dilimde olursa olsun Europe/Istanbul'a çevrilir; Intl dilim
// desteği yoksa yerel saat kullanılır (yaklaşık ama güvenli tarafta).
const mesaiSaatindeMi = (now: Date = new Date()): boolean => {
    let saat: number;
    try {
        const parca = new Intl.DateTimeFormat("en-US", {
            timeZone: "Europe/Istanbul",
            hour: "numeric",
            hourCycle: "h23",
        }).formatToParts(now).find(p => p.type === "hour");
        saat = parca ? Number(parca.value) : now.getHours();
        if (Number.isNaN(saat)) saat = now.getHours();
    } catch {
        saat = now.getHours();
    }
    return saat >= 9 && saat < 18;
};

const sayi = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : String(n));

const tarih = (iso: string | null): string => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("tr-TR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
};

const boyut = (b: number): string => {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB`;
};

// Hata yanıtından sunucu `detail`'ini çıkarır; yoksa verilen yedek metin.
const hataMetni = async (res: Response, yedek: string): Promise<string> => {
    try {
        const data = await res.json();
        if (typeof data?.detail === "string" && data.detail.trim()) return data.detail;
    } catch {
        // gövde JSON değil — yedek metin kullanılır
    }
    return yedek;
};

// apiClient'ın zaman aşımı (`ApiTimeoutError`, ad üzerinden tanınır — sınıfı
// içe almak test mock'unu bağlar). Kuru koşu/uygulama 8.409 satırda 45-60 sn
// sürebilir; istemci kesse de sunucu işi bitirir, liste tazelenince görünür (G117).
const ZAMAN_ASIMI_METNI =
    "İstek zaman aşımına uğradı; işlem sunucuda sürüyor olabilir, listeyi yenileyin.";
const zamanAsimiMi = (e: unknown): boolean => e instanceof Error && e.name === "ApiTimeoutError";

function DurumRozeti({ durum }: { durum: TeslimDurum }) {
    const ton = DURUM_TON[durum] ?? "neutral";
    return (
        <span
            data-tone={ton}
            className={`inline-flex items-center border px-2 py-0.5 text-[11px] font-mono uppercase tracking-[0.06em] whitespace-nowrap ${TON_SINIF[ton]}`}
        >
            {DURUM_ETIKET[durum] ?? durum}
        </span>
    );
}

export function DeliveryInboxCard() {
    const [teslimler, setTeslimler] = useState<Teslim[]>([]);
    const [esikler, setEsikler] = useState<Esikler | null>(null);
    const [etkin, setEtkin] = useState<boolean>(true);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);

    const [isScanning, setIsScanning] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [busyId, setBusyId] = useState<number | null>(null);

    const [raporlar, setRaporlar] = useState<Record<number, RaporDosyasi[]>>({});
    const [acikRaporId, setAcikRaporId] = useState<number | null>(null);
    const [indirilen, setIndirilen] = useState<string | null>(null);

    const [onayTeslim, setOnayTeslim] = useState<Teslim | null>(null);
    const [isApplying, setIsApplying] = useState(false);

    const fileInputRef = useRef<HTMLInputElement>(null);

    const load = useCallback(async () => {
        setIsLoading(true);
        setLoadError(null);
        try {
            const res = await apiClient.fetch(`${BASE}/teslimler?limit=50`);
            if (!res.ok) throw new Error("Teslim listesi alınamadı");
            const data = await res.json();
            setTeslimler(data.teslimler ?? []);
            setEsikler(data.esikler ?? null);
            setEtkin(data.etkin !== false);
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : "Teslim listesi alınamadı");
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const handleTara = async () => {
        setIsScanning(true);
        try {
            const res = await apiClient.fetch(`${BASE}/tara`, { method: "POST" });
            if (!res.ok) throw new Error(await hataMetni(res, "Tarama başlatılamadı"));
            const data = await res.json();
            const ozet = `${data.yeni ?? 0} yeni, ${data.yinelenen ?? 0} yinelenen`;
            toast.success(data.not ? `${ozet} — ${data.not}` : ozet);
            void load();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Tarama başlatılamadı");
        } finally {
            setIsScanning(false);
        }
    };

    const handleUpload = async (file: File) => {
        setIsUploading(true);
        try {
            const formData = new FormData();
            formData.append("file", file);
            const res = await apiClient.fetch(`${BASE}/teslimler`, { method: "POST", body: formData });
            if (!res.ok) {
                throw new Error(
                    res.status === 400
                        ? await hataMetni(res, "Dosya kabul edilmedi")
                        : await hataMetni(res, "Dosya yüklenemedi"),
                );
            }
            const data = await res.json();
            toast.success(`Yüklendi: ${file.name} (${DURUM_ETIKET[data.durum as TeslimDurum] ?? data.durum})`);
            void load();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Dosya yüklenemedi");
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    const handleKuruKos = async (t: Teslim) => {
        setBusyId(t.id);
        try {
            const res = await apiClient.fetch(`${BASE}/teslimler/${t.id}/kuru-kos`, { method: "POST" });
            if (res.status === 409) throw new Error("Bu durumda kuru koşulamaz");
            if (!res.ok) throw new Error(await hataMetni(res, "Kuru koşu başlatılamadı"));
            const data = await res.json();
            const karar = data.kapi_karari ? KAPI_ETIKET[data.kapi_karari as Exclude<KapiKarari, null>] ?? data.kapi_karari : null;
            const gerekce = data.kapi_gerekcesi ? ` — ${data.kapi_gerekcesi}` : "";
            toast.success(`Kuru koşu tamamlandı${karar ? ` · kapı: ${karar}` : ""}${gerekce}`);
            void load();
        } catch (e) {
            toast.error(zamanAsimiMi(e) ? ZAMAN_ASIMI_METNI : e instanceof Error ? e.message : "Kuru koşu başlatılamadı");
            if (zamanAsimiMi(e)) void load();
        } finally {
            setBusyId(null);
        }
    };

    const handleRaporlar = async (t: Teslim) => {
        if (acikRaporId === t.id) {
            setAcikRaporId(null);
            return;
        }
        setBusyId(t.id);
        try {
            const res = await apiClient.fetch(`${BASE}/teslimler/${t.id}/raporlar`);
            if (!res.ok) throw new Error(await hataMetni(res, "Raporlar alınamadı"));
            const data = await res.json();
            setRaporlar(prev => ({ ...prev, [t.id]: data.dosyalar ?? [] }));
            setAcikRaporId(t.id);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Raporlar alınamadı");
        } finally {
            setBusyId(null);
        }
    };

    // Rapor dosyası apiClient üzerinden (Bearer başlığıyla) blob olarak alınır;
    // düz <a href> yetkisiz gider. Blob geçici URL'ye bağlanıp indirilir.
    const handleIndir = async (t: Teslim, ad: string) => {
        const anahtar = `${t.id}:${ad}`;
        setIndirilen(anahtar);
        try {
            const res = await apiClient.fetch(`${BASE}/teslimler/${t.id}/raporlar/${encodeURIComponent(ad)}`);
            if (!res.ok) throw new Error(await hataMetni(res, "Rapor indirilemedi"));
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = ad;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            toast.success(`İndirildi: ${ad}`);
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Rapor indirilemedi");
        } finally {
            setIndirilen(null);
        }
    };

    const handleUygula = async () => {
        if (!onayTeslim) return;
        const t = onayTeslim;
        setIsApplying(true);
        try {
            const res = await apiClient.fetch(`${BASE}/teslimler/${t.id}/uygula`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ onay: true }),
            });
            if (res.status === 409) throw new Error("Bu durumda uygulanamaz");
            if (!res.ok) throw new Error(await hataMetni(res, "Uygulama başlatılamadı"));
            const data = await res.json();
            toast.success(`Uygulama başlatıldı: ${t.dosya_adi} (${DURUM_ETIKET[data.durum as TeslimDurum] ?? data.durum})`);
            setOnayTeslim(null);
            void load();
        } catch (e) {
            toast.error(zamanAsimiMi(e) ? ZAMAN_ASIMI_METNI : e instanceof Error ? e.message : "Uygulama başlatılamadı");
            if (zamanAsimiMi(e)) void load();
        } finally {
            setIsApplying(false);
        }
    };

    const mesaide = onayTeslim ? mesaiSaatindeMi() : false;

    return (
        <Card className="w-full bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
            <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                        <CardTitle>Veri Teslimleri</CardTitle>
                        <CardDescription>
                            Veri ekibinin teslim defteri: yükle, tara, kuru koş, raporları indir, onayla uygula.
                            {esikler && (
                                <span className="block mt-1 text-[11px] font-mono text-[var(--fg-muted)]">
                                    Eşikler · hata oranı {esikler.hata_orani} · eşleşmeyen oranı {esikler.eslesmeyen_orani} · alan değişikliği {esikler.alan_degisikligi}
                                </span>
                            )}
                        </CardDescription>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="rounded-none"
                            disabled={isScanning}
                            onClick={() => void handleTara()}
                        >
                            {isScanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                            Şimdi tara
                        </Button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".xlsx"
                            className="hidden"
                            data-testid="teslim-dosya"
                            onChange={e => {
                                const f = e.target.files?.[0];
                                if (f) void handleUpload(f);
                            }}
                        />
                        <Button
                            type="button"
                            size="sm"
                            className="rounded-none"
                            disabled={isUploading}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                            Dosya yükle
                        </Button>
                    </div>
                </div>
                {!isLoading && !loadError && !etkin && (
                    <p
                        role="status"
                        className="mt-3 border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2 text-[12px]"
                    >
                        Otomasyon kapalı — Özellikler sekmesinden açın.
                    </p>
                )}
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-6">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                ) : loadError ? (
                    <p className="text-sm text-destructive py-2">{loadError}</p>
                ) : teslimler.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-2">Henüz teslim yok.</p>
                ) : (
                    <div className="w-full overflow-x-auto">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Dosya</TableHead>
                                    <TableHead>Kaynak</TableHead>
                                    <TableHead>Durum</TableHead>
                                    <TableHead className="whitespace-nowrap">Okunan / İşlenen / Atlanan / Hata</TableHead>
                                    <TableHead className="whitespace-nowrap">Alan değişikliği</TableHead>
                                    <TableHead>Kapı</TableHead>
                                    <TableHead>Tarih</TableHead>
                                    <TableHead className="text-right">İşlem</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {teslimler.map(t => {
                                    const mesgul = busyId === t.id;
                                    const raporAcik = acikRaporId === t.id;
                                    return (
                                        <TeslimSatiri
                                            key={t.id}
                                            t={t}
                                            mesgul={mesgul}
                                            raporAcik={raporAcik}
                                            raporlar={raporlar[t.id] ?? []}
                                            indirilen={indirilen}
                                            onKuruKos={() => void handleKuruKos(t)}
                                            onRaporlar={() => void handleRaporlar(t)}
                                            onIndir={ad => void handleIndir(t, ad)}
                                            onUygula={() => setOnayTeslim(t)}
                                        />
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </div>
                )}
            </CardContent>

            <Dialog open={onayTeslim !== null} onOpenChange={open => { if (!open && !isApplying) setOnayTeslim(null); }}>
                <DialogContent className="rounded-none">
                    <DialogHeader>
                        <DialogTitle>Teslimi uygula</DialogTitle>
                        <DialogDescription>
                            Bu işlem dava kartlarına yazar ve geri alınmaz. Kuru koşu raporunu incelediğinizden emin olun.
                        </DialogDescription>
                    </DialogHeader>
                    {onayTeslim && (
                        <div className="space-y-2 text-sm" data-testid="uygula-onay">
                            <p className="font-medium break-all">{onayTeslim.dosya_adi}</p>
                            <p className="text-[12px] text-[var(--fg-muted)] font-mono">
                                okunan {sayi(onayTeslim.okunan)} · işlenen {sayi(onayTeslim.islenen)} · atlanan {sayi(onayTeslim.atlanan)} · hata {sayi(onayTeslim.hata_sayisi)} · alan değişikliği {sayi(onayTeslim.alan_degisikligi)} · kart {sayi(onayTeslim.kart_degisen)}
                            </p>
                            {onayTeslim.envanter_denk === false && (
                                <p className="text-[12px] text-red-700">Belge envanteri denk değil.</p>
                            )}
                            <p className="text-[12px]">
                                <span className="text-[var(--fg-muted)]">Kapı: </span>
                                {onayTeslim.kapi_karari ? KAPI_ETIKET[onayTeslim.kapi_karari] : "—"}
                                {onayTeslim.kapi_gerekcesi ? ` — ${onayTeslim.kapi_gerekcesi}` : ""}
                            </p>
                            {mesaide && (
                                <p
                                    role="alert"
                                    className="border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2 text-[12px]"
                                >
                                    Mesai saatindesiniz (09:00–18:00). Uygulama sırasında kartlar değişir; mümkünse mesai dışına bırakın.
                                </p>
                            )}
                        </div>
                    )}
                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            className="rounded-none"
                            disabled={isApplying}
                            onClick={() => setOnayTeslim(null)}
                        >
                            Vazgeç
                        </Button>
                        <Button
                            type="button"
                            className="rounded-none"
                            disabled={isApplying}
                            onClick={() => void handleUygula()}
                        >
                            {isApplying && <Loader2 className="h-4 w-4 animate-spin" />}
                            Onaylıyorum, uygula
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
}

interface SatirProps {
    t: Teslim;
    mesgul: boolean;
    raporAcik: boolean;
    raporlar: RaporDosyasi[];
    indirilen: string | null;
    onKuruKos: () => void;
    onRaporlar: () => void;
    onIndir: (ad: string) => void;
    onUygula: () => void;
}

function TeslimSatiri({ t, mesgul, raporAcik, raporlar, indirilen, onKuruKos, onRaporlar, onIndir, onUygula }: SatirProps) {
    const kapiMetni = t.kapi_karari ? KAPI_ETIKET[t.kapi_karari] : "—";
    return (
        <>
            <TableRow data-teslim-id={t.id} data-durum={t.durum}>
                <TableCell className="align-top">
                    <p className="font-medium break-all">{t.dosya_adi}</p>
                    {t.onceki_teslim_adi && (
                        <p className="text-[11px] text-[var(--fg-muted)] mt-0.5 break-all">
                            Önceki: {t.onceki_teslim_adi}
                            {t.zincir_tamam === false && <span className="text-red-700"> · zincir kopuk</span>}
                        </p>
                    )}
                    {t.hata_mesaji && (
                        <p className="text-[11px] text-red-700 mt-0.5 break-words">{t.hata_mesaji}</p>
                    )}
                </TableCell>
                <TableCell className="align-top whitespace-nowrap">{KAYNAK_ETIKET[t.kaynak] ?? t.kaynak}</TableCell>
                <TableCell className="align-top"><DurumRozeti durum={t.durum} /></TableCell>
                <TableCell className="align-top font-mono text-[12px] whitespace-nowrap" data-testid="sayaclar">
                    {sayi(t.okunan)} / {sayi(t.islenen)} / {sayi(t.atlanan)} / {sayi(t.hata_sayisi)}
                    {t.envanter_denk === false && (
                        <span className="block text-red-700 font-sans text-[11px]">envanter denk değil</span>
                    )}
                </TableCell>
                <TableCell className="align-top font-mono text-[12px]" data-testid="alan-degisikligi">
                    {sayi(t.alan_degisikligi)}
                    {t.kart_degisen !== null && (
                        <span className="text-[var(--fg-muted)]"> ({t.kart_degisen} kart)</span>
                    )}
                </TableCell>
                <TableCell className="align-top">
                    <span title={t.kapi_gerekcesi ?? undefined} className={t.kapi_gerekcesi ? "underline decoration-dotted cursor-help" : ""}>
                        {kapiMetni}
                    </span>
                </TableCell>
                <TableCell className="align-top whitespace-nowrap text-[12px]">
                    <span title={t.done_at ? `Bitiş: ${tarih(t.done_at)}` : undefined}>{tarih(t.created_at)}</span>
                    {t.uygulayan && (
                        <span className="block text-[11px] text-[var(--fg-muted)]">{t.uygulayan}</span>
                    )}
                </TableCell>
                <TableCell className="align-top">
                    <div className="flex flex-wrap justify-end gap-1">
                        {KURU_KOS_IZINLI.has(t.durum) && (
                            <Button type="button" variant="outline" size="sm" className="rounded-none" disabled={mesgul} onClick={onKuruKos}>
                                Kuru koş
                            </Button>
                        )}
                        <Button type="button" variant="ghost" size="sm" className="rounded-none" disabled={mesgul} onClick={onRaporlar}>
                            Raporlar
                        </Button>
                        {UYGULA_IZINLI.has(t.durum) && (
                            <Button type="button" size="sm" className="rounded-none" disabled={mesgul} onClick={onUygula}>
                                Uygula
                            </Button>
                        )}
                    </div>
                </TableCell>
            </TableRow>
            {raporAcik && (
                <TableRow data-rapor-satiri={t.id}>
                    <TableCell colSpan={8} className="bg-[var(--bg)]">
                        {raporlar.length === 0 ? (
                            <p className="text-[12px] text-[var(--fg-muted)]">Rapor dosyası yok.</p>
                        ) : (
                            <ul className="flex flex-wrap gap-2">
                                {raporlar.map(r => {
                                    const anahtar = `${t.id}:${r.ad}`;
                                    return (
                                        <li key={r.ad}>
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                className="rounded-none font-mono text-[11px]"
                                                disabled={indirilen === anahtar}
                                                onClick={() => onIndir(r.ad)}
                                            >
                                                {indirilen === anahtar && <Loader2 className="h-3 w-3 animate-spin" />}
                                                {r.ad} <span className="text-[var(--fg-muted)]">({boyut(r.boyut)})</span>
                                            </Button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </TableCell>
                </TableRow>
            )}
        </>
    );
}
