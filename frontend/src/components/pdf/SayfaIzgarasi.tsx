// Sayfa ızgarası (G271): seçili dosyanın sayfaları `SayfaKarti` ile, `@dnd-kit/sortable` (fare + klavye) ile sıralanır.
// Yerel düzen (sıra/döndürme/silme/seçim) `usePdfTezgah`'tadır; "Uygula" tek `sayfa_duzenle` isteği atar (değişiklik yoksa
// kapalı). Izgara `role="list"`; responsive kolonlar 140-240 px.
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, rectSortingStrategy, sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { Check, Loader2, RotateCcw } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import type { Dosya } from "@/types/pdfAraclari";
import { SayfaKarti } from "./SayfaKarti";
import type { SayfaDuzeni } from "./usePdfTezgah";

type Props = {
  dosya: Dosya;
  duzen: SayfaDuzeni;
  degisiklikVar: boolean;
  uygulaniyor: boolean;
  onTasi: (aktifNo: number, hedefNo: number) => void;
  onDondur: (no: number) => void;
  onSil: (no: number) => void;
  onSec: (no: number, secili: boolean, aralik: boolean) => void;
  onHepsiniSec: (hepsi: boolean) => void;
  onSifirla: () => void;
  onUygula: () => void;
};

export function SayfaIzgarasi({ dosya, duzen, degisiklikVar, uygulaniyor, onTasi, onDondur, onSil, onSec, onHepsiniSec, onSifirla, onUygula }: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const sayfaMeta = new Map(dosya.sayfalar.map((s) => [s.no, s]));
  const silinecek = duzen.sayfalar.filter((s) => s.silindi).length;
  const kalan = duzen.sayfalar.length - silinecek;
  const hepsiSecili = kalan > 0 && duzen.secili.length === kalan;

  const surukleBitti = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    onTasi(Number(active.id), Number(over.id));
  };

  return (
    <div data-testid="sayfa-izgarasi" className="flex flex-col gap-3 h-full min-h-0">
      <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
        <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">
          {dosya.sayfa} sayfa · {duzen.secili.length} seçili{silinecek > 0 ? ` · ${silinecek} silinecek` : ""}
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => onHepsiniSec(!hepsiSecili)}
          className="text-[12px] text-[var(--fg-muted)] hover:text-[var(--fg)] underline-offset-2 hover:underline"
        >
          {hepsiSecili ? "Seçimi temizle" : "Tümünü seç"}
        </button>
        <FlowButton size="sm" variant="secondary" disabled={!degisiklikVar || uygulaniyor} onClick={onSifirla} title="Sıra, döndürme ve silmeleri geri al">
          <RotateCcw className="w-3.5 h-3.5" />
          Sıfırla
        </FlowButton>
        <FlowButton size="sm" disabled={!degisiklikVar || uygulaniyor} onClick={onUygula} title="Sıra, döndürme ve silmeleri yeni dosya olarak uygula">
          {uygulaniyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Uygula
        </FlowButton>
      </div>
      <p className="px-3 -mt-1 text-[11px] text-[var(--fg-subtle)]">
        Sürükleyerek sıralayın (tutamaç: boşluk + ok tuşları), döndürün, silin; shift ile aralık seçin. "Uygula" yeni bir dosya üretir, bu dosya listede kalır.
      </p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={surukleBitti}>
        <SortableContext items={duzen.sayfalar.map((s) => s.no)} strategy={rectSortingStrategy}>
          <ul
            role="list"
            aria-label={`${dosya.ad} sayfaları`}
            className="grid gap-2 px-3 pb-3 overflow-y-auto min-h-0 grid-cols-[repeat(auto-fill,minmax(140px,240px))]"
          >
            {duzen.sayfalar.map((s, i) => (
              <SayfaKarti
                key={s.no}
                dosyaId={dosya.id}
                sayfa={sayfaMeta.get(s.no)}
                durum={s}
                sira={i + 1}
                secili={duzen.secili.includes(s.no)}
                onDondur={onDondur}
                onSil={onSil}
                onSec={onSec}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </div>
  );
}
