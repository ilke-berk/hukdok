/**
 * Kart alanı için hata bildirimi (02.10.2026) — zil düğmesi, bildirim penceresi, açık bildirim şeridi.
 *
 * Avukat kartta yanlış gördüğü bilginin yanındaki küçük kırmızı zile basar, doğrusunu / notunu yazar
 * ve bildirimin kime gideceğini seçer (idari personel + iç avukatlar + yönetici; son seçim tarayıcıda
 * hatırlanır, ilk kullanımda Yönetim > E-posta Alıcıları > "Hata bildirimi" işaretlileri ön-seçilidir).
 * Alıcı kartı açınca üstte açık bildirimleri görür, kaydı düzeltir ve bildirimi kapatır.
 *
 * Doğrudan düzeltme: davanın sorumlu avukatı (ya da yönetici) doğrusunu biliyorsa "Kendim düzelt"
 * ile kimseye bildirmeden kaydı düzeltir — yalnız sunucunun izin verdiği serbest metinli alanlarda
 * (esas no, hasar/hukuk/klasör no, yargı birimi) ve "Emin misiniz?" onayından sonra.
 *
 * Kullanım: kart `HataBildirimSaglayici` ile sarılır (hedef = dava ya da müvekkil); alanların yanına
 * `HataBildirButonu`, kartın üstüne `AcikHataBildirimleri` konur. Sağlayıcı YOKSA düğme ve şerit hiç
 * çizilmez — alan bileşenleri sağlayıcısız ekranlarda (ve testlerde) olduğu gibi çalışır.
 *
 * Bilinçli seçimler:
 * - İyimser güncelleme YOK: gönderim/kapatma başarılı olunca liste sunucudan yeniden çekilir.
 * - Liste yüklenemezse kart BOZULMAZ ve toast atılmaz: ziller çalışır, yalnız "açık bildirim var"
 *   işareti görünmez (kartın asıl işi bu listeye bağlı değil).
 * - Metinler düz metin basılır (React kaçışı), satır sonları `whitespace-pre-wrap`.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Bell, BellRing, Check, Pencil, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { notTarihi } from "@/lib/caseNotes";
import { Checkbox } from "@/components/ui/checkbox";
import {
    type HataAliciAdayi,
    type HataBildirimi,
    type HataHedefi,
    ALICI_GRUPLARI,
    GENEL_ALAN,
    HATA_ACIKLAMA_AZAMI,
    HATA_DEGER_AZAMI,
    HATA_DOGRUDAN_DEGER_AZAMI,
    alicilariGetir,
    alicilarMetni,
    dogrudanAlanlariGetir,
    kapat,
    kisiEtiketi,
    listele,
    olustur,
    onSecim,
    sonAlicilariOku,
    sonAlicilariYaz,
    taslakGecerliMi,
} from "@/lib/hataBildirimleri";

interface BildirilecekAlan {
    alan: string;
    etiket: string;
    deger: string | null;
}

interface BaglamDegeri {
    acik: HataBildirimi[];
    acikAlanlar: ReadonlySet<string>;
    bildir: (hedefAlan: BildirilecekAlan) => void;
    yenile: () => Promise<void>;
}

const Baglam = createContext<BaglamDegeri | null>(null);

const hataMesaji = (err: unknown, varsayilan: string): string =>
    err instanceof Error && err.message ? err.message : varsayilan;

/** Ekrandaki değerin bildirime yazılacak hâli: boş/tanımsız → null, gerisi kırpılmış metin. */
const degerMetni = (deger: unknown): string | null => {
    if (deger === null || deger === undefined) return null;
    const metin = String(deger).trim();
    return metin ? metin.slice(0, HATA_DEGER_AZAMI) : null;
};

interface SaglayiciProps {
    hedef: HataHedefi;
    /** Bildiren kaydı KENDİSİ düzelttikten sonra (kart verisini tazelemek için). */
    onDuzeltildi?: () => void;
    children: ReactNode;
}

export function HataBildirimSaglayici({ hedef, onDuzeltildi, children }: SaglayiciProps) {
    const caseId = hedef.caseId ?? null;
    const clientId = hedef.clientId ?? null;
    const [acik, setAcik] = useState<HataBildirimi[]>([]);
    const [secili, setSecili] = useState<BildirilecekAlan | null>(null);
    // Hedef değişince (başka müvekkil seçildi) geç gelen eski yanıt listeyi ezmesin.
    const turRef = useRef(0);

    const sabitHedef = useMemo<HataHedefi | null>(
        () => (caseId != null ? { caseId } : clientId != null ? { clientId } : null),
        [caseId, clientId],
    );

    const yenile = useCallback(async () => {
        if (!sabitHedef) return;
        const tur = ++turRef.current;
        try {
            const liste = await listele(sabitHedef);
            if (tur === turRef.current) setAcik(liste);
        } catch {
            if (tur === turRef.current) setAcik([]);
        }
    }, [sabitHedef]);

    useEffect(() => {
        setAcik([]);
        void yenile();
    }, [yenile]);

    const deger = useMemo<BaglamDegeri>(() => ({
        acik,
        acikAlanlar: new Set(acik.map(b => b.alan)),
        bildir: setSecili,
        yenile,
    }), [acik, yenile]);

    return (
        <Baglam.Provider value={deger}>
            {children}
            {sabitHedef && (
                <HataBildirPenceresi
                    hedef={sabitHedef}
                    alan={secili}
                    onKapat={() => setSecili(null)}
                    onGonderildi={yenile}
                    onDuzeltildi={onDuzeltildi}
                />
            )}
        </Baglam.Provider>
    );
}

interface ButonProps {
    /** Kart alanının anahtarı ("esas_no", "taraf:12"); verilmezse karta genel bildirim. */
    alan?: string;
    etiket?: string;
    /** Ekranda görünen değer — bildirime "kayıtlı değer" olarak yazılır. */
    deger?: unknown;
    /** true: "Hata Bildir" yazılı düğme (kart başlığı); false: yalnız küçük zil (alan yanı). */
    metinli?: boolean;
    className?: string;
}

export function HataBildirButonu({ alan = GENEL_ALAN, etiket = "Genel", deger, metinli = false, className = "" }: ButonProps) {
    const baglam = useContext(Baglam);
    if (!baglam) return null;
    const acikVar = baglam.acikAlanlar.has(alan);
    const Ikon = acikVar ? BellRing : Bell;
    const baslik = acikVar ? `${etiket}: açık hata bildirimi var — yeni bildirim ekle` : `${etiket} için hata bildir`;
    const tikla = (e: React.MouseEvent) => {
        // Zil tıklanabilir bir satırın/kartın içinde durabilir (taraf kartı) — onu tetiklemesin.
        e.preventDefault();
        e.stopPropagation();
        baglam.bildir({ alan, etiket, deger: degerMetni(deger) });
    };

    if (metinli) {
        return (
            <Button
                type="button"
                variant="outline"
                size="sm"
                className={`gap-2 border-tone-danger/40 text-tone-danger hover:bg-tone-danger/10 hover:text-tone-danger ${className}`}
                onClick={tikla}
                data-testid="hata-bildir-genel"
            >
                <Ikon className="w-4 h-4" />
                Hata Bildir
            </Button>
        );
    }
    return (
        <button
            type="button"
            onClick={tikla}
            title={baslik}
            aria-label={baslik}
            data-testid="hata-bildir"
            data-alan={alan}
            data-acik={acikVar ? "1" : "0"}
            className={`inline-grid place-items-center align-middle ml-1 p-0.5 rounded-[3px] text-tone-danger transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-tone-danger ${acikVar ? "opacity-100" : "opacity-45"} ${className}`}
        >
            <Ikon className="w-3 h-3" strokeWidth={acikVar ? 2.4 : 2} />
        </button>
    );
}

function HataBildirPenceresi({
    hedef, alan, onKapat, onGonderildi, onDuzeltildi,
}: {
    hedef: HataHedefi;
    alan: BildirilecekAlan | null;
    onKapat: () => void;
    onGonderildi: () => Promise<void>;
    onDuzeltildi?: () => void;
}) {
    const [dogruDeger, setDogruDeger] = useState("");
    const [aciklama, setAciklama] = useState("");
    const [gonderiliyor, setGonderiliyor] = useState(false);
    // Doğrudan düzeltme (02.10): davanın sorumlu avukatı / yönetici doğrusunu biliyorsa kimseye
    // bildirmeden kaydı kendisi düzeltir. Hangi alanlarda yapabileceğini sunucu söyler (null =
    // henüz sorulmadı; müvekkil kartında hiç sorulmaz). Uygulamadan önce "emin misiniz" adımı.
    const [dogrudanAlanlar, setDogrudanAlanlar] = useState<string[] | null>(null);
    const [onayda, setOnayda] = useState(false);
    const hedefCaseId = hedef.caseId ?? null;
    // Alıcı adayları: null = henüz çekilmedi/çekiliyor, "hata" = alınamadı (bildirim yine
    // gönderilebilir — sunucu varsayılan alıcılara yollar). Kart başına BİR KEZ çekilir.
    const [adaylar, setAdaylar] = useState<HataAliciAdayi[] | "hata" | null>(null);
    const [secili, setSecili] = useState<string[]>([]);
    const pencereAcik = alan != null;

    useEffect(() => {
        if (!pencereAcik) {
            // Alınamayan liste bir sonraki açılışta yeniden denenir.
            if (adaylar === "hata") setAdaylar(null);
            return;
        }
        if (adaylar !== null) return;
        let iptal = false;
        alicilariGetir()
            .then(liste => { if (!iptal) setAdaylar(liste); })
            .catch(() => { if (!iptal) setAdaylar("hata"); });
        return () => { iptal = true; };
    }, [pencereAcik, adaylar]);

    // Her açılışta taslak sıfırlanır: önceki alanın metni yeni alana taşınmasın. Alıcı ön-seçimi
    // son seçimden gelir (yoksa yönetim panelindeki varsayılanlar) — liste geç gelirse o an uygulanır.
    useEffect(() => {
        if (alan) {
            setDogruDeger("");
            setAciklama("");
        }
        setOnayda(false);
    }, [alan]);
    useEffect(() => {
        if (alan && Array.isArray(adaylar)) setSecili(onSecim(adaylar, sonAlicilariOku()));
    }, [alan, adaylar]);

    useEffect(() => {
        if (!pencereAcik || hedefCaseId == null || dogrudanAlanlar !== null) return;
        let iptal = false;
        void dogrudanAlanlariGetir(hedefCaseId).then(alanlar => { if (!iptal) setDogrudanAlanlar(alanlar); });
        return () => { iptal = true; };
    }, [pencereAcik, hedefCaseId, dogrudanAlanlar]);

    const genel = alan?.alan === GENEL_ALAN;
    const yeniDeger = dogruDeger.trim();
    const dogrudanMumkun = alan != null && !genel && (dogrudanAlanlar ?? []).includes(alan.alan);
    // "Kendim düzelt": doğrusu yazılmış, kayıtlı değerden farklı ve karta sığacak uzunlukta.
    const dogrudanHazir = dogrudanMumkun && yeniDeger.length > 0 && yeniDeger.length <= HATA_DOGRUDAN_DEGER_AZAMI
        && yeniDeger !== (alan?.deger ?? "") && !gonderiliyor;

    const dogrudanDuzelt = async () => {
        if (!alan || !dogrudanHazir) return;
        setGonderiliyor(true);
        try {
            await olustur(hedef, {
                alan: alan.alan,
                alanEtiketi: alan.etiket,
                mevcutDeger: alan.deger,
                dogruDeger: yeniDeger,
                aciklama,
                dogrudanDuzelt: true,
            });
            toast.success(`${alan.etiket} düzeltildi`, { description: `${alan.deger ?? "(boş)"} → ${yeniDeger}` });
            onKapat();
            await onGonderildi();
            onDuzeltildi?.();
        } catch (err) {
            toast.error(hataMesaji(err, "Düzeltme uygulanamadı."));
            setOnayda(false);
        } finally {
            setGonderiliyor(false);
        }
    };
    const adayListesi = Array.isArray(adaylar) ? adaylar : null;
    // Aday listesi geldiyse en az bir alıcı şart; liste alınamadıysa ya da boşsa sunucu varsayılanı.
    const aliciTamam = !adayListesi || adayListesi.length === 0 || secili.length > 0;
    const gecerli = taslakGecerliMi(dogruDeger, aciklama) && aliciTamam && adaylar !== null && !gonderiliyor;

    const aliciDegistir = (email: string, isaretli: boolean) =>
        setSecili(onceki => (isaretli ? [...onceki.filter(e => e !== email), email] : onceki.filter(e => e !== email)));

    const gonder = async () => {
        if (!alan || !gecerli) return;
        setGonderiliyor(true);
        try {
            // Aday sırasıyla gönder (seçim sırası değil): satırdaki "Kime" metni kararlı olsun.
            const alicilar = adayListesi?.filter(a => secili.includes(a.email)).map(a => a.email);
            const kayit = await olustur(hedef, {
                alan: alan.alan,
                alanEtiketi: alan.etiket,
                mevcutDeger: alan.deger,
                dogruDeger,
                aciklama,
                alicilar,
            });
            if (alicilar && alicilar.length > 0) sonAlicilariYaz(alicilar);
            const kime = alicilarMetni(kayit.alicilar);
            toast.success("Hata bildirimi gönderildi", {
                description: kime ? `Gönderildi: ${kime}` : "Kayıt açıldı; tanımlı alıcı olmadığı için bildirim gitmedi.",
            });
            onKapat();
            await onGonderildi();
        } catch (err) {
            toast.error(hataMesaji(err, "Hata bildirimi gönderilemedi."));
        } finally {
            setGonderiliyor(false);
        }
    };

    return (
        <Dialog open={pencereAcik} onOpenChange={(yeniDurum) => { if (!yeniDurum && !gonderiliyor) onKapat(); }}>
            <DialogContent className="theme-classic bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none" data-testid="hata-bildir-pencere">
                <DialogHeader>
                    <DialogTitle className="font-display font-medium text-[18px] text-tone-danger flex items-center gap-2">
                        <Bell className="w-4 h-4" />
                        Hata bildir{alan && !genel ? `: ${alan.etiket}` : ""}
                    </DialogTitle>
                    <DialogDescription className="text-[13px] text-[var(--fg-muted)] leading-relaxed">
                        Bildirim seçtiğiniz kişilere uygulama içinden iletilir; kayıt düzeltilince size haber verilir.
                    </DialogDescription>
                </DialogHeader>

                {onayda && alan ? (
                    <div className="grid gap-3" data-testid="hata-dogrudan-onay">
                        <p className="text-sm font-semibold text-[var(--fg)]">Emin misiniz?</p>
                        <div className="p-3 border border-tone-danger/40 bg-tone-danger/5 grid gap-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-subtle)]">{alan.etiket}</span>
                            <p className="text-sm break-words">
                                <span className="line-through opacity-70">{alan.deger ?? "(boş)"}</span>
                                <span className="mx-2 text-[var(--fg-muted)]">→</span>
                                <span className="font-semibold" data-testid="hata-dogrudan-yeni">{yeniDeger}</span>
                            </p>
                        </div>
                        <p className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                            Kayıt hemen değiştirilir ve dava geçmişine adınızla yazılır; kimseye bildirim gönderilmez.
                        </p>
                    </div>
                ) : (
                <div className="grid gap-3">
                    {alan && !genel && (
                        <div className="p-3 border border-[var(--border)] bg-[var(--bg)]">
                            <span className="block text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-subtle)]">Kayıtlı değer</span>
                            <span className="block mt-0.5 text-sm whitespace-pre-wrap break-words" data-testid="hata-mevcut-deger">
                                {alan.deger ?? "— (boş)"}
                            </span>
                        </div>
                    )}
                    {!genel && (
                        <label className="grid gap-1">
                            <span className="text-[12px] text-[var(--fg-muted)]">Doğrusu</span>
                            <Input
                                value={dogruDeger}
                                onChange={e => setDogruDeger(e.target.value)}
                                maxLength={HATA_DEGER_AZAMI}
                                placeholder="Olması gereken değer (biliyorsanız)"
                                disabled={gonderiliyor}
                                className="bg-[var(--bg)] border-[var(--border-strong)] rounded-[3px]"
                                data-testid="hata-dogru-deger"
                            />
                            {dogrudanMumkun && (
                                <span className="text-[11.5px] text-[var(--fg-subtle)] leading-relaxed" data-testid="hata-dogrudan-ipucu">
                                    Bu dosyada yetkilisiniz: doğrusunu yazıp “Kendim düzelt” ile kaydı kimseye bildirmeden düzeltebilirsiniz.
                                </span>
                            )}
                        </label>
                    )}
                    <label className="grid gap-1">
                        <span className="text-[12px] text-[var(--fg-muted)]">Açıklama</span>
                        <Textarea
                            rows={3}
                            value={aciklama}
                            onChange={e => setAciklama(e.target.value)}
                            maxLength={HATA_ACIKLAMA_AZAMI}
                            placeholder={genel ? "Kartta neyin yanlış olduğunu yazın…" : "Not (isteğe bağlı): neden yanlış, kaynağı ne…"}
                            disabled={gonderiliyor}
                            className="bg-[var(--bg)] border-[var(--border-strong)] rounded-[3px] resize-none"
                            data-testid="hata-aciklama"
                        />
                    </label>

                    <fieldset className="grid gap-1.5" data-testid="hata-alicilar">
                        <legend className="text-[12px] text-[var(--fg-muted)] mb-1">Kime gönderilsin</legend>
                        {adaylar === null ? (
                            <p className="text-[12px] text-[var(--fg-subtle)]">Alıcılar yükleniyor…</p>
                        ) : adaylar === "hata" ? (
                            <p className="text-[12px] text-tone-caution" data-testid="hata-alici-hatasi">
                                Alıcı listesi alınamadı — bildirim varsayılan alıcılara gönderilecek.
                            </p>
                        ) : adaylar.length === 0 ? (
                            <p className="text-[12px] text-[var(--fg-subtle)]">
                                Tanımlı alıcı yok — kayıt yine açılır ve idari panoda görünür.
                            </p>
                        ) : (
                            <div className="grid gap-2.5 p-3 border border-[var(--border)] bg-[var(--bg)] max-h-[190px] overflow-y-auto">
                                {ALICI_GRUPLARI.map(({ grup, baslik }) => {
                                    const kisiler = adaylar.filter(a => a.grup === grup);
                                    if (kisiler.length === 0) return null;
                                    return (
                                        <div key={grup} className="grid gap-1.5">
                                            <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-subtle)]">{baslik}</span>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
                                                {kisiler.map(a => (
                                                    <label key={a.email} className="flex items-center gap-2 cursor-pointer min-w-0" title={a.email}>
                                                        <Checkbox
                                                            checked={secili.includes(a.email)}
                                                            onCheckedChange={v => aliciDegistir(a.email, v === true)}
                                                            disabled={gonderiliyor}
                                                            className="w-4 h-4 rounded-[2px] shrink-0 data-[state=checked]:bg-brand-solid data-[state=checked]:border-brand-solid"
                                                            data-testid="hata-alici"
                                                            data-email={a.email}
                                                        />
                                                        <span className="text-[13px] text-[var(--fg)] truncate">{a.ad}</span>
                                                    </label>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        {adayListesi && adayListesi.length > 0 && secili.length === 0 && (
                            <p className="text-[12px] text-tone-danger" data-testid="hata-alici-uyari">En az bir alıcı seçin.</p>
                        )}
                    </fieldset>
                </div>
                )}

                {onayda ? (
                    <DialogFooter className="gap-2 sm:space-x-0">
                        <Button type="button" variant="outline" onClick={() => setOnayda(false)} disabled={gonderiliyor} className="rounded-[3px]">
                            Geri
                        </Button>
                        <Button
                            type="button"
                            onClick={() => void dogrudanDuzelt()}
                            disabled={!dogrudanHazir}
                            className="bg-tone-danger hover:bg-tone-danger/90 text-white rounded-[3px]"
                            data-testid="hata-dogrudan-onayla"
                        >
                            {gonderiliyor ? "Düzeltiliyor…" : "Evet, düzelt"}
                        </Button>
                    </DialogFooter>
                ) : (
                    <DialogFooter className="gap-2 sm:space-x-0">
                        <Button type="button" variant="outline" onClick={onKapat} disabled={gonderiliyor} className="rounded-[3px]">
                            Vazgeç
                        </Button>
                        {dogrudanMumkun && (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setOnayda(true)}
                                disabled={!dogrudanHazir}
                                className="rounded-[3px] border-tone-danger/50 text-tone-danger hover:bg-tone-danger/10 hover:text-tone-danger"
                                data-testid="hata-dogrudan"
                            >
                                Kendim düzelt
                            </Button>
                        )}
                        <Button
                            type="button"
                            onClick={() => void gonder()}
                            disabled={!gecerli}
                            className="bg-tone-danger hover:bg-tone-danger/90 text-white rounded-[3px]"
                            data-testid="hata-gonder"
                        >
                            {gonderiliyor ? "Gönderiliyor…" : "Bildir"}
                        </Button>
                    </DialogFooter>
                )}
            </DialogContent>
        </Dialog>
    );
}

interface SeritProps {
    /** Bildirimden gelindiyse (`?hata=<id>`) o satır vurgulanır ve görünür alana kaydırılır. */
    vurgulananId?: number | null;
    /** Kaydı düzeltme ekranına götürür (dava formu / müvekkil formu). */
    onDuzelt?: () => void;
    /** Bir bildirim kapatıldıktan sonra (kart verisini tazelemek için). */
    onKapandi?: () => void;
    className?: string;
}

/** Kartın üstündeki "açık hata bildirimleri" şeridi — açık bildirim yoksa hiç çizilmez. */
export function AcikHataBildirimleri({ vurgulananId = null, onDuzelt, onKapandi, className = "" }: SeritProps) {
    const baglam = useContext(Baglam);
    const [kapananId, setKapananId] = useState<number | null>(null);
    const vurguRef = useRef<HTMLLIElement | null>(null);
    const acik = baglam?.acik ?? [];
    const vurguVar = vurgulananId != null && acik.some(b => b.id === vurgulananId);

    useEffect(() => {
        if (vurguVar) vurguRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, [vurguVar]);

    if (!baglam || acik.length === 0) return null;

    const handleKapat = async (b: HataBildirimi, sonuc: "COZULDU" | "REDDEDILDI") => {
        let not: string | undefined;
        if (sonuc === "REDDEDILDI") {
            const yanit = window.prompt("Bildirim değişiklik yapılmadan kapatılacak. Bildirene iletilecek not (isteğe bağlı):", "");
            if (yanit === null) return;
            not = yanit;
        }
        setKapananId(b.id);
        try {
            await kapat(b.id, sonuc, not);
            toast.success(sonuc === "COZULDU" ? "Bildirim düzeltildi olarak kapatıldı" : "Bildirim kapatıldı");
            await baglam.yenile();
            onKapandi?.();
        } catch (err) {
            toast.error(hataMesaji(err, "Hata bildirimi kapatılamadı."));
            // 409: başkası kapatmış — liste bayat, tazele.
            await baglam.yenile();
        } finally {
            setKapananId(null);
        }
    };

    return (
        <section
            className={`border border-tone-danger/40 bg-tone-danger/5 ${className}`}
            aria-label="Açık hata bildirimleri"
            data-testid="acik-hata-bildirimleri"
        >
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-tone-danger/30">
                <span className="flex items-center gap-2 text-sm font-semibold text-tone-danger">
                    <BellRing className="w-4 h-4" />
                    Açık hata bildirimleri ({acik.length})
                </span>
                {onDuzelt && (
                    <Button type="button" variant="outline" size="sm" className="gap-1.5 border-tone-danger/40 hover:bg-tone-danger/10" onClick={onDuzelt}>
                        <Pencil className="w-3.5 h-3.5" />
                        Kaydı düzelt
                    </Button>
                )}
            </div>
            <ul className="divide-y divide-tone-danger/20">
                {acik.map(b => {
                    const vurgulu = b.id === vurgulananId;
                    return (
                        <li
                            key={b.id}
                            ref={vurgulu ? vurguRef : undefined}
                            className={`px-4 py-3 grid gap-1.5 ${vurgulu ? "bg-tone-danger/10" : ""}`}
                            data-testid="hata-bildirimi-satiri"
                            data-vurgulu={vurgulu ? "1" : "0"}
                        >
                            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                                <span className="text-sm font-semibold text-[var(--fg)]">{b.alan_etiketi}</span>
                                <span className="text-xs text-[var(--fg-muted)]">
                                    <span className="font-medium text-[var(--fg)]" title={b.bildiren_email}>
                                        {kisiEtiketi(b.bildiren_ad, b.bildiren_email)}
                                    </span>
                                    <span className="mx-1.5">·</span>
                                    <time dateTime={b.created_at}>{notTarihi(b.created_at)}</time>
                                </span>
                            </div>
                            {(b.mevcut_deger || b.dogru_deger) && (
                                <p className="text-sm break-words" data-testid="hata-deger-farki">
                                    <span className="text-[var(--fg-muted)]">Kayıtlı: </span>
                                    <span className={b.dogru_deger ? "line-through opacity-70" : ""}>{b.mevcut_deger ?? "—"}</span>
                                    {b.dogru_deger && (
                                        <>
                                            <span className="mx-1.5 text-[var(--fg-muted)]">→ Doğrusu:</span>
                                            <span className="font-semibold">{b.dogru_deger}</span>
                                        </>
                                    )}
                                </p>
                            )}
                            {b.aciklama && (
                                <p className="text-sm whitespace-pre-wrap break-words text-[var(--fg)]" data-testid="hata-aciklama-metni">{b.aciklama}</p>
                            )}
                            {b.alicilar?.length > 0 && (
                                <p className="text-xs text-[var(--fg-muted)]" data-testid="hata-kime">
                                    Gönderildi: <span className="text-[var(--fg)]">{alicilarMetni(b.alicilar)}</span>
                                </p>
                            )}
                            <div className="flex flex-wrap gap-2 pt-1">
                                <Button
                                    type="button"
                                    size="sm"
                                    className="h-7 gap-1.5"
                                    disabled={kapananId === b.id}
                                    onClick={() => void handleKapat(b, "COZULDU")}
                                    data-testid="hata-cozuldu"
                                >
                                    <Check className="w-3.5 h-3.5" />
                                    Düzeltildi
                                </Button>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 gap-1.5 text-[var(--fg-muted)]"
                                    disabled={kapananId === b.id}
                                    onClick={() => void handleKapat(b, "REDDEDILDI")}
                                    data-testid="hata-gecersiz"
                                >
                                    <X className="w-3.5 h-3.5" />
                                    Değişiklik gerekmiyor
                                </Button>
                            </div>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
}
