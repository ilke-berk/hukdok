// @vitest-environment jsdom
// MicButton + MicDurumSatiri (G217) — sunum katmanı: desteklenmeyen ortamda hiç çizilmez; boşta mikrofon ikonu +
// Türkçe aria-label; kayıtta `aria-pressed=true` + `0:12` sayacı ve tık `durdur`; çevrilirken/izin beklenirken dönen
// gösterge ve pasif; `disabled` yalnız BAŞLATMAYI engeller; durum satırı uyarıyı/“çevriliyor”u gösterir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { VoiceInput } from "@/hooks/useVoiceInput";
import { MicButton, MicDurumSatiri } from "./MicButton";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function sesNesnesi(p: Partial<VoiceInput> = {}): VoiceInput {
    return {
        destekleniyor: true,
        durum: "bosta",
        gecenSn: 0,
        uyari: null,
        baslat: vi.fn(async () => undefined),
        durdur: vi.fn(),
        iptal: vi.fn(),
        ...p,
    };
}

let root: Root | null = null;
let kap: HTMLDivElement;

function ciz(el: ReactElement) {
    act(() => root!.render(el));
}
const dugme = () => kap.querySelector<HTMLButtonElement>("[data-testid='mic-button']");
const tikla = (el: Element) => act(() => { el.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

beforeEach(() => {
    kap = document.createElement("div");
    document.body.appendChild(kap);
    root = createRoot(kap);
});
afterEach(() => {
    act(() => root!.unmount());
    root = null;
    kap.remove();
});

describe("MicButton", () => {
    it("desteklenmeyen ortamda düğme de durum satırı da yok", () => {
        const ses = sesNesnesi({ destekleniyor: false, uyari: "x" });
        ciz(<><MicButton ses={ses} /><MicDurumSatiri ses={ses} /></>);
        expect(dugme()).toBeNull();
        expect(kap.querySelector("[data-testid='mic-durum']")).toBeNull();
        expect(kap.innerHTML).toBe("");
    });

    it("boşta: Türkçe aria-label, aria-pressed=false, sayaç yok; tık baslat", () => {
        const ses = sesNesnesi();
        ciz(<MicButton ses={ses} />);
        const b = dugme()!;
        expect(b.getAttribute("aria-label")).toBe("Sesle yaz (mikrofon)");
        expect(b.getAttribute("aria-pressed")).toBe("false");
        expect(b.disabled).toBe(false);
        expect(b.querySelector("svg")).not.toBeNull();
        expect(kap.querySelector("[data-testid='mic-sayac']")).toBeNull();
        tikla(b);
        expect(ses.baslat).toHaveBeenCalledTimes(1);
        expect(ses.durdur).not.toHaveBeenCalled();
    });

    it("kayıtta: kırmızı, aria-pressed=true, 0:12 sayacı; tık durdur", () => {
        const ses = sesNesnesi({ durum: "kayitta", gecenSn: 12 });
        ciz(<MicButton ses={ses} disabled />);
        const b = dugme()!;
        expect(b.getAttribute("aria-pressed")).toBe("true");
        expect(b.getAttribute("aria-label")).toBe("Kaydı durdur ve yazıya çevir");
        expect(b.className).toContain("bg-tone-danger");
        expect(kap.querySelector("[data-testid='mic-sayac']")?.textContent).toBe("0:12");
        // disabled yalnız başlatmayı engeller — süren kayıt durdurulabilir
        expect(b.disabled).toBe(false);
        tikla(b);
        expect(ses.durdur).toHaveBeenCalledTimes(1);
        expect(ses.baslat).not.toHaveBeenCalled();
    });

    it.each(["cevriliyor", "izin_isteniyor"] as const)("%s: dönen gösterge ve pasif", (durum) => {
        const ses = sesNesnesi({ durum });
        ciz(<MicButton ses={ses} />);
        const b = dugme()!;
        expect(b.disabled).toBe(true);
        expect(b.querySelector(".animate-spin")).not.toBeNull();
        expect(b.getAttribute("aria-pressed")).toBe("false");
        tikla(b);
        expect(ses.baslat).not.toHaveBeenCalled();
    });

    it("disabled iken boşta düğme pasif (başlatmaz)", () => {
        const ses = sesNesnesi();
        ciz(<MicButton ses={ses} disabled />);
        expect(dugme()!.disabled).toBe(true);
    });
});

describe("MicDurumSatiri", () => {
    it("uyarı yok ve çevrilmiyorsa çizilmez", () => {
        ciz(<MicDurumSatiri ses={sesNesnesi()} />);
        expect(kap.querySelector("[data-testid='mic-durum']")).toBeNull();
    });

    it("çevrilirken 'Yazıya çevriliyor…'", () => {
        ciz(<MicDurumSatiri ses={sesNesnesi({ durum: "cevriliyor" })} />);
        expect(kap.querySelector("[data-testid='mic-durum']")?.textContent).toBe("Yazıya çevriliyor…");
    });

    it("hata uyarısı kırmızı tonda gösterilir", () => {
        ciz(<MicDurumSatiri ses={sesNesnesi({ durum: "hata", uyari: "Mikrofon izni verilmedi" })} />);
        const p = kap.querySelector("[data-testid='mic-durum']")!;
        expect(p.textContent).toBe("Mikrofon izni verilmedi");
        expect(p.getAttribute("role")).toBe("status");
        expect(p.className).toContain("text-tone-danger");
    });
});
