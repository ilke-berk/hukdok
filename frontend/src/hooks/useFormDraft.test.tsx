// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// api.ts MSAL yapılandırma zincirini çeker — hook yalnız olay ADINA muhtaç.
vi.mock("@/lib/api", () => ({ SESSION_EXPIRED_EVENT: "hukdok:session-expired" }));

import { SESSION_EXPIRED_EVENT } from "@/lib/api";
import {
  createDraftStore,
  resumeAllDrafts,
  suppressAllDrafts,
} from "@/lib/formDraft";
import { useFormDraft, type FormDraftHandle } from "./useFormDraft";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// =====================================================================
// useFormDraft etkileşim testleri (G004 denetim düzeltmesi — RET bulgusu).
//
// Denetimin işaret ettiği boşluk: bastırma/flush ETKİLEŞİMİ test dışıydı.
// Burada hook gerçek bir render ağacında kurulur; pagehide / beforeunload /
// SESSION_EXPIRED olayları jsdom'da dispatch edilerek üç sözleşme doğrulanır:
//  1) Normal akış: debounce'lu yazım + bekletmesiz flush yolları çalışır.
//  2) LOGOUT: suppressAllDrafts() sonrası HİÇBİR flush yolu temizlenen
//     taslağı geri yazamaz; beforeunload diyaloğu logout'u bölmez.
//  3) Sayfa içi clear() kilidi (yerel suppressed) global bayraktan bağımsız
//     çalışmaya devam eder.
// =====================================================================

interface Sample {
  name: string;
}

const KEY = "hukdok.hook-test-draft.v1";
const DEBOUNCE_MS = 100;
const HOUR = 60 * 60 * 1000;

const store = createDraftStore<Sample>({ key: KEY, version: 1, maxAgeMs: HOUR });

const rawDraft = () => sessionStorage.getItem(KEY);

const fireUnload = () => {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
};
const firePagehide = () => window.dispatchEvent(new Event("pagehide"));
const fireSessionExpired = () => window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));

type HarnessProps = { data: Sample; dirty: boolean };

interface Mounted {
  handle: () => FormDraftHandle<Sample>;
  rerender: (props: HarnessProps) => void;
  unmount: () => void;
}

let active: { root: Root; container: HTMLDivElement; unmounted: boolean } | null = null;

function mountHook(props: HarnessProps): Mounted {
  let captured: FormDraftHandle<Sample> | null = null;
  const Harness = ({ data, dirty }: HarnessProps) => {
    captured = useFormDraft(store, { data, dirty, debounceMs: DEBOUNCE_MS });
    return null;
  };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(<Harness {...props} />));
  const state = { root, container, unmounted: false };
  active = state;
  return {
    handle: () => captured!,
    rerender: (next: HarnessProps) => act(() => root.render(<Harness {...next} />)),
    unmount: () => {
      if (!state.unmounted) {
        state.unmounted = true;
        act(() => root.unmount());
        container.remove();
      }
    },
  };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  resumeAllDrafts(); // bayrak modül düzeyi — sonraki teste sızmasın
  if (active && !active.unmounted) {
    act(() => active!.root.unmount());
    active.container.remove();
  }
  active = null;
  vi.useRealTimers();
});

const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));

describe("useFormDraft — yazım/flush etkileşimi (normal akış)", () => {
  it("kirli formda debounce süresi dolunca taslak diske iner", () => {
    mountHook({ data: { name: "Ahmet" }, dirty: true });
    expect(rawDraft()).toBeNull(); // debounce dolmadan yazım yok
    advance(DEBOUNCE_MS + 10);
    expect(store.load()?.data).toEqual({ name: "Ahmet" });
  });

  it("pagehide bekleyen yazımı BEKLETMEDEN flush eder", () => {
    mountHook({ data: { name: "Ahmet" }, dirty: true });
    firePagehide(); // debounce dolmadı ama flush anında yazar
    expect(store.load()?.data).toEqual({ name: "Ahmet" });
  });

  it("oturum düşmesi (SESSION_EXPIRED_EVENT) flush eder — 401 özelliği yaşıyor", () => {
    mountHook({ data: { name: "Ahmet" }, dirty: true });
    fireSessionExpired();
    expect(store.load()?.data).toEqual({ name: "Ahmet" });
  });

  it("kirli formda beforeunload uyarır VE bekleyen yazımı flush eder", () => {
    mountHook({ data: { name: "Ahmet" }, dirty: true });
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(true); // tarayıcı diyaloğu çıkar
    expect(store.load()?.data).toEqual({ name: "Ahmet" });
  });

  it("temiz formda (dirty=false) hiçbir yol yazmaz, uyarı da çıkmaz", () => {
    mountHook({ data: { name: "" }, dirty: false });
    advance(DEBOUNCE_MS * 3);
    firePagehide();
    const event = fireUnload();
    expect(event.defaultPrevented).toBe(false);
    expect(rawDraft()).toBeNull();
  });
});

describe("useFormDraft — logout bastırması (RET senaryosu)", () => {
  it("Çıkış akışı: suppress + temizlik sonrası pagehide taslağı GERİ YAZMAZ", () => {
    // Bug'ın gerçek sırası: kirli form → taslak diskte → Çıkış.
    mountHook({ data: { name: "önceki kullanıcının TC'li formu" }, dirty: true });
    advance(DEBOUNCE_MS + 10);
    expect(rawDraft()).not.toBeNull();

    suppressAllDrafts(); // Sidebar.handleLogout adım 1
    sessionStorage.clear(); // adım 2: clearAppStorage temsilcisi

    firePagehide(); // logoutRedirect navigasyonunun tetiklediği flush
    expect(rawDraft()).toBeNull(); // depo TEMİZ kaldı — dirilme yok

    advance(DEBOUNCE_MS * 3); // bekleyen debounce da yazamaz
    expect(rawDraft()).toBeNull();
  });

  it("Çıkış akışı: beforeunload diyaloğu logout'u BÖLMEZ, flush yazmaz", () => {
    mountHook({ data: { name: "kirli form" }, dirty: true });
    suppressAllDrafts();
    sessionStorage.clear();

    const event = fireUnload();
    expect(event.defaultPrevented).toBe(false); // "ayrılmak istiyor musunuz?" YOK
    expect(rawDraft()).toBeNull();
  });

  it("Çıkış akışı: oturum-düşmesi ve unmount flush'ları da bastırılır", () => {
    const mounted = mountHook({ data: { name: "kirli form" }, dirty: true });
    suppressAllDrafts();
    sessionStorage.clear();

    fireSessionExpired();
    expect(rawDraft()).toBeNull();

    mounted.unmount(); // route değişimi flush'ı (useEffect cleanup)
    expect(rawDraft()).toBeNull();
  });

  it("logout kurulamadı (resume): taslak sistemi kaldığı yerden yazar", () => {
    mountHook({ data: { name: "oturum sürüyor" }, dirty: true });
    suppressAllDrafts();
    firePagehide();
    expect(rawDraft()).toBeNull();

    resumeAllDrafts(); // Sidebar catch yolu — kullanıcı oturumda kaldı
    firePagehide();
    expect(store.load()?.data).toEqual({ name: "oturum sürüyor" });
  });
});

describe("useFormDraft — sayfa içi clear() sözleşmesi bozulmadı", () => {
  it("clear() sonrası pagehide 'kaydedilmiş verinin hayaleti'ni geri yazmaz", () => {
    const mounted = mountHook({ data: { name: "kaydedildi" }, dirty: true });
    advance(DEBOUNCE_MS + 10);
    expect(rawDraft()).not.toBeNull();

    act(() => mounted.handle().clear()); // kaydet/iptal sonrası yerel kilit
    expect(rawDraft()).toBeNull();

    firePagehide();
    expect(rawDraft()).toBeNull(); // global bayrak KURULMADAN yerel kilit yetti
  });

  it("clear() kilidi veri DEĞİŞİNCE açılır — yazım normal akışta devam eder", () => {
    const mounted = mountHook({ data: { name: "ilk" }, dirty: true });
    advance(DEBOUNCE_MS + 10);
    act(() => mounted.handle().clear());
    expect(rawDraft()).toBeNull();

    mounted.rerender({ data: { name: "yeni emek" }, dirty: true });
    advance(DEBOUNCE_MS + 10);
    expect(store.load()?.data).toEqual({ name: "yeni emek" });
  });
});
