// Yönetim paneli "Ofis No Kodları" sekmesi (karar 023, G241) — numarada kullanılan
// iki kod listesi: müvekkil kategorisi kodları (DR, SC, HS, ...) ve sigorta şirketi
// kodları (AXA, ANADOLU, ...) + müvekkil adında aranan eşleşme kelimeleri.
// Silme YOK: sigorta satırı pasife alınır. Kurallar sunucudadır (G235); kod
// değişikliği verilmiş numaralara dokunmaz — yalnız yeni kartları etkiler.
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import {
    anahtarlariAyir, asciiBuyuk, kategoriOrnegi, kisiKategorisiMi, kodBicimle, kodSorunu,
    ofisNoKodlariApi, sigortaOrnegi,
    type KategoriKodu, type SigortaKodu,
} from "@/lib/ofisNoKodlari";

export const KOD_DEGISIKLIGI_UYARISI =
    "Kod değişikliği mevcut ofis numaralarını değiştirmez, yalnız yeni kartları etkiler.";

const KART = "bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none";
const ORNEK = "font-mono text-[12px] text-[var(--fg-muted)]";
const HATA = "text-sm text-destructive";

const mesaj = (e: unknown, varsayilan: string) => (e instanceof Error ? e.message : varsayilan);

/** Kategori adı → `client_categories.code` (AdminPage'deki kategori ekleme kuralıyla aynı). */
const kategoriAnahtari = (ad: string) =>
    ad.trim().split(/\s+/).map(asciiBuyuk).filter(Boolean).join("-");

export function OfisNoKodlariPanel() {
    const isAdmin = useIsAdmin();
    const queryClient = useQueryClient();

    const [kategoriler, setKategoriler] = useState<KategoriKodu[]>([]);
    const [sigortalar, setSigortalar] = useState<SigortaKodu[]>([]);
    const [varsayilanKod, setVarsayilanKod] = useState("SG");
    const [yukleniyor, setYukleniyor] = useState(true);
    const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
    const [mesgul, setMesgul] = useState(false);

    // Kategori: satır içi kod düzenleme + yeni kategori
    const [kategoriDuzenlenen, setKategoriDuzenlenen] = useState<string | null>(null);
    const [kategoriKodTaslak, setKategoriKodTaslak] = useState("");
    const [yeniKategori, setYeniKategori] = useState({ ad: "", kod: "" });
    const [kategoriHatasi, setKategoriHatasi] = useState<string | null>(null);

    // Sigorta: satır içi düzenleme + yeni şirket
    const [sigortaDuzenlenen, setSigortaDuzenlenen] = useState<number | null>(null);
    const [sigortaTaslak, setSigortaTaslak] = useState({ kod: "", ad: "", anahtarlar: "" });
    const [yeniSigorta, setYeniSigorta] = useState({ kod: "", ad: "", anahtarlar: "" });
    const [sigortaHatasi, setSigortaHatasi] = useState<string | null>(null);

    const yukle = useCallback(async () => {
        setYuklemeHatasi(null);
        try {
            const [k, s] = await Promise.all([
                ofisNoKodlariApi.kategoriKodlari(),
                ofisNoKodlariApi.sigortaKodlari(),
            ]);
            setKategoriler(k.kategoriler ?? []);
            setSigortalar(s.kodlar ?? []);
            if (s.varsayilan_kod) setVarsayilanKod(s.varsayilan_kod);
        } catch (e) {
            setYuklemeHatasi(mesaj(e, "Kod listeleri alınamadı"));
        } finally {
            setYukleniyor(false);
        }
    }, []);

    useEffect(() => {
        if (isAdmin === true) void yukle();
    }, [isAdmin, yukle]);

    // Bölüm yalnız yöneticiye görünür (uçlar da sunucuda `require_admin` arkasında).
    if (isAdmin !== true) return null;

    const doktorKodu = kategoriler.find(k => k.code === "DOKTOR")?.ofis_no_kodu || "DR";

    const kategoriKoduKaydet = async (kategori: KategoriKodu) => {
        const sorun = kodSorunu(kategoriKodTaslak);
        if (sorun) { setKategoriHatasi(sorun); return; }
        setMesgul(true);
        setKategoriHatasi(null);
        try {
            await ofisNoKodlariApi.kategoriKoduGuncelle(kategori.code, kategoriKodTaslak);
            toast.success("Kategori kodu güncellendi");
            setKategoriDuzenlenen(null);
            await yukle();
        } catch (e) {
            setKategoriHatasi(mesaj(e, "Kategori kodu güncellenemedi"));
        } finally {
            setMesgul(false);
        }
    };

    const kategoriEkle = async () => {
        const ad = yeniKategori.ad.trim();
        const anahtar = kategoriAnahtari(ad);
        if (!ad || !anahtar) { setKategoriHatasi("Kategori adı boş olamaz"); return; }
        const sorun = kodSorunu(yeniKategori.kod);
        if (sorun) { setKategoriHatasi(sorun); return; }
        setMesgul(true);
        setKategoriHatasi(null);
        try {
            await ofisNoKodlariApi.kategoriEkle(anahtar, ad);
        } catch (e) {
            setKategoriHatasi(mesaj(e, "Kategori eklenemedi"));
            setMesgul(false);
            return;
        }
        // Kategori kaydı oluştu; kodu ayrı uçtan yazılır (genel liste ucu kod taşımaz).
        try {
            await ofisNoKodlariApi.kategoriKoduGuncelle(anahtar, yeniKategori.kod);
            toast.success("Kategori eklendi");
            setYeniKategori({ ad: "", kod: "" });
        } catch (e) {
            setKategoriHatasi(
                `"${ad}" kategorisi eklendi ama kodu kaydedilemedi: ${mesaj(e, "bilinmeyen hata")}. ` +
                "Listeden kodunu düzenleyin.");
        } finally {
            void queryClient.invalidateQueries({ queryKey: ["config", "client_categories"] });
            await yukle();
            setMesgul(false);
        }
    };

    const sigortaEkle = async () => {
        const sorun = kodSorunu(yeniSigorta.kod);
        if (sorun) { setSigortaHatasi(sorun); return; }
        if (!yeniSigorta.ad.trim()) { setSigortaHatasi("Şirket adı boş olamaz"); return; }
        setMesgul(true);
        setSigortaHatasi(null);
        try {
            await ofisNoKodlariApi.sigortaKoduEkle({
                kod: yeniSigorta.kod,
                ad: yeniSigorta.ad.trim(),
                eslesme_anahtarlari: anahtarlariAyir(yeniSigorta.anahtarlar),
            });
            toast.success("Sigorta şirketi kodu eklendi");
            setYeniSigorta({ kod: "", ad: "", anahtarlar: "" });
            await yukle();
        } catch (e) {
            setSigortaHatasi(mesaj(e, "Sigorta kodu eklenemedi"));
        } finally {
            setMesgul(false);
        }
    };

    const sigortaKaydet = async (satir: SigortaKodu) => {
        const sorun = kodSorunu(sigortaTaslak.kod);
        if (sorun) { setSigortaHatasi(sorun); return; }
        if (!sigortaTaslak.ad.trim()) { setSigortaHatasi("Şirket adı boş olamaz"); return; }
        setMesgul(true);
        setSigortaHatasi(null);
        try {
            await ofisNoKodlariApi.sigortaKoduGuncelle(satir.id, {
                kod: sigortaTaslak.kod,
                ad: sigortaTaslak.ad.trim(),
                eslesme_anahtarlari: anahtarlariAyir(sigortaTaslak.anahtarlar),
            });
            toast.success("Sigorta şirketi kodu güncellendi");
            setSigortaDuzenlenen(null);
            await yukle();
        } catch (e) {
            setSigortaHatasi(mesaj(e, "Sigorta kodu güncellenemedi"));
        } finally {
            setMesgul(false);
        }
    };

    const sigortaAktiflik = async (satir: SigortaKodu) => {
        setMesgul(true);
        setSigortaHatasi(null);
        try {
            await ofisNoKodlariApi.sigortaKoduGuncelle(satir.id, { aktif: !satir.aktif });
            toast.success(satir.aktif ? "Kod pasife alındı" : "Kod etkinleştirildi");
            await yukle();
        } catch (e) {
            setSigortaHatasi(mesaj(e, "Sigorta kodu güncellenemedi"));
        } finally {
            setMesgul(false);
        }
    };

    if (yukleniyor) {
        return (
            <div className="flex justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="ofis-no-kodlari">
            <p role="note" className="text-sm border border-[var(--border)] bg-[var(--brand-soft)] text-[var(--fg)] px-4 py-3">
                {KOD_DEGISIKLIGI_UYARISI}
            </p>
            {yuklemeHatasi && <p className={HATA}>{yuklemeHatasi}</p>}

            {/* ── Kategori kodları ─────────────────────────────────────────── */}
            <Card className={KART} data-testid="kategori-kodlari">
                <CardHeader>
                    <CardTitle>Kategori Kodları</CardTitle>
                    <CardDescription>
                        Müvekkil kategorisinin numaradaki kısaltması. Kod 2-10 büyük ASCII harftir.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex flex-wrap items-end gap-2">
                        <Input
                            aria-label="Yeni kategori adı" placeholder="Kategori adı" className="max-w-xs"
                            value={yeniKategori.ad}
                            onChange={e => setYeniKategori({ ...yeniKategori, ad: e.target.value })}
                        />
                        <Input
                            aria-label="Yeni kategori kodu" placeholder="KOD" className="w-32 font-mono"
                            value={yeniKategori.kod} maxLength={10}
                            onChange={e => setYeniKategori({ ...yeniKategori, kod: kodBicimle(e.target.value) })}
                        />
                        <Button size="sm" onClick={() => void kategoriEkle()} disabled={mesgul}>Kategori ekle</Button>
                    </div>
                    {kategoriHatasi && <p role="alert" className={HATA}>{kategoriHatasi}</p>}
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Kategori</TableHead>
                                <TableHead>Kod</TableHead>
                                <TableHead>Örnek numara</TableHead>
                                <TableHead className="text-right">İşlemler</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {kategoriler.map(k => {
                                const duzenleniyor = kategoriDuzenlenen === k.code;
                                const gosterilenKod = duzenleniyor ? kategoriKodTaslak : (k.ofis_no_kodu ?? "");
                                return (
                                    <TableRow key={k.code} data-testid={`kategori-${k.code}`}>
                                        <TableCell>
                                            {k.name}
                                            {!k.active && <span className="ml-2 text-[11px] text-[var(--fg-muted)]">(pasif)</span>}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                            {duzenleniyor ? (
                                                <Input
                                                    aria-label={`${k.name} kodu`} className="w-32 font-mono"
                                                    value={kategoriKodTaslak} maxLength={10}
                                                    onChange={e => setKategoriKodTaslak(kodBicimle(e.target.value))}
                                                />
                                            ) : (k.ofis_no_kodu ?? "—")}
                                        </TableCell>
                                        <TableCell className={ORNEK}>
                                            {gosterilenKod
                                                ? kategoriOrnegi(gosterilenKod, kisiKategorisiMi(k, kategoriler))
                                                : "Kod tanımlı değil"}
                                        </TableCell>
                                        <TableCell className="text-right space-x-2">
                                            {duzenleniyor ? (
                                                <>
                                                    <Button size="sm" onClick={() => void kategoriKoduKaydet(k)} disabled={mesgul}>Kaydet</Button>
                                                    <Button size="sm" variant="outline" onClick={() => { setKategoriDuzenlenen(null); setKategoriHatasi(null); }}>Vazgeç</Button>
                                                </>
                                            ) : (
                                                <Button
                                                    size="sm" variant="outline" aria-label={`${k.name} kodunu düzenle`}
                                                    onClick={() => {
                                                        setKategoriDuzenlenen(k.code);
                                                        setKategoriKodTaslak(k.ofis_no_kodu ?? "");
                                                        setKategoriHatasi(null);
                                                    }}
                                                >Düzenle</Button>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>

            {/* ── Sigorta şirketi kodları ──────────────────────────────────── */}
            <Card className={KART} data-testid="sigorta-kodlari">
                <CardHeader>
                    <CardTitle>Sigorta Şirketi Kodları</CardTitle>
                    <CardDescription>
                        Müvekkil adında eşleşme kelimelerinden biri geçen sigortacı bu kodu alır. Silme yoktur;
                        pasife alınan şirketin yeni kartı {varsayilanKod} kodunu alır.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex flex-wrap items-end gap-2">
                        <Input
                            aria-label="Yeni sigorta kodu" placeholder="KOD" className="w-32 font-mono"
                            value={yeniSigorta.kod} maxLength={10}
                            onChange={e => setYeniSigorta({ ...yeniSigorta, kod: kodBicimle(e.target.value) })}
                        />
                        <Input
                            aria-label="Yeni sigorta şirketi adı" placeholder="Şirket adı" className="max-w-xs"
                            value={yeniSigorta.ad}
                            onChange={e => setYeniSigorta({ ...yeniSigorta, ad: e.target.value })}
                        />
                        <Input
                            aria-label="Yeni sigorta eşleşme kelimeleri" placeholder="Eşleşme kelimeleri (virgülle)" className="max-w-xs"
                            value={yeniSigorta.anahtarlar}
                            onChange={e => setYeniSigorta({ ...yeniSigorta, anahtarlar: e.target.value })}
                        />
                        <Button size="sm" onClick={() => void sigortaEkle()} disabled={mesgul}>Şirket ekle</Button>
                    </div>
                    {sigortaHatasi && <p role="alert" className={HATA}>{sigortaHatasi}</p>}
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Kod</TableHead>
                                <TableHead>Şirket</TableHead>
                                <TableHead>Eşleşme kelimeleri</TableHead>
                                <TableHead>Durum</TableHead>
                                <TableHead>Örnek numara</TableHead>
                                <TableHead className="text-right">İşlemler</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {sigortalar.map(s => {
                                const duzenleniyor = sigortaDuzenlenen === s.id;
                                const gosterilenKod = duzenleniyor ? sigortaTaslak.kod : s.kod;
                                return (
                                    <TableRow key={s.id} data-testid={`sigorta-${s.id}`} className={s.aktif ? undefined : "opacity-60"}>
                                        <TableCell className="font-mono">
                                            {duzenleniyor ? (
                                                <Input
                                                    aria-label={`${s.ad} kodu`} className="w-32 font-mono"
                                                    value={sigortaTaslak.kod} maxLength={10}
                                                    onChange={e => setSigortaTaslak({ ...sigortaTaslak, kod: kodBicimle(e.target.value) })}
                                                />
                                            ) : s.kod}
                                        </TableCell>
                                        <TableCell>
                                            {duzenleniyor ? (
                                                <Input
                                                    aria-label={`${s.ad} adı`} value={sigortaTaslak.ad}
                                                    onChange={e => setSigortaTaslak({ ...sigortaTaslak, ad: e.target.value })}
                                                />
                                            ) : s.ad}
                                        </TableCell>
                                        <TableCell className="font-mono text-[12px]">
                                            {duzenleniyor ? (
                                                <Input
                                                    aria-label={`${s.ad} eşleşme kelimeleri`} value={sigortaTaslak.anahtarlar}
                                                    onChange={e => setSigortaTaslak({ ...sigortaTaslak, anahtarlar: e.target.value })}
                                                />
                                            ) : s.eslesme_anahtarlari.join(", ")}
                                        </TableCell>
                                        <TableCell>{s.aktif ? "Aktif" : "Pasif"}</TableCell>
                                        <TableCell className={ORNEK}>
                                            {gosterilenKod ? sigortaOrnegi(gosterilenKod, doktorKodu) : "—"}
                                        </TableCell>
                                        <TableCell className="text-right space-x-2">
                                            {duzenleniyor ? (
                                                <>
                                                    <Button size="sm" onClick={() => void sigortaKaydet(s)} disabled={mesgul}>Kaydet</Button>
                                                    <Button size="sm" variant="outline" onClick={() => { setSigortaDuzenlenen(null); setSigortaHatasi(null); }}>Vazgeç</Button>
                                                </>
                                            ) : (
                                                <>
                                                    <Button
                                                        size="sm" variant="outline" aria-label={`${s.ad} satırını düzenle`}
                                                        onClick={() => {
                                                            setSigortaDuzenlenen(s.id);
                                                            setSigortaTaslak({ kod: s.kod, ad: s.ad, anahtarlar: s.eslesme_anahtarlari.join(", ") });
                                                            setSigortaHatasi(null);
                                                        }}
                                                    >Düzenle</Button>
                                                    <Button
                                                        size="sm" variant="outline" disabled={mesgul}
                                                        aria-label={s.aktif ? `${s.ad} pasife al` : `${s.ad} etkinleştir`}
                                                        onClick={() => void sigortaAktiflik(s)}
                                                    >{s.aktif ? "Pasife al" : "Etkinleştir"}</Button>
                                                </>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                            <TableRow data-testid="sigorta-varsayilan">
                                <TableCell className="font-mono">{varsayilanKod}</TableCell>
                                <TableCell>Listede olmayan sigortacı</TableCell>
                                <TableCell className="text-[12px] text-[var(--fg-muted)]">—</TableCell>
                                <TableCell>Sabit</TableCell>
                                <TableCell className={ORNEK}>{sigortaOrnegi(varsayilanKod, doktorKodu)}</TableCell>
                                <TableCell className="text-right text-[12px] text-[var(--fg-muted)]">Düzenlenmez</TableCell>
                            </TableRow>
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
