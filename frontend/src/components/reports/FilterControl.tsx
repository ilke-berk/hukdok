import { useState } from "react";
import type { FiltreDeger, KatalogKolon, KolonTipi, KontrolDurumu, TarihKisayolu } from "@/lib/reports";
import {
    OP_ETIKETLERI, TARIH_KISAYOL_ETIKETLERI, opDegerSekli, tarihKisayolu,
} from "@/lib/reports";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import type { SeritOgesi } from "./builderState";
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

/**
 * Şerit kontrolü (§4.1 madde 2 / §4.3): operatör seçici YOK — op kontrolden türetilir.
 * tarih aralığı (alan değiştirici + kısayollar), çoklu seçim (checkbox'lı açılır), metin
 * (öneri varsa cmdk combobox: seçim → `eq` (kolon `oplar`ında varsa), yazım → `contains`),
 * sayı/para aralığı, mantık Evet/Hayır; her kontrolde "boş olanlar" anahtarı (`is_null`,
 * değer girdisi kilitlenir). Gelişmiş çip (çözülemeyen op) yalnız değer girdisi taşır.
 */
export function FilterControl({ oge, kolon, kolonOf, onChange, onHemen, bugun }: FilterControlProps) {
    const d = oge.durum;
    const etiket = kolon.etiket;

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

    const bosAnahtari = d.kontrol !== "gelismis" ? (
        <label className="inline-flex items-center gap-1 text-[10.5px] text-[var(--fg-subtle)] cursor-pointer select-none whitespace-nowrap">
            <input
                type="checkbox"
                aria-label={`${etiket} boş olanlar`}
                checked={d.bos}
                onChange={e => onChange({ ...d, bos: e.target.checked })}
                className={CHECK_CLS}
            />
            boş olanlar
        </label>
    ) : null;

    const kilitli = d.kontrol !== "gelismis" && d.bos;

    return (
        <div
            data-testid="filtre-kontrolu"
            data-alan={d.alan}
            data-kontrol={d.kontrol}
            className="flex flex-col gap-1 min-w-0"
        >
            <div className="flex items-center justify-between gap-2">
                {alanDegistirici}
                {bosAnahtari}
            </div>
            <div className={kilitli ? "opacity-50" : ""}>
                {d.kontrol === "tarih_araligi" && (
                    <TarihAraligi
                        etiket={etiket}
                        durum={d}
                        kilitli={kilitli}
                        onChange={onChange}
                        onHemen={onHemen}
                        bugun={bugun}
                    />
                )}
                {d.kontrol === "sayi_araligi" && (
                    <div className="grid grid-cols-2 gap-1">
                        <input
                            type="number"
                            aria-label={`${etiket} en az`}
                            placeholder="en az"
                            disabled={kilitli}
                            value={sayiMetni(d.en_az)}
                            onChange={e => onChange({ ...d, en_az: sayiOku(e.target.value) }, true)}
                            onBlur={onHemen}
                            className={KUCUK_INPUT_CLS}
                        />
                        <input
                            type="number"
                            aria-label={`${etiket} en çok`}
                            placeholder="en çok"
                            disabled={kilitli}
                            value={sayiMetni(d.en_cok)}
                            onChange={e => onChange({ ...d, en_cok: sayiOku(e.target.value) }, true)}
                            onBlur={onHemen}
                            className={KUCUK_INPUT_CLS}
                        />
                    </div>
                )}
                {d.kontrol === "coklu_secim" && (
                    <CokluSecim
                        etiket={etiket}
                        secenekler={kolon.secenekler ?? []}
                        secili={d.secili}
                        kilitli={kilitli}
                        onChange={secili => onChange({ ...d, secili })}
                    />
                )}
                {d.kontrol === "metin_icerir" && (
                    kolon.oneriler && kolon.oneriler.length > 0 ? (
                        <MetinCombobox
                            etiket={etiket}
                            oneriler={kolon.oneriler}
                            kesik={kolon.oneri_kesik}
                            metin={d.metin}
                            kilitli={kilitli}
                            onYaz={metin => onChange({ ...d, metin, tam: false }, true)}
                            onSec={metin => onChange({ ...d, metin, tam: kolon.oplar.includes("eq") })}
                            onHemen={onHemen}
                        />
                    ) : (
                        <input
                            type="text"
                            aria-label={`${etiket} içerir`}
                            placeholder="içerir…"
                            disabled={kilitli}
                            value={d.metin}
                            onChange={e => onChange({ ...d, metin: e.target.value, tam: false }, true)}
                            onBlur={onHemen}
                            className={KUCUK_INPUT_CLS}
                        />
                    )
                )}
                {d.kontrol === "mantik" && (
                    <select
                        aria-label={`${etiket} değeri`}
                        disabled={kilitli}
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
    kilitli: boolean;
    onChange: (durum: KontrolDurumu, gecikmeli?: boolean) => void;
    onHemen: () => void;
    bugun?: () => Date;
};

function TarihAraligi({ etiket, durum: d, kilitli, onChange, onHemen, bugun }: TarihAraligiProps) {
    const kisayolSec = (ad: string) => {
        if (!ad) return;
        const [baslangic, bitis] = tarihKisayolu(ad as TarihKisayolu, bugun ? bugun() : new Date());
        onChange({ ...d, baslangic, bitis });
    };
    return (
        <div className="grid grid-cols-[1fr_1fr_auto] gap-1 items-center">
            <input
                type="date"
                aria-label={`${etiket} başlangıç`}
                disabled={kilitli}
                value={d.baslangic}
                onChange={e => onChange({ ...d, baslangic: e.target.value }, true)}
                onBlur={onHemen}
                className={KUCUK_INPUT_CLS}
            />
            <input
                type="date"
                aria-label={`${etiket} bitiş`}
                disabled={kilitli}
                value={d.bitis}
                onChange={e => onChange({ ...d, bitis: e.target.value }, true)}
                onBlur={onHemen}
                className={KUCUK_INPUT_CLS}
            />
            <select
                aria-label={`${etiket} kısayol`}
                disabled={kilitli}
                value=""
                onChange={e => kisayolSec(e.target.value)}
                className={KUCUK_SELECT_CLS + " w-auto"}
                title="Hazır aralık"
            >
                <option value="">Kısayol…</option>
                {KISAYOLLAR.map(k => <option key={k} value={k}>{TARIH_KISAYOL_ETIKETLERI[k]}</option>)}
            </select>
        </div>
    );
}

// ---------------------------------------------------------------------------

type CokluSecimProps = {
    etiket: string;
    secenekler: string[];
    secili: string[];
    kilitli: boolean;
    onChange: (secili: string[]) => void;
};

/** Kapalı liste: checkbox'lı açılır, seçilenler düğmede özetlenir. Serbest metin girişi YOK. */
function CokluSecim({ etiket, secenekler, secili, kilitli, onChange }: CokluSecimProps) {
    const [acik, setAcik] = useState(false);
    const ref = useDisariTiklama<HTMLDivElement>(acik, () => setAcik(false));

    const toggle = (s: string) =>
        onChange(secili.includes(s) ? secili.filter(x => x !== s) : [...secili, s]);

    const ozet = secili.length === 0
        ? "Hepsi"
        : secili.length <= 2 ? secili.join(", ") : `${secili.length} seçili`;

    return (
        <div ref={ref} className="relative">
            <button
                type="button"
                aria-label={`${etiket} seç`}
                aria-expanded={acik}
                aria-haspopup="listbox"
                disabled={kilitli}
                onClick={() => setAcik(v => !v)}
                className={KUCUK_SELECT_CLS + " text-left truncate " + (secili.length > 0 ? "text-[var(--fg)]" : "text-[var(--fg-subtle)]")}
            >
                {ozet}
            </button>
            {acik && (
                <div
                    role="listbox"
                    aria-label={`${etiket} seçenekleri`}
                    aria-multiselectable="true"
                    className="absolute z-30 mt-1 min-w-full max-h-56 overflow-y-auto border border-[var(--border)] bg-[var(--bg-elevated)] shadow-md p-1 flex flex-col"
                >
                    {secenekler.length === 0 && (
                        <span className="px-2 py-1 text-[11px] text-[var(--fg-subtle)]">Seçenek listesi boş.</span>
                    )}
                    {secenekler.map(s => (
                        <label
                            key={s}
                            role="option"
                            aria-selected={secili.includes(s)}
                            className="flex items-center gap-2 px-2 py-1 text-[12px] text-[var(--fg)] hover:bg-[var(--bg)] cursor-pointer whitespace-nowrap"
                        >
                            <input
                                type="checkbox"
                                aria-label={`${etiket}: ${s}`}
                                checked={secili.includes(s)}
                                onChange={() => toggle(s)}
                                className={CHECK_CLS}
                            />
                            {s}
                        </label>
                    ))}
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
    kilitli: boolean;
    onYaz: (metin: string) => void;
    onSec: (metin: string) => void;
    onHemen: () => void;
};

/**
 * Öneri listeli metin: cmdk `Command` — yazdıkça daralır; listeden seçim `onSec` (→ `eq`, kolon
 * `oplar`ında varsa), serbest yazım `onYaz` (→ `contains`). Liste yalnız odaktayken açılır.
 */
function MetinCombobox({ etiket, oneriler, kesik, metin, kilitli, onYaz, onSec, onHemen }: MetinComboboxProps) {
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
                    disabled={kilitli}
                    value={metin}
                    onValueChange={v => { onYaz(v); setAcik(true); }}
                    onFocus={() => setAcik(true)}
                    onBlur={onHemen}
                    className="h-7 py-0 text-[11.5px] placeholder:text-[var(--fg-subtle)]"
                />
                {acik && !kilitli && (
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

/**
 * Gelişmiş çipin değer girdisi: op çipin "…" menüsünden gelir, burada yalnız değer düzenlenir
 * (tekil: tipe göre metin/sayı/tarih/liste seçimi/Evet-Hayır; `in` metinde virgülle; `between` iki kutu;
 * `is_null`/`not_null` değersiz).
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
        if (tip === "liste") {
            const secenekler = kolon.secenekler ?? [];
            const secili = Array.isArray(d.deger) ? d.deger.map(String) : [];
            return (
                <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                    {opRozeti}
                    <CokluSecim etiket={etiket} secenekler={secenekler} secili={secili} kilitli={false}
                        onChange={liste => degerAyarla(liste)} />
                </div>
            );
        }
        const metin = Array.isArray(d.deger) ? d.deger.join(", ") : "";
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
    if (tip === "liste") {
        return (
            <div className="grid grid-cols-[auto_1fr] gap-1 items-center">
                {opRozeti}
                <select aria-label={`${etiket} değeri`} value={tekilMetin(d.deger)}
                    onChange={e => degerAyarla(e.target.value === "" ? undefined : e.target.value)} className={KUCUK_SELECT_CLS}>
                    <option value="">Seçiniz</option>
                    {(kolon.secenekler ?? []).map(s => <option key={s} value={s}>{s}</option>)}
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
