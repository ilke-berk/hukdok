import { Search, X } from "lucide-react";
import { INPUT_CLS } from "./ui";

type SearchBoxProps = {
    /** Kolon etiketi ("Ara") — erişilebilirlik adı. */
    etiket: string;
    /** Katalog `aciklama`sından; yoksa genel metin. */
    placeholder?: string | null;
    metin: string;
    /** Yazım — sayfa 600 ms bekletir (`gecikmeli`). */
    onYaz: (metin: string) => void;
    /** × — anında boşalır. */
    onTemizle: () => void;
    /** Odak çıkışı — bekleyen gecikmeli önizleme hemen istenir. */
    onHemen: () => void;
};

const VARSAYILAN_PLACEHOLDER = "Ara…";

/**
 * Şeridin en üstündeki tek arama kutusu (§5.1 madde 1 / §5.3 `sunum=arama`): sanal `arama` kolonuna
 * `contains` gönderir (sunucu birden çok kolonda "içerir" uygular). Tam genişlik, büyüteç + temizle ×;
 * gecikme sayfanın mevcut `gecikmeli` yoludur (ayrı zamanlayıcı yok).
 */
export function SearchBox({ etiket, placeholder, metin, onYaz, onTemizle, onHemen }: SearchBoxProps) {
    return (
        <div data-testid="arama-kutusu" className="relative w-full">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fg-subtle)] pointer-events-none" />
            <input
                type="search"
                aria-label={etiket}
                placeholder={placeholder || VARSAYILAN_PLACEHOLDER}
                value={metin}
                onChange={e => onYaz(e.target.value)}
                onBlur={onHemen}
                className={INPUT_CLS + " h-9 pl-9 pr-9 text-[13px] [&::-webkit-search-cancel-button]:hidden"}
            />
            {metin !== "" && (
                <button
                    type="button"
                    aria-label={`${etiket} temizle`}
                    title="Aramayı temizle"
                    onClick={onTemizle}
                    className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] rounded-[2px]"
                >
                    <X className="w-3.5 h-3.5" />
                </button>
            )}
        </div>
    );
}
