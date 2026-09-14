// @vitest-environment jsdom
// G188 (F6, KVKK) — Yetki Belgesi avukat önbelleği:
// - TC kimlik no HİÇBİR depoya yazılmaz (lib/formDraft.ts:10-11 kuralı);
// - sicil no + ad sessionStorage'da sürümlü `:v1` anahtarında tutulur;
// - depo yazımı fırlatınca (kota/politika) akış durmaz, 3. adım açılır;
// - eski sürümsüz KALICI localStorage anahtarı modal açılınca silinir, içindeki TC okunmaz.
// Adımlar gerçek bileşen akışıyla geçilir; Radix/cmdk katmanı print testindeki gibi düzleştirilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const LAWYERS = vi.hoisted(() => [
  { name: "Deniz Kaya", tc_no: "12345678901", sicil_no: "4567", address: "Büro Cad. No:1 Kadıköy" },
  { name: "Ali Vural", tc_no: "", sicil_no: "", address: "" },
]);
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => ({ lawyers: LAWYERS }) }));

vi.mock("@/hooks/useAuthRequest", () => ({ useAuthRequest: () => ({ authRequest: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

type Kids = { children?: unknown };

vi.mock("@/components/ui/dialog", () => {
  const duz = ({ children }: Kids) => <div>{children as never}</div>;
  return {
    Dialog: ({ open, children }: { open: boolean } & Kids) => (open ? <>{children as never}</> : null),
    DialogContent: duz,
    DialogHeader: duz,
    DialogTitle: duz,
    DialogDescription: duz,
  };
});
vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: Kids) => <>{children as never}</>,
  PopoverTrigger: ({ children }: Kids) => <>{children as never}</>,
  PopoverContent: ({ children }: Kids) => <div>{children as never}</div>,
}));
vi.mock("@/components/ui/command", () => {
  const duz = ({ children }: Kids) => <div>{children as never}</div>;
  return {
    Command: duz,
    CommandInput: () => null,
    CommandList: duz,
    CommandEmpty: duz,
    CommandGroup: duz,
    CommandItem: ({ children, onSelect, value }: Kids & { onSelect?: () => void; value?: string }) => (
      <button type="button" data-cmd-item={value} onClick={onSelect}>{children as never}</button>
    ),
  };
});

import { YetkiBelgesiModal } from "./YetkiBelgesiModal";
import type { Client } from "@/pages/ClientList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ESKI_KALICI_ANAHTAR = "yetki_belgesi_avukat_cache";
const OTURUM_ANAHTARI = "yetki_belgesi_avukat_cache:v1";

const VEREN_TC = "12345678901";
const YETKILI_TC = "11122233344";
const YETKILI_SICIL = "999";

const MUVEKKIL: Client = {
  id: 7,
  name: "Ayşe Yılmaz",
  tc_no: "98765432109",
  address: "Bağdat Cad. No:5",
  il: "İstanbul",
  noterlik: "Kadıköy 3. Noterliği",
  vekaletname_tarihi: "2025-01-27",
  yevmiye_no: "1234",
};

/** Deponun tüm anahtar+değer metni — TC'nin HİÇBİR anahtarda geçmediğini denetlemek için. */
function depoDokumu(depo: Storage): string {
  const parcalar: string[] = [];
  for (let i = 0; i < depo.length; i++) {
    const anahtar = depo.key(i)!;
    parcalar.push(`${anahtar}=${depo.getItem(anahtar)}`);
  }
  return parcalar.join("\n");
}

describe("YetkiBelgesiModal — avukat önbelleği KVKK (G188 · F6)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  function buton(metin: string): HTMLButtonElement {
    const b = Array.from(container.querySelectorAll("button"))
      .find((x) => x.textContent?.trim() === metin);
    if (!b) throw new Error(`'${metin}' butonu bulunamadı`);
    return b;
  }

  function cmdItem(value: string, liste: "veren" | "yetkili"): HTMLButtonElement {
    const hepsi = Array.from(container.querySelectorAll<HTMLButtonElement>(`button[data-cmd-item="${value}"]`));
    const b = liste === "veren" ? hepsi[0] : hepsi[hepsi.length - 1];
    if (!b || (liste === "yetkili" && hepsi.length < 2)) throw new Error(`'${value}' seçeneği (${liste}) bulunamadı`);
    return b;
  }

  /** Etiket metnine göre alanın input'u; `sira` aynı etiketli alanlar arasındaki sıra (0 = veren). */
  function alan(etiket: string, sira: number): HTMLInputElement {
    const etiketler = Array.from(container.querySelectorAll("label"))
      .filter((l) => l.textContent?.replace("*", "").trim() === etiket);
    const input = etiketler[sira]?.parentElement?.querySelector("input");
    if (!input) throw new Error(`'${etiket}' alanı (${sira}) bulunamadı`);
    return input;
  }

  async function yaz(input: HTMLInputElement, deger: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => {
      setter.call(input, deger);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  async function ac() {
    root = createRoot(container);
    await act(async () => {
      root!.render(<YetkiBelgesiModal open onClose={() => {}} client={MUVEKKIL} />);
    });
  }

  /** Adım 1: veren Deniz Kaya + yetkili Ali Vural → adım 2. */
  async function adim2yeGit() {
    await ac();
    await act(async () => { cmdItem("Deniz Kaya", "veren").click(); });
    await act(async () => { cmdItem("Ali Vural", "yetkili").click(); });
    await act(async () => { buton("Devam").click(); });
    expect(container.textContent).toContain("Veren Avukat · Detayları");
  }

  it("3. adıma geçince TC hiçbir depoda yok; sicil+ad sessionStorage :v1 anahtarında", async () => {
    await adim2yeGit();
    await yaz(alan("T.C. Kimlik No", 1), YETKILI_TC);
    await yaz(alan("Sicil No", 1), YETKILI_SICIL);
    expect(alan("T.C. Kimlik No", 1).value).toBe(YETKILI_TC);

    await act(async () => { buton("Devam").click(); });
    expect(container.textContent).toContain("YETKİ BELGESİ VEREN AVUKAT");

    for (const depo of [localStorage, sessionStorage]) {
      const dokum = depoDokumu(depo);
      expect(dokum).not.toContain(VEREN_TC);
      expect(dokum).not.toContain(YETKILI_TC);
    }
    expect(localStorage.length).toBe(0);

    const onbellek = JSON.parse(sessionStorage.getItem(OTURUM_ANAHTARI) || "null");
    expect(onbellek).toEqual({
      "DENİZ KAYA": { ad: "Deniz Kaya", sicil: "4567" },
      "ALİ VURAL": { ad: "Ali Vural", sicil: YETKILI_SICIL },
    });
  });

  it("depo setItem fırlatınca (kota/politika) akış durmaz, 3. adım açılır", async () => {
    await adim2yeGit();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Kota doldu", "QuotaExceededError");
    });

    await act(async () => { buton("Devam").click(); });

    expect(container.textContent).toContain("YETKİ BELGESİ VEREN AVUKAT");
  });

  it("depo okuması da fırlatınca modal açılır ve 3. adıma kadar ilerler", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Depo erişimi engellendi", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("Depo erişimi engellendi", "SecurityError");
    });

    await adim2yeGit();
    await act(async () => { buton("Devam").click(); });

    expect(container.textContent).toContain("YETKİ BELGESİ VEREN AVUKAT");
  });

  it("eski sürümsüz kalıcı localStorage anahtarı modal açılınca silinir, içindeki TC okunmaz", async () => {
    localStorage.setItem(
      ESKI_KALICI_ANAHTAR,
      JSON.stringify({ "ALİ VURAL": { tc: "55566677788", sicil: "888" } }),
    );

    await ac();
    expect(localStorage.getItem(ESKI_KALICI_ANAHTAR)).toBeNull();

    await act(async () => { cmdItem("Deniz Kaya", "veren").click(); });
    await act(async () => { cmdItem("Ali Vural", "yetkili").click(); });
    await act(async () => { buton("Devam").click(); });
    expect(alan("T.C. Kimlik No", 1).value).toBe("");
    expect(alan("Sicil No", 1).value).toBe("");
  });

  it("oturum önbelleğindeki sicil no config'de boş olan avukata doldurulur; TC doldurulmaz", async () => {
    sessionStorage.setItem(OTURUM_ANAHTARI, JSON.stringify({ "ALİ VURAL": { ad: "Ali Vural", sicil: "777" } }));

    await adim2yeGit();

    expect(alan("Sicil No", 1).value).toBe("777");
    expect(alan("T.C. Kimlik No", 1).value).toBe("");
  });

  it("modal kapalıyken eski anahtara dokunulmaz; açılınca silinir", async () => {
    localStorage.setItem(ESKI_KALICI_ANAHTAR, JSON.stringify({ "DENİZ KAYA": { tc: VEREN_TC, sicil: "4567" } }));
    root = createRoot(container);
    await act(async () => {
      root!.render(<YetkiBelgesiModal open={false} onClose={() => {}} client={MUVEKKIL} />);
    });
    expect(localStorage.getItem(ESKI_KALICI_ANAHTAR)).not.toBeNull();

    await act(async () => {
      root!.render(<YetkiBelgesiModal open onClose={() => {}} client={MUVEKKIL} />);
    });
    expect(localStorage.getItem(ESKI_KALICI_ANAHTAR)).toBeNull();
  });
});
