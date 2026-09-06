import { X } from "lucide-react";
import type { FiltreDeger, FiltreOp, KatalogKolon, KolonTipi } from "@/lib/reports";
import { OP_ETIKETLERI, degerSekleUyarla, filtreTamamMi, opDegerSekli, opsForTip } from "@/lib/reports";
import type { FiltreSatiri } from "./builderState";
import { ICON_BTN_CLS, INPUT_CLS, SELECT_CLS } from "./ui";

type FilterRowProps = {
    filtre: FiltreSatiri;
    /** Yalnız `filtrelenebilir` kolonlar (türetilmişler çağıran tarafından elenir). */
    kolonlar: KatalogKolon[];
    onChange: (next: FiltreSatiri) => void;
    onRemove: () => void;
};

const SAYISAL: ReadonlySet<KolonTipi> = new Set<KolonTipi>(["sayi", "para"]);

function girdiTipi(tip: KolonTipi): "date" | "number" | "text" {
    if (tip === "tarih") return "date";
    if (SAYISAL.has(tip)) return "number";
    return "text";
}

/** Girdi metnini kolon tipine göre sözleşme değerine çevirir (sayı → number, boş → ""). */
function metniDegereCevir(tip: KolonTipi, metin: string): string | number {
    if (metin === "") return "";
    if (SAYISAL.has(tip)) {
        const n = Number(metin);
        return Number.isFinite(n) ? n : "";
    }
    return metin;
}

function degerMetni(v: FiltreDeger | undefined): string {
    if (v === undefined || v === null || typeof v === "boolean" || Array.isArray(v)) return "";
    return String(v);
}

function ikiliEleman(v: FiltreDeger | undefined, i: 0 | 1): string {
    if (!Array.isArray(v)) return "";
    const x = v[i];
    return x === undefined || x === null ? "" : String(x);
}

/**
 * Tek filtre satırı: alan (yalnız filtrelenebilir) → op (tipe göre §2.2) → değer girdisi
 * (metin / sayı / tarih / liste; `in` çoklu seçim, `between` iki kutu, `is_null`/`not_null` değersiz).
 */
export function FilterRow({ filtre, kolonlar, onChange, onRemove }: FilterRowProps) {
    const kolon = kolonlar.find(k => k.anahtar === filtre.alan);
    const tip = kolon?.tip;
    const oplar = tip ? opsForTip(tip) : [];
    const sekil = opDegerSekli(filtre.op);
    const tamam = filtreTamamMi(filtre, tip);

    const alanDegisti = (anahtar: string) => {
        const yeni = kolonlar.find(k => k.anahtar === anahtar);
        const ilkOp: FiltreOp = yeni ? opsForTip(yeni.tip)[0] : "eq";
        onChange({ ...filtre, alan: anahtar, op: ilkOp, deger: undefined });
    };

    const opDegisti = (op: FiltreOp) => {
        onChange({ ...filtre, op, deger: degerSekleUyarla(op, filtre.deger) });
    };

    const degerAyarla = (deger: FiltreDeger | undefined) => onChange({ ...filtre, deger });

    const ikiliAyarla = (i: 0 | 1, metin: string) => {
        if (!tip) return;
        const mevcut: (string | number)[] = [ikiliEleman(filtre.deger, 0), ikiliEleman(filtre.deger, 1)];
        mevcut[i] = metniDegereCevir(tip, metin);
        degerAyarla(mevcut);
    };

    const listeToggle = (secenek: string) => {
        const mevcut = Array.isArray(filtre.deger) ? filtre.deger.map(String) : [];
        degerAyarla(mevcut.includes(secenek) ? mevcut.filter(s => s !== secenek) : [...mevcut, secenek]);
    };

    const degerGirdisi = () => {
        if (!tip || sekil === "yok") return null;

        if (tip === "mantik") {
            const v = typeof filtre.deger === "boolean" ? String(filtre.deger) : "";
            return (
                <select
                    aria-label="Değer"
                    value={v}
                    onChange={e => degerAyarla(e.target.value === "" ? undefined : e.target.value === "true")}
                    className={SELECT_CLS}
                >
                    <option value="">Seçiniz</option>
                    <option value="true">Evet</option>
                    <option value="false">Hayır</option>
                </select>
            );
        }

        if (tip === "liste") {
            const secenekler = kolon?.secenekler ?? [];
            if (sekil === "liste") {
                const secili = Array.isArray(filtre.deger) ? filtre.deger.map(String) : [];
                return (
                    <div role="group" aria-label="Değerler" className="flex flex-wrap gap-1">
                        {secenekler.length === 0 && (
                            <span className="text-[11px] text-[var(--fg-subtle)]">Seçenek listesi boş.</span>
                        )}
                        {secenekler.map(s => {
                            const aktif = secili.includes(s);
                            return (
                                <button
                                    key={s}
                                    type="button"
                                    aria-pressed={aktif}
                                    onClick={() => listeToggle(s)}
                                    className={[
                                        "px-2 py-0.5 text-[11px] border rounded-[2px] transition-colors",
                                        aktif
                                            ? "bg-[var(--brand)] text-[var(--brand-fg)] border-[var(--brand)]"
                                            : "bg-transparent text-[var(--fg-muted)] border-[var(--border)] hover:border-[var(--border-strong)]",
                                    ].join(" ")}
                                >
                                    {s}
                                </button>
                            );
                        })}
                    </div>
                );
            }
            return (
                <select
                    aria-label="Değer"
                    value={degerMetni(filtre.deger)}
                    onChange={e => degerAyarla(e.target.value === "" ? undefined : e.target.value)}
                    className={SELECT_CLS}
                >
                    <option value="">Seçiniz</option>
                    {secenekler.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
            );
        }

        const inputType = girdiTipi(tip);

        if (sekil === "ikili") {
            return (
                <div className="grid grid-cols-2 gap-1.5">
                    <input
                        type={inputType}
                        aria-label="Başlangıç"
                        placeholder={tip === "tarih" ? "" : "en az"}
                        value={ikiliEleman(filtre.deger, 0)}
                        onChange={e => ikiliAyarla(0, e.target.value)}
                        className={INPUT_CLS}
                    />
                    <input
                        type={inputType}
                        aria-label="Bitiş"
                        placeholder={tip === "tarih" ? "" : "en çok"}
                        value={ikiliEleman(filtre.deger, 1)}
                        onChange={e => ikiliAyarla(1, e.target.value)}
                        className={INPUT_CLS}
                    />
                </div>
            );
        }

        if (sekil === "liste") {
            // metin `in`: virgülle ayrılmış değerler → list[str]
            const metin = Array.isArray(filtre.deger) ? filtre.deger.join(", ") : "";
            return (
                <input
                    type="text"
                    aria-label="Değerler (virgülle)"
                    placeholder="değer1, değer2, …"
                    defaultValue={metin}
                    onChange={e => degerAyarla(e.target.value.split(",").map(s => s.trim()).filter(Boolean))}
                    className={INPUT_CLS}
                />
            );
        }

        return (
            <input
                type={inputType}
                aria-label="Değer"
                value={degerMetni(filtre.deger)}
                onChange={e => {
                    const v = metniDegereCevir(tip, e.target.value);
                    degerAyarla(v === "" ? undefined : v);
                }}
                className={INPUT_CLS}
            />
        );
    };

    return (
        <div
            data-testid="filtre-satiri"
            className={[
                "grid gap-1.5 p-2 border bg-[var(--bg)]",
                tamam ? "border-[var(--border)]" : "border-[var(--brand)]/40",
            ].join(" ")}
        >
            <div className="grid grid-cols-[1fr_auto] gap-1.5 items-center">
                <select
                    aria-label="Alan"
                    value={filtre.alan}
                    onChange={e => alanDegisti(e.target.value)}
                    className={SELECT_CLS}
                >
                    <option value="">Alan seçiniz</option>
                    {kolonlar.map(k => <option key={k.anahtar} value={k.anahtar}>{k.etiket}</option>)}
                </select>
                <button type="button" className={ICON_BTN_CLS} onClick={onRemove} aria-label="Filtreyi kaldır">
                    <X className="w-3 h-3" />
                </button>
            </div>
            {tip && (
                <select
                    aria-label="Operatör"
                    value={filtre.op}
                    onChange={e => opDegisti(e.target.value as FiltreOp)}
                    className={SELECT_CLS}
                >
                    {oplar.map(op => <option key={op} value={op}>{OP_ETIKETLERI[op]}</option>)}
                </select>
            )}
            {degerGirdisi()}
            {!tamam && filtre.alan && (
                <span className="font-mono text-[9.5px] tracking-[0.08em] text-[var(--brand)]">
                    değer eksik
                </span>
            )}
        </div>
    );
}
