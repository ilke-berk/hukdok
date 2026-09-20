// @vitest-environment jsdom
// Toplu yükleme tezgâhı — ek bağlama kuralları (tebligat dilekçesi + mazbata aynı e-postada).
// Bir satır başka bir satırın e-posta EKİ olarak işaretlenir: kendi e-postası kapanır ve
// kilitlenir, zincir kurulamaz, ana satırın e-postası kapanınca / satır silinince bağ
// çözülür; "Onaya Geç" payload'ında ana satır ekin File'ını taşır.
// Radix Select/Switch/Popover/Command düz DOM'a indirilir (jsdom).
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, createContext, useContext, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { BulkUploadStartConfig } from "./BulkUploadWorkbench";

const configMock = vi.hoisted(() => ({
  doctypes: [
    { code: "TEBLIGAT______", name: "Tebligat" },
    { code: "DILEKCE_______", name: "Dilekçe" },
  ],
  emailRecipients: [{ name: "Av. Ali", email: "ali@x.com" }],
}));
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => configMock }));
const toastMock = vi.hoisted(() => ({ info: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

type Kids = { children?: ReactNode };

// Select: kök bağlamı (değer, değişim, disabled) → tetikleyici <button aria-label>,
// seçenekler [data-option] olarak tıklanabilir div'ler.
vi.mock("@/components/ui/select", () => {
  type Ctx = { value: string; onValueChange: (v: string) => void; disabled?: boolean };
  const SelectCtx = createContext<Ctx>({ value: "", onValueChange: () => undefined });
  return {
    Select: ({ value, onValueChange, disabled, children }: Kids & Ctx) => (
      <SelectCtx.Provider value={{ value, onValueChange, disabled }}>
        <div data-select="" data-value={value}>{children}</div>
      </SelectCtx.Provider>
    ),
    SelectTrigger: ({ children, ...props }: Kids & Record<string, unknown>) => {
      const ctx = useContext(SelectCtx);
      return <button type="button" data-trigger="" disabled={!!ctx.disabled} {...props}>{children}</button>;
    },
    SelectValue: ({ children }: Kids) => <span data-selected="">{children}</span>,
    SelectContent: ({ children }: Kids) => <div data-content="">{children}</div>,
    SelectItem: ({ value, children }: Kids & { value: string }) => {
      const ctx = useContext(SelectCtx);
      return <div data-option="" data-value={value} onClick={() => ctx.onValueChange(value)}>{children}</div>;
    },
  };
});
vi.mock("@/components/ui/switch", () => ({
  Switch: ({ checked, onCheckedChange, disabled, ...props }: {
    checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean;
  } & Record<string, unknown>) => (
    <input
      type="checkbox"
      role="switch"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onCheckedChange(e.target.checked)}
      {...props}
    />
  ),
}));
vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: Kids) => <>{children}</>,
  PopoverTrigger: ({ children }: Kids) => <>{children}</>,
  PopoverContent: ({ children }: Kids) => <div>{children}</div>,
}));
vi.mock("@/components/ui/command", () => ({
  Command: ({ children }: Kids) => <div>{children}</div>,
  CommandInput: () => null,
  CommandList: ({ children }: Kids) => <div>{children}</div>,
  CommandEmpty: () => null,
  CommandGroup: ({ children }: Kids) => <div>{children}</div>,
  CommandItem: ({ children, onSelect }: Kids & { onSelect?: () => void }) => (
    <div data-item="" onClick={onSelect}>{children}</div>
  ),
}));

import { BulkUploadWorkbench } from "./BulkUploadWorkbench";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DILEKCE = new File(["d"], "dilekce.pdf", { type: "application/pdf" });
const MAZBATA = new File(["m"], "mazbata.pdf", { type: "application/pdf" });
const KARAR = new File(["k"], "karar.pdf", { type: "application/pdf" });
const FILES = [DILEKCE, MAZBATA, KARAR];

describe("BulkUploadWorkbench — ek bağlama", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let onStart: Mock<(config: BulkUploadStartConfig) => void>;

  beforeEach(() => {
    vi.clearAllMocks();
    onStart = vi.fn<(config: BulkUploadStartConfig) => void>();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root!.render(<BulkUploadWorkbench files={FILES} onCancel={() => undefined} onStart={onStart} />));
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
  });

  const byLabel = <T extends Element>(label: string) => container.querySelector(`[aria-label='${label}']`) as T;
  const attachTrigger = (name: string) => byLabel<HTMLButtonElement>(`Ek bağla: ${name}`);
  const attachOptions = (name: string) =>
    Array.from(attachTrigger(name).closest("[data-select]")!.querySelectorAll("[data-option]")).map(o => o.textContent);
  const rowOf = (name: string) => container.querySelector(`[data-testid='bulk-row'][data-file='${name}']`)!;
  const attachValue = (name: string) => rowOf(name).getAttribute("data-attach-to");
  const rowOrder = () => Array.from(container.querySelectorAll("[data-testid='bulk-row']")).map(r => r.getAttribute("data-file"));
  const emailSwitch = (name: string) => byLabel<HTMLInputElement>(`E-posta: ${name}`);
  const click = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  const toggle = (input: HTMLInputElement) => act(() => { input.click(); });

  // mazbata satırını dilekçe satırının eki yap.
  const attachMazbataToDilekce = () => {
    const option = attachTrigger("mazbata.pdf").closest("[data-select]")!
      .querySelector("[data-option][data-value^='0-dilekce.pdf']")!;
    click(option);
  };

  it("aday ana satırlar: kendisi yok, e-postası kapalı satır yok", () => {
    expect(attachOptions("mazbata.pdf")).toEqual(["— Ek değil —", "01 · dilekce.pdf", "03 · karar.pdf"]);

    toggle(emailSwitch("karar.pdf"));
    expect(attachOptions("mazbata.pdf")).toEqual(["— Ek değil —", "01 · dilekce.pdf"]);
  });

  it("bağlanınca ek satır ana belgenin hemen altına girer, e-postası kapanır ve kilitlenir; ana satır +1 ek gösterir", () => {
    expect(rowOrder()).toEqual(["dilekce.pdf", "mazbata.pdf", "karar.pdf"]);
    attachMazbataToDilekce();

    expect(attachValue("mazbata.pdf")).toMatch(/^0-dilekce\.pdf/);
    expect(rowOrder()).toEqual(["dilekce.pdf", "mazbata.pdf", "karar.pdf"]);
    expect(rowOf("mazbata.pdf").textContent).toContain("↳");
    expect(rowOf("mazbata.pdf").textContent).toContain("kendi e-postası gitmez");
    expect(attachTrigger("mazbata.pdf")).toBeNull();               // ek satırda seçici yok, "Ayır" var
    expect(byLabel("Eki ayır: mazbata.pdf")).not.toBeNull();
    expect(emailSwitch("mazbata.pdf").checked).toBe(false);
    expect(emailSwitch("mazbata.pdf").disabled).toBe(true);
    expect(rowOf("dilekce.pdf").textContent).toContain("+1 ek");
    // Numara yalnız ana belgelerde: karar artık 02.
    expect(rowOf("karar.pdf").textContent).toContain("02");
  });

  it("ek satır görsel sırada ana belgeyi izler (karar → dilekçe eki olunca dilekçenin altına taşınır)", () => {
    const option = attachTrigger("karar.pdf").closest("[data-select]")!
      .querySelector("[data-option][data-value^='0-dilekce.pdf']")!;
    click(option);

    expect(rowOrder()).toEqual(["dilekce.pdf", "karar.pdf", "mazbata.pdf"]);

    click(byLabel("Eki ayır: karar.pdf"));
    expect(rowOrder()).toEqual(["dilekce.pdf", "mazbata.pdf", "karar.pdf"]);
    expect(attachValue("karar.pdf")).toBe("");
    expect(emailSwitch("karar.pdf").disabled).toBe(false);
    expect(emailSwitch("karar.pdf").checked).toBe(false);          // ayrılınca kapalı kalır
  });

  it("zincir yasak: ek olan satır aday değildir, ek taşıyan satırın seçicisi kilitlenir", () => {
    attachMazbataToDilekce();

    expect(attachOptions("karar.pdf")).toEqual(["— Ek değil —", "01 · dilekce.pdf"]);
    expect(attachTrigger("dilekce.pdf").disabled).toBe(true);
    expect(attachTrigger("karar.pdf").disabled).toBe(false);
  });

  it("ana satırın e-postası kapanınca bağ çözülür ve kullanıcı bilgilendirilir", () => {
    attachMazbataToDilekce();
    toggle(emailSwitch("dilekce.pdf"));

    expect(attachValue("mazbata.pdf")).toBe("");
    expect(attachTrigger("mazbata.pdf")).not.toBeNull();
    expect(emailSwitch("mazbata.pdf").disabled).toBe(false);
    expect(emailSwitch("mazbata.pdf").checked).toBe(false);
    expect(toastMock.info).toHaveBeenCalledWith("1 ek bağlantısı çözüldü.");
  });

  it("ana satır kuyruktan çıkarılınca bağ çözülür", () => {
    attachMazbataToDilekce();
    click(byLabel("Kuyruktan çıkar: dilekce.pdf"));

    expect(rowOrder()).toEqual(["mazbata.pdf", "karar.pdf"]);
    expect(attachValue("mazbata.pdf")).toBe("");
    expect(emailSwitch("mazbata.pdf").disabled).toBe(false);
  });

  it("toplu e-posta anahtarı kapanınca tüm bağlar çözülür", () => {
    attachMazbataToDilekce();
    toggle(byLabel<HTMLInputElement>("Tüm dosyalarda e-posta"));

    expect(attachValue("mazbata.pdf")).toBe("");
    for (const name of ["dilekce.pdf", "mazbata.pdf", "karar.pdf"]) {
      expect(emailSwitch(name).checked).toBe(false);
      expect(emailSwitch(name).disabled).toBe(false);
    }
  });

  it("Onaya Geç: ana satır ekin File'ını taşır, ek satır e-postasız ve eksiz gider", () => {
    attachMazbataToDilekce();
    // Alıcı seçilmeden e-posta açık → "her dosyada ayrıca onayla" ile kapı geçilir.
    toggle(container.querySelector("#wb-confirm-per-file") as HTMLInputElement);
    const start = Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes("Onaya Geç"))!;
    click(start);

    expect(onStart).toHaveBeenCalledTimes(1);
    const config = onStart.mock.calls[0][0];
    const byName = (n: string) => config.results.find(r => r.file.name === n)!;
    expect(byName("dilekce.pdf").email).toBe(true);
    expect(byName("dilekce.pdf").attachments).toEqual([MAZBATA]);
    expect(byName("dilekce.pdf").attachments![0]).toBe(MAZBATA);
    expect(byName("mazbata.pdf")).toMatchObject({ email: false, attachments: [] });
    expect(byName("karar.pdf")).toMatchObject({ email: true, attachments: [] });
    expect(config.emailConfig.confirmPerFile).toBe(true);
  });
});
