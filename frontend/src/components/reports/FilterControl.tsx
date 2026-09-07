import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import type { FiltreDeger, KatalogKolon, KolonTipi, KontrolDurumu, Secim, TarihKisayolu } from "@/lib/reports";
import {
    OP_ETIKETLERI, TARIH_KISAYOL_ETIKETLERI, bosSayisi, kolonOplari, opDegerSekli, secenekEtiketi, secenekSayisi, tarihKisayolu,
} from "@/lib/reports";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import type { SeritOgesi } from "./builderState";
import { ChipSelect } from "./ChipSelect";
import { BosAnahtari, BosCipi, SayiRozeti, VarYokAnahtari } from "./ToggleFilter";
import { INPUT_CLS, SELECT_CLS, useDisariTiklama } from "./ui";

type FilterControlProps = {
    oge: SeritOgesi;
    /** `oge.durum.alan`'ın kolonu. */
    kolon: KatalogKolon;
    /** Alan değiştirici etiketleri için (tarih aralığı alternatifleri). */
    kolonOf: (anahtar: string) => KatalogKolon | undefined;
    /** `gecikmeli`: yazarak girilen değer (600 ms bekletilir); seçim/tik anında. */
    onChange: (durum: KontrolDurumu, gecikmeli?: boolean) => void;
    /** Odak çıkışı — bekleyen gecikmeli önizleme hemen istenir. */
    onHemen: () => void;
    /** Kısayollar için bugün; test sabitler. */
    bugun?: () => Date;
};

const KISAYOLLAR: TarihKisayolu[] = ["bu_yil", "gecen_yil", "son_30_gun", "son_12_ay"];

/** "Sık" bölümü: sıklık sıralı listenin ilk bu kadarı (§5.2). */
export const SIK_SECENEK_SAYISI = 8;

/** Öneri listesi düz alt-dize ile daralır (cmdk bulanık skoru değil; FieldPicker ile aynı kural). */
function altDizeFiltresi(value: string, search: string): number {
    const q = search.trim().toLocaleLowerCase("tr-TR");
    if (!q) return 1;
    return value.toLocaleLowerCase("tr-TR").includes(q) ? 1 : 0;
}

const ETIKET_CLS = "font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] whitespace-nowrap";
const KUCUK_INPUT_CLS = INPUT_CLS + " h-7 text-[11.5px]";
const KUCUK_SELECT_CLS = SELECT_CLS + " h-7 text-[11.5px]";
const CHECK_CLS = "w-3.5 h-3.5 accent-[var(--brand)] cursor-pointer";

function sayiOku(metin: string): number | null {
    if (metin.trim() === "") return null;
    const n = Number(metin);
    return Number.isFinite(n) ? n : null;
}

/** Sayı ucu kutu metni (null → ""). */
const sayiMetni = (v: number | null) => (v === null ? "" : String(v));

/** "Boş" seçeneği/çipi: kolon `is_null` izin veriyorsa (veriden liste, `liste` tipi, tarih/sayı/metin). */
function bosSecenegiVarMi(kolon: Pick<KatalogKolon, "tip" | "filtrelenebilir" | "oplar">): boolean {
    return kolonOplari(kolon).includes("is_null");
}

/**
 * Şerit kontrolü (§4.1 madde 2 / §4.3 / §5.3 / §7.1): operatör seçici YOK — op kontrolden türetilir.
 * Kontrol bileşeni `oge.sunum` + `durum.kontrol` ikilisinden seçilir: tarih aralığı (alan değiştirici +
 * kısayollar), çoklu seçim (aranabilir açılır: "Sık"/"Tümü"/"Boş", sayı rozetli; `sunum=cipler` görünür
 * çip satırı), metin (öneri varsa cmdk combobox), sayı/para aralığı, mantık Evet/Hayır, var/yok üçlü
 * anahtar, "X yok" kutucuğu. Tarih/sayı/metin kontrolünde girdinin sağında "Boş" toggle çipi (`is_null`,
 * girdiler kilitli; kolon `is_null` izinliyse) — yan kutucuk değil. Mantık boşluğu çipin "…" menüsünden.
 * Arama kutusu (`sunum=arama`) QuickFilters'ta ayrı satırdadır (SearchBox; sanal kolon, boş çipi yok).
 */
export function FilterControl({ oge, kolon, kolonOf, onChange, onHemen, bugun }: FilterControlProps) {
    const d = oge.durum;
    const etiket = kolon.etiket;
    const bosCipi = bosSecenegiVarMi(kolon);
    const bosSayi = bosSayisi(kolon);

    if (d.kontrol === "var_yok") {
        return (
            <div data-testid="filtre-kontrolu" data-alan={d.alan} data-kontrol={d.kontrol} data-sunum={oge.sunum} className="min-w-0">
                <VarYokAnahtari etiket={oge.etiket ?? etiket} durum={d.durum} onChange={durum => onChange({ ...d, durum })} />
            </div>
        );
    }
    if (d.kontrol === "bos_anahtari") {
        return (
            <div data-testid="filtre-kontrolu" data-alan={d.alan} data-kontrol={d.kontrol} data-sunum={oge.sunum} className="min-w-0">
                <BosAnahtari etiket={oge.etiket ?? `${etiket} boş`} acik={d.acik} sayi={bosSayi} onChange={acik => onChange({ ...d, acik })} />
            </div>
        );
    }

    const alanDegistirici = oge.alanSecenekleri.length > 0 && d.kontrol !== "gelismis" ? (
        <select
            aria-label={`${etiket} alanı`}
            value={d.alan}
            onChange={e => onChange({ ...d, alan: e.target.value })}
            className={KUCUK_SELECT_CLS + " w-auto max-w-[180px] font-mono text-[10px] tracking-[0.08em] uppercase"}
        >
            {oge.alanSecenekleri.map(a => (
                <option key={a} value={a}>{kolonOf(a)?.etiket ?? a}</option>
            ))}
        </select>
    ) : (
        <span className={ETIKET_CLS}>{etiket}</span>
    );

    return (
        <div
            data-testid="filtre-kontrolu"
            data-alan={d.alan}
            data-kontrol={d.kontrol}
            data-sunum={oge.sunum}
            className="flex flex-col gap-1 min-w-0"
        >
            <div className="flex items-center justify-between gap-2">
                {alanDegistirici}
            </div>
            <div>
                {d.kontrol === "tarih_araligi" && (
                    <TarihAraligi
                        etiket={etiket}
                        durum={d}
                        bosCipi={bosCipi}
                        bosSayi={bosSayi}
                        onChange={onChange}
                        onHemen={onHemen}
                        bugun={bugun}
                    />
                )}
                {d.kontrol === "sayi_araligi" && (
                    <div className={"grid gap-1 items-center " + (bosCipi ? "grid-cols-[1fr_1fr_auto]" : "grid-cols-2")}>
                        <input
                            type="number"
                            aria-label={`${etiket} en az`}
                            placeholder="en az"
                            value={sayiMetni(d.en_az)}
                            disabled={d.bos}
                            onChange={e => onChange({ ...d, en_az: sayiOku(e.target.value) }, true)}
                            onBlur={onHemen}
                            className={KUCUK_INPUT_CLS}
                        />
                        <input
                            type="number"
                            aria-label={`${etiket} en çok`}
                            placeholder="en çok"
                            value={sayiMetni(d.en_cok)}
                            disabled={d.bos}
                            onChange={e => onChange({ ...d, en_cok: sayiOku(e.target.value) }, true)}
                            onBlur={onHemen}
                            className={KUCUK_INPUT_CLS}
                        />
                        {bosCipi && <BosCipi etiket={etiket} acik={d.bos} sayi={bosSayi} onChange={bos => onChange({ ...d, bos })} />}
                    </div>
                )}
                {d.kontrol === "coklu_secim" && (
                    oge.sunum === "cipler" ? (
                        <ChipSelect
                            etiket={etiket}
                            kolon={kolon}
                            secili={d.secili}
                            bosSecenegi={bosSecenegiVarMi(kolon)}
                            onChange={secili => onChange({ ...d, secili })}
                        />
                    ) : (
                        <CokluSecim
                            etiket={etiket}
                            kolon={kolon}
                            secili={d.secili}
                            bosSecenegi={bosSecenegiVarMi(kolon)}
                            onChange={secili => onChange({ ...d, secili })}
                        />
                    )
                )}
                {d.kontrol === "metin_icerir" && (
                    <div className={"grid gap-1 items-center " + (bosCipi ? "grid-cols-[1fr_auto]" : "grid-cols-1")}>
                        {kolon.oneriler && kolon.oneriler.length > 0 ? (
                            <MetinCombobox
                                etiket={etiket}
                                oneriler={kolon.oneriler}
                                kesik={kolon.oneri_kesik}
                                metin={d.metin}
                                disabled={d.bos}
                                onYaz={metin => onChange({ ...d, metin, tam: false }, true)}
                                onSec={metin => onChange({ ...d, metin, tam: kolon.oplar.includes("eq") })}
                                onHemen={onHemen}
                            />
                        ) : (
                            <input
                                type="text"
                                aria-label={`${etiket} içerir`}
                                placeholder="içerir…"
                                value={d.metin}
                                disabled={d.bos}
                                onChange={e => onChange({ ...d, metin: e.target.value, tam: false }, true)}
                                onBlur={onHemen}
                                className={KUCUK_INPUT_CLS}
                            />
                        )}
                        {bosCipi && <BosCipi etiket={etiket} acik={d.bos} sayi={bosSayi} onChange={bos => onChange({ ...d, bos })} />}
                    </div>
                )}
                {d.kontrol === "mantik" && (
                    <select
                        aria-label={`${etiket} değeri`}
                        value={d.deger === null ? "" : String(d.deger)}
                        onChange={e => onChange({ ...d, deger: e.target.value === "" ? null : e.target.value === "true" })}
                        className={KUCUK_SELECT_CLS}
                    >
                        <option value="">Hepsi</option>
                        <option value="true">Evet</option>
                        <option value="false">Hayır</option>
                    </select>
                )}
                {d.kontrol === "gelismis" && (
                    <GelismisDeger
                        etiket={etiket}
                        kolon={kolon}
                        durum={d}
                        onChange={onChange}
                        onHemen={onHemen}
                    />
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------

type TarihAraligiProps = {
    etiket: string;
    durum: Extract<KontrolDurumu, { kontrol: "tarih_araligi" }>;
    /** Kolon `is_null` izinli → sağda "Boş" çipi. */
    bosCipi: boolean;
    bosSayi: number | null;
    onChange: (durum: KontrolDurumu, gecikmeli?: boolean) => void;
    onHemen: () => void;
    bugun?: () => Date;
};

function TarihAraligi({ etiket, durum: d, bosCipi, bosSayi, onChange, onHemen, bugun }: TarihAraligiProps) {
    const kisayolSec = (ad: string) => {
        if (!ad) return;
        const [baslangic, bitis] = tarihKisayolu(ad as TarihKisayolu, bugun ? bugun() : new Date());
        onChange({ ...d, baslangic, bitis });
    };
    return (
        <div className={"grid gap-1 items-center " + (bosCipi ? "grid-cols-[1fr_1fr_auto_auto]" : "grid-cols-[1fr_1fr_auto]")}>
            <input
                type="date"
                aria-label={`${etiket} başlangıç`}
                value={d.baslangic}
                disabled={d.bos}
                onChange={e => onChange({ ...d, baslangic: e.target.value }, true)}
                onBlur={onHemen}
                className={KUCUK_INPUT_CLS}
            />
            <input
                type="date"
                aria-label={`${etiket} bitiş`}
                value={d.bitis}
                disabled={d.bos}
                onChange={e => onChange({ ...d, bitis: e.target.value }, true)}
                onBlur={onHemen}
                className={KUCUK_INPUT_CLS}
            />
            <select
                aria-label={`${etiket} kısayol`}
                value=""
                disabled={d.bos}
                onChange={e => kisayolSec(e.target.value)}
                className={KUCUK_SELECT_CLS + " w-auto"}
                title="Hazır aralık"
            >
                <option value="">Kısayol…</option>
                {KISAYOLLAR.map(k => <option key={k} value={k}>{TARIH_KISAYOL_ETIKETLERI[k]}</option>)}
            </select>
            {bosCipi && <BosCipi etiket={etiket} acik={d.bos} sayi={bosSayi} onChange={bos => onChange({ ...d, bos })} />}
        </div>
    );
}

// ---------------------------------------------------------------------------

type CokluSecimProps = {
    etiket: string;
    kolon: Pick<KatalogKolon, "secenekler" | "secenek_etiketleri" | "secenek_sayilari" | "bos_sayisi">;
    secili: Secim[];
    /** Listenin sonunda "Boş" seçeneği (ayırıcıyla). */
    bosSecenegi: boolean;
    onChange: (secili: Secim[]) => void;
};

type ListeBolumu = { ad: "Sık" | "Tümü" | null; secenekler: Secim[] };

/**
 * Aranabilir çoklu seçim (§5.1 madde 3-4 / §5.3 / §7.1): açılırda arama kutusu; sorgu boşken "Sık"
 * (katalog sıklık sırasında ilk 8 — sıfır kayıtlılar yalnız "Tümü"de) + "Tümü" bölümleri; her satırda
 * sayı rozeti (`secenek_sayilari`), sıfırlılar soluk ama seçilebilir (sıra katalogdan: sayıya göre azalan,
 * sıfırlılar sonda — istemci yeniden sıralamaz); en altta ayırıcıyla italik **Boş** satırı (rozet
 * `bos_sayisi`). Yazdıkça Tümü daralır (etiket ve ham kod üzerinde, tr-TR). Seçilenler düğmenin altında
 * çip (× ile düşer). Etiketli gösterim, HAM değer. Klavye: ↑↓ öğe gezer, Enter işaretler, Esc kapatır
 * (`useDisariTiklama`). Serbest metin girişi YOK.
 */
export function CokluSecim({ etiket, kolon, secili, bosSecenegi, onChange }: CokluSecimProps) {
    const [acik, setAcik] = useState(false);
    const [arama, setArama] = useState("");
    const [aktif, setAktif] = useState(0);
    const ref = useDisariTiklama<HTMLDivElement>(acik, () => setAcik(false));
    const listeRef = useRef<HTMLDivElement>(null);

    const secenekler = useMemo<Secim[]>(
        () => [...(kolon.secenekler ?? []), ...(bosSecenegi ? [null] : [])],
        [kolon.secenekler, bosSecenegi],
    );

    const bolumler = useMemo<ListeBolumu[]>(() => {
        const q = arama.trim().toLocaleLowerCase("tr-TR");
        if (q) {
            const uyan = secenekler.filter(s =>
                secenekEtiketi(kolon, s).toLocaleLowerCase("tr-TR").includes(q)
                || (s !== null && s.toLocaleLowerCase("tr-TR").includes(q)),
            );
            return [{ ad: null, secenekler: uyan }];
        }
        const dolu = secenekler.filter((s): s is string => s !== null);
        if (dolu.length <= SIK_SECENEK_SAYISI) return [{ ad: null, secenekler }];
        // "Sık": katalog sırasında sıfır kayıtlı olmayan ilk 8 (0'lılar yalnız "Tümü"de).
        const sik = dolu.filter(s => secenekSayisi(kolon, s) !== 0).slice(0, SIK_SECENEK_SAYISI);
        return [
            { ad: "Sık", secenekler: sik },
            { ad: "Tümü", secenekler },
        ];
    }, [secenekler, arama, kolon]);

    // Klavye gezintisi için düz görünen liste (bölüm sırasıyla).
    const duz = useMemo(() => bolumler.flatMap(b => b.secenekler), [bolumler]);

    useEffect(() => {
        setAktif(0);
    }, [arama, acik]);

    useEffect(() => {
        if (!acik) return;
        const el = listeRef.current?.querySelector<HTMLElement>("[data-aktif='true']");
        el?.scrollIntoView?.({ block: "nearest" });
    }, [aktif, acik]);

    const toggle = (s: Secim) =>
        onChange(secili.includes(s) ? secili.filter(x => x !== s) : [...secili, s]);

    const ozet = secili.length === 0
        ? "Hepsi"
        : secili.length <= 2 ? secili.map(s => secenekEtiketi(kolon, s)).join(", ") : `${secili.length} seçili`;

    const tus = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "ArrowDown") {
            e.preventDefault();
            setAktif(i => (duz.length === 0 ? 0 : Math.min(i + 1, duz.length - 1)));
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setAktif(i => Math.max(i - 1, 0));
        } else if (e.key === "Enter") {
            e.preventDefault();
            if (duz.length > 0) toggle(duz[Math.min(aktif, duz.length - 1)]);
        }
    };

    let sira = -1;

    return (
        <div ref={ref} className="relative flex flex-col gap-1">
            <button
                type="button"
                aria-label={`${etiket} seç`}
                aria-expanded={acik}
                aria-haspopup="listbox"
                onClick={() => setAcik(v => !v)}
                className={KUCUK_SELECT_CLS + " text-left truncate " + (secili.length > 0 ? "text-[var(--fg)]" : "text-[var(--fg-subtle)]")}
            >
                {ozet}
            </button>
            {secili.length > 0 && (
                <div data-testid="secili-cipler" className="flex flex-wrap gap-1">
                    {secili.map(s => (
                        <span
                            key={s ?? " bos"}
                            data-deger={s ?? ""}
                            className={"inline-flex items-center gap-0.5 pl-1.5 pr-0.5 py-0.5 text-[11px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--fg)] rounded-[3px]" + (s === null ? " italic" : "")}
                        >
                            {secenekEtiketi(kolon, s)}
                            <button
                                type="button"
                                aria-label={`${etiket}: ${secenekEtiketi(kolon, s)} kaldır`}
                                onClick={() => toggle(s)}
                                className="w-4 h-4 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)]"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </span>
                    ))}
                </div>
            )}
            {acik && (
                <div className="absolute top-full left-0 z-30 mt-1 min-w-full w-max max-w-[320px] border border-[var(--border)] bg-[var(--bg-elevated)] shadow-md flex flex-col">
                    <input
                        type="search"
                        aria-label={`${etiket} ara`}
                        placeholder="Ara…"
                        autoFocus
                        value={arama}
                        onChange={e => setArama(e.target.value)}
                        onKeyDown={tus}
                        className={KUCUK_INPUT_CLS + " rounded-none border-0 border-b border-[var(--border)] [&::-webkit-search-cancel-button]:hidden"}
                    />
                    <div
                        ref={listeRef}
                        role="listbox"
                        aria-label={`${etiket} seçenekleri`}
                        aria-multiselectable="true"
                        className="max-h-56 overflow-y-auto p-1 flex flex-col"
                    >
                        {duz.length === 0 && (
                            <span className="px-2 py-1 text-[11px] text-[var(--fg-subtle)]">
                                {secenekler.length === 0 ? "Seçenek listesi boş." : "Aramaya uyan seçenek yok."}
                            </span>
                        )}
                        {bolumler.map(b => (
                            <div key={b.ad ?? "liste"} data-bolum={b.ad ?? undefined} className="flex flex-col">
                                {b.ad && (
                                    <span className="px-2 pt-1.5 pb-0.5 font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">{b.ad}</span>
                                )}
                                {b.secenekler.map(s => {
                                    sira += 1;
                                    const i = sira;
                                    const metin = secenekEtiketi(kolon, s);
                                    const isaretli = secili.includes(s);
                                    const sayi = secenekSayisi(kolon, s);
                                    return (
                                        <label
                                            key={s ?? " bos"}
                                            role="option"
                                            aria-selected={isaretli}
                                            data-aktif={i === aktif ? "true" : undefined}
                                            data-deger={s ?? ""}
                                            data-sifir={sayi === 0 ? "true" : undefined}
                                            onMouseEnter={() => setAktif(i)}
                                            className={[
                                                "flex items-center gap-2 px-2 py-1 text-[12px] text-[var(--fg)] cursor-pointer whitespace-nowrap rounded-[2px]",
                                                i === aktif ? "bg-[var(--bg)]" : "hover:bg-[var(--bg)]",
                                                s === null ? "italic text-[var(--fg-muted)] mt-1 pt-1.5 border-t border-[var(--border)] rounded-t-none" : "",
                                                sayi === 0 ? "opacity-60" : "",
                                            ].join(" ")}
                                        >
                                            <input
                                                type="checkbox"
                                                aria-label={`${etiket}: ${metin}`}
                                                checked={isaretli}
                                                onChange={() => toggle(s)}
                                                className={CHECK_CLS}
                                            />
                                            <span className="flex-1">{metin}</span>
                                            <SayiRozeti sayi={sayi} />
                                        </label>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------

type MetinComboboxProps = {
    etiket: string;
    oneriler: string[];
    kesik: boolean;
    metin: string;
    /** "Boş" çipi açık: girdi kilitli, liste açılmaz. */
    disabled?: boolean;
    onYaz: (metin: string) => void;
    onSec: (metin: string) => void;
    onHemen: () => void;
};

/**
 * Öneri listeli metin: cmdk `Command` — yazdıkça daralır; listeden seçim `onSec` (→ `eq`, kolon
 * `oplar`ında varsa), serbest yazım `onYaz` (→ `contains`). Liste yalnız odaktayken açılır.
 */
function MetinCombobox({ etiket, oneriler, kesik, metin, disabled = false, onYaz, onSec, onHemen }: MetinComboboxProps) {
    const [acik, setAcik] = useState(false);
    const ref = useDisariTiklama<HTMLDivElement>(acik, () => setAcik(false));

    return (
        <div ref={ref} className="relative">
            <Command
                shouldFilter
                filter={altDizeFiltresi}
                loop
                className="rounded-[3px] bg-transparent text-[var(--fg)] overflow-visible"
                onKeyDown={e => { if (e.key === "Escape") setAcik(false); }}
            >
                <CommandInput
                    aria-label={`${etiket} içerir`}
                    placeholder="içerir…"
                    value={metin}
                    disabled={disabled}
                    onValueChange={v => { onYaz(v); setAcik(true); }}
                    onFocus={() => { if (!disabled) setAcik(true); }}
                    onBlur={onHemen}
                    className="h-7 py-0 text-[11.5px] placeholder:text-[var(--fg-subtle)]"
                />
                {acik && !disabled && (
                    // cmdk List kendi aria-label'ını basar ("Suggestions"); testler `[cmdk-list]` ile bulur.
                    <CommandList className="absolute left-0 right-0 z-30 mt-1 max-h-56 border border-[var(--border)] bg-[var(--bg-elevated)] shadow-md">
                        <CommandEmpty className="py-2 text-[11px] text-[var(--fg-subtle)]">
                            Öneri yok — yazdığınız metin "içerir" olarak süzülür.
                        </CommandEmpty>
                        <CommandGroup heading={kesik ? "İlk 300 değer (liste kesildi)" : undefined}>
                            {oneriler.map(o => (
                                <CommandItem
                                    key={o}
                                    value={o}
                                    onSelect={() => { onSec(o); setAcik(false); }}
                                    className="text-[12px] py-1"
                                >
                                    {o}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                )}
            </Command>
        </div>
    );
}

// ---------------------------------------------------------------------------

type GelismisDegerProps = {
    etiket: string;
    kolon: KatalogKolon;
    durum: Extract<KontrolDurumu, { kontrol: "gelismis" }>;
    onChange: (durum: KontrolDurumu, gecikmeli?: boolean) => void;
    onHemen: () => void;
};

const SAYISAL: ReadonlySet<KolonTipi> = new Set<KolonTipi>(["sayi", "para"]);

function girdiTipi(tip: KolonTipi): "date" | "number" | "text" {
    if (tip === "tarih") return "date";
    if (SAYISAL.has(tip)) return "number";
    return "text";
}

/** Girdi metni → sözleşme değeri (sayı number, boş → ""). */
function metniDegereCevir(tip: KolonTipi, metin: string): string | number {
    if (metin === "") return "";
    if (SAYISAL.has(tip)) {
        const n = Number(metin);
        return Number.isFinite(n) ? n : "";
    }
    return metin;
}

function tekilMetin(v: FiltreDeger | undefined): string {
    if (v === undefined || v === null || typeof v === "boolean" || Array.isArray(v)) return "";
    return String(v);
}

function ikiliUc(v: FiltreDeger | undefined, i: 0 | 1): string | number {
    if (!Array.isArray(v)) return "";
    const x = v[i];
    return x === undefined || x === null ? "" : x;
}

/** `in` listesi → seçim listesi (`null` "Boş" korunur, sayı metne çevrilir). */
function listeSecimleri(v: FiltreDeger | undefined): Secim[] {
    if (!Array.isArray(v)) return [];
    return v.map(x => (x === null ? null : String(x)));
}

/**
 * Gelişmiş çipin değer girdisi: op çipin "…" menüsünden gelir, burada yalnız değer düzenlenir
 * (tekil: tipe göre metin/sayı/tarih/liste seçimi/Evet-Hayır; `in` seçenekli kolonda çoklu seçim,
 * metinde virgülle; `between` iki kutu; `is_null`/`not_null` değersiz).
 */
function GelismisDeger({ etiket, kolon, durum: d, onChange, onHemen }: GelismisDegerProps) {
    const sekil = opDegerSekli(d.op);
    const tip = kolon.tip;
    const degerAyarla = (deger: FiltreDeger | undefined, gecikmeli?: boolean) =>
        onChange(deger === undefined ? { kontrol: "gelismis", alan: d.alan, op: d.op } : { ...d, deger }, gecikmeli);

    const opRozeti = (
        <span className="font-mono text-[9.5px] tracking-[0.08em] uppercase text-[var(--brand)] whitespace-nowrap">
            {OP_ETIKETLERI[d.op]}
        </span>
    );

    if (sekil === "yok") {
        return <div className="h-7 flex items-center">{opRozeti}</div>;
    }

    if (sekil === "ikili") {
        const ikiliAyarla = (i: 0 | 1, metin: string) => {
            const mevcut: (string | number)[] = [ikiliUc(d.deger, 0), ikiliUc(d.deger, 1)];
            mevcut[i] = metniDegereCevir(tip, metin);
            degerAyarla(mevcut, true);
        };
        return (
            <div className="grid grid-cols-[auto_1fr_1fr] gap-1 items-center">
                {opRozeti}
                <input type={girdiTipi(tip)} aria-label={`${etiket} başlangıç`} value={String(ikiliUc(d.deger, 0))}
                    onChange={e => ikiliAyarla(0, e.target.value)} onBlur={onHemen} className={KUCUK_INPUT_CLS} />
                <input type={girdiTipi(tip)} aria-label={`${etiket} bitiş`} value={String(ikiliUc(d.deger, 1))}
                    onChange={e => ikiliAyarla(1, e.target.value)} onBlur={onHemen} className={KUCUK_INPUT_CLS} />
            </div>
        );
    }

    if (sekil === "liste") {
        if (kolon.secenekler && kolon.secenekler.length > 0) {
            return (
                <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                    {opRozeti}
                    <CokluSecim etiket={etiket} kolon={kolon} secili={listeSecimleri(d.deger)} bosSecenegi={bosSecenegiVarMi(kolon)}
                        onChange={liste => degerAyarla(liste)} />
                </div>
            );
        }
        const metin = listeSecimleri(d.deger).filter((x): x is string => x !== null).join(", ");
        return (
            <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                {opRozeti}
                <input
                    type="text"
                    aria-label={`${etiket} değerleri (virgülle)`}
                    placeholder="değer1, değer2, …"
                    defaultValue={metin}
                    onChange={e => degerAyarla(e.target.value.split(",").map(s => s.trim()).filter(Boolean), true)}
                    onBlur={onHemen}
                    className={KUCUK_INPUT_CLS}
                />
            </div>
        );
    }

    // tekil
    if (tip === "mantik") {
        return (
            <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                {opRozeti}
                <select aria-label={`${etiket} değeri`} value={typeof d.deger === "boolean" ? String(d.deger) : ""}
                    onChange={e => degerAyarla(e.target.value === "" ? undefined : e.target.value === "true")} className={KUCUK_SELECT_CLS}>
                    <option value="">Seçiniz</option>
                    <option value="true">Evet</option>
                    <option value="false">Hayır</option>
                </select>
            </div>
        );
    }
    if (kolon.secenekler && kolon.secenekler.length > 0) {
        return (
            <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                {opRozeti}
                <select aria-label={`${etiket} değeri`} value={tekilMetin(d.deger)}
                    onChange={e => degerAyarla(e.target.value === "" ? undefined : e.target.value)} className={KUCUK_SELECT_CLS}>
                    <option value="">Seçiniz</option>
                    {kolon.secenekler.map(s => <option key={s} value={s}>{secenekEtiketi(kolon, s)}</option>)}
                </select>
            </div>
        );
    }
    return (
        <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
            {opRozeti}
            <input
                type={girdiTipi(tip)}
                aria-label={`${etiket} değeri`}
                value={tekilMetin(d.deger)}
                onChange={e => {
                    const v = metniDegereCevir(tip, e.target.value);
                    degerAyarla(v === "" ? undefined : v, true);
                }}
                onBlur={onHemen}
                className={KUCUK_INPUT_CLS}
            />
        </div>
    );
}
