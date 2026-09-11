import { useRef, useState, type KeyboardEvent } from "react";
import { Search } from "lucide-react";
import type { KatalogKolon } from "@/lib/reports";
import { secenekEtiketi, secenekSayisi } from "@/lib/reports";
import { DEGER_LISTESI_MAX, degerAnahtari } from "@/lib/reportsChat";
import { INPUT_CLS } from "./ui";
import { SayiRozeti } from "./ToggleFilter";

type DegerListesiProps = {
    /** `oneriler` ya da `secenekler` taşıyan kolon (liste niyeti çözümü, `listeNiyeti`). */
    kolon: KatalogKolon;
    /** Satır tıklandı — HAM değer (etiket değil). AssistantBar `onFiltreEkle` ile filtreye çevirir ya da girdiye yazar. */
    onSec: (deger: string) => void;
};

/**
 * "Hangi X'ler var" liste balonu (G174, Gemini'siz — değerler zaten katalogda, K6 korunur): kolonun
 * `oneriler` (yoksa `secenekler`) değerleri, üstte arama kutusu (normalize süzme, `degerAnahtari`), en çok
 * 300 satır, `secenek_sayilari` varsa yanında kayıt sayısı rozeti, `oneri_kesik` notu. Liste `role="listbox"`,
 * satırlar `role="option"` düğmeleri: Tab ile girilir, ok tuşları satırlar arasında gezer, Enter/boşluk seçer.
 */
export function DegerListesi({ kolon, onSec }: DegerListesiProps) {
    const [arama, setArama] = useState("");
    const listeRef = useRef<HTMLDivElement>(null);
    const tum: string[] = kolon.oneriler && kolon.oneriler.length > 0 ? kolon.oneriler : (kolon.secenekler ?? []);
    const n = degerAnahtari(arama);
    const gorunen = (n
        ? tum.filter(d => degerAnahtari(d).includes(n) || degerAnahtari(secenekEtiketi(kolon, d)).includes(n))
        : tum
    ).slice(0, DEGER_LISTESI_MAX);
    const kesik = kolon.oneri_kesik === true || tum.length > DEGER_LISTESI_MAX;

    /** Ok tuşları: odak satırlar arasında; Home/End uçlara. Enter/boşluk düğmenin kendi tıklamasıdır. */
    const onTus = (e: KeyboardEvent<HTMLDivElement>) => {
        const satirlar = Array.from(listeRef.current?.querySelectorAll<HTMLButtonElement>("[role='option']") ?? []);
        if (satirlar.length === 0) return;
        const i = satirlar.indexOf(document.activeElement as HTMLButtonElement);
        let hedef: number | null = null;
        if (e.key === "ArrowDown") hedef = Math.min(satirlar.length - 1, i + 1);
        else if (e.key === "ArrowUp") hedef = Math.max(0, i - 1);
        else if (e.key === "Home") hedef = 0;
        else if (e.key === "End") hedef = satirlar.length - 1;
        if (hedef === null) return;
        e.preventDefault();
        satirlar[hedef].focus();
    };

    return (
        <div
            data-testid="deger-listesi"
            data-alan={kolon.anahtar}
            className="w-full min-w-0 max-w-[420px] px-3 py-2 rounded-[4px] border border-[var(--border)] bg-[var(--bg-elevated)] grid gap-2"
        >
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                    {kolon.etiket} · değerler
                </span>
                <span className="text-[11px] text-[var(--fg-subtle)]" data-testid="deger-listesi-sayi">
                    {gorunen.length}{n ? ` / ${tum.length}` : ""} değer
                </span>
            </div>
            <label className="relative block">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)] pointer-events-none" />
                <input
                    type="search"
                    aria-label={`${kolon.etiket} değerlerinde ara`}
                    placeholder="Ara…"
                    value={arama}
                    onChange={e => setArama(e.target.value)}
                    className={INPUT_CLS + " h-8 pl-7 text-[12px] [&::-webkit-search-cancel-button]:hidden"}
                />
            </label>
            <div
                ref={listeRef}
                role="listbox"
                aria-label={`${kolon.etiket} değerleri`}
                onKeyDown={onTus}
                className="max-h-[220px] overflow-y-auto flex flex-col -mx-1"
            >
                {gorunen.length === 0 && (
                    <span className="px-2 py-1 text-[11px] text-[var(--fg-subtle)]" data-testid="deger-listesi-bos">
                        {tum.length === 0 ? "Değer listesi boş." : "Aramaya uyan değer yok."}
                    </span>
                )}
                {gorunen.map(d => {
                    const metin = secenekEtiketi(kolon, d);
                    const sayi = secenekSayisi(kolon, d);
                    return (
                        <button
                            key={d}
                            type="button"
                            role="option"
                            aria-selected={false}
                            data-deger={d}
                            onClick={() => onSec(d)}
                            title={`Filtre olarak ekle: ${metin}`}
                            className="flex items-center gap-2 px-2 py-1 text-left text-[12px] text-[var(--fg)] rounded-[2px] hover:bg-[var(--bg)] focus:outline-none focus:bg-[var(--bg)] focus:ring-1 focus:ring-[var(--brand)]"
                        >
                            <span className="flex-1 min-w-0 truncate">{metin}</span>
                            <SayiRozeti sayi={sayi} />
                        </button>
                    );
                })}
            </div>
            {kesik && (
                <p className="text-[11px] text-[var(--fg-subtle)]" data-testid="deger-listesi-kesik">
                    Liste {DEGER_LISTESI_MAX} değerle kesik — aradığınız değer listede olmayabilir; arama kutusuna yazın ya da mesajda belirtin.
                </p>
            )}
            <p className="text-[11px] text-[var(--fg-subtle)]">Bir değere tıklayın: filtre olarak eklenir.</p>
        </div>
    );
}
