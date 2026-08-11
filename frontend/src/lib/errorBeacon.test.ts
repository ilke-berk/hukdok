// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
  buildFromErrorEvent,
  buildFromRejection,
  initErrorBeacon,
  reportCaughtRenderError,
  sendReport,
  shouldSend,
} from "./errorBeacon";

// jsdom navigator.sendBeacon uygulamaz — testler kendi stub'ını takar.
function stubSendBeacon() {
  const spy = vi.fn().mockReturnValue(true);
  Object.defineProperty(window.navigator, "sendBeacon", {
    value: spy,
    configurable: true,
    writable: true,
  });
  return spy;
}

beforeEach(() => {
  _resetForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (window.navigator as { sendBeacon?: unknown }).sendBeacon;
});

describe("buildFromErrorEvent", () => {
  it("alanları beyaz listeye eşler ve kırpar", () => {
    const err = new Error("patladı");
    const event = new ErrorEvent("error", {
      message: "x".repeat(3000),
      filename: "https://hukukoid.com/app.js",
      lineno: 42,
      colno: 7,
      error: err,
    });
    const report = buildFromErrorEvent(event);
    expect(report.kind).toBe("error");
    expect(report.message).toHaveLength(2000); // MAX_MESSAGE kırpması
    expect(report.url).toBe("https://hukukoid.com/app.js");
    expect(report.line).toBe(42);
    expect(report.col).toBe(7);
    expect(report.stack).toBe(err.stack);
  });

  it("mesaj yoksa error.message'a düşer", () => {
    const event = new ErrorEvent("error", { error: new Error("iç mesaj") });
    expect(buildFromErrorEvent(event).message).toBe("iç mesaj");
  });
});

describe("buildFromRejection", () => {
  it("Error reason'dan mesaj + stack alır", () => {
    const reason = new Error("reddedildi");
    const report = buildFromRejection({ reason } as PromiseRejectionEvent);
    expect(report.kind).toBe("unhandledrejection");
    expect(report.message).toBe("reddedildi");
    expect(report.stack).toBe(reason.stack);
  });

  it("string ve nesne reason'ları stringleştirir", () => {
    expect(buildFromRejection({ reason: "düz metin" } as PromiseRejectionEvent).message).toBe(
      "düz metin",
    );
    expect(buildFromRejection({ reason: { code: 7 } } as PromiseRejectionEvent).message).toBe(
      '{"code":7}',
    );
  });
});

describe("shouldSend (kısma)", () => {
  it("aynı imzayı 30 sn penceresinde bir kez geçirir", () => {
    expect(shouldSend("a", 1000)).toBe(true);
    expect(shouldSend("a", 2000)).toBe(false);
    expect(shouldSend("b", 2000)).toBe(true); // farklı imza serbest
    expect(shouldSend("a", 1000 + 30_000)).toBe(true); // pencere doldu
  });

  it("oturum tavanından (20) sonra her şeyi keser", () => {
    for (let i = 0; i < 20; i++) {
      expect(shouldSend(`sig-${i}`, 1000)).toBe(true);
    }
    expect(shouldSend("yepyeni", 999_999_999)).toBe(false);
  });
});

describe("sendReport", () => {
  it("sendBeacon varsa düz string gövdeyle onu kullanır", () => {
    const spy = stubSendBeacon();
    sendReport({ kind: "error", message: "m" });
    expect(spy).toHaveBeenCalledTimes(1);
    const [url, body] = spy.mock.calls[0];
    expect(url).toBe("/api/client-error");
    // Düz string (Blob değil): application/json CORS preflight isterdi
    expect(typeof body).toBe("string");
    expect(JSON.parse(body as string)).toEqual({ kind: "error", message: "m" });
  });

  it("sendBeacon yoksa keepalive fetch'e düşer", () => {
    const fetchSpy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchSpy);
    sendReport({ kind: "error", message: "m" });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/client-error");
    expect(options.keepalive).toBe(true);
    vi.unstubAllGlobals();
  });

  it("fetch reddi yutulur, sendReport asla fırlatmaz", async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new TypeError("ağ yok"));
    vi.stubGlobal("fetch", fetchSpy);
    expect(() => sendReport({ kind: "error", message: "m" })).not.toThrow();
    await Promise.resolve(); // .catch() zinciri koşsun
    vi.unstubAllGlobals();
  });
});

describe("initErrorBeacon (uçtan uca dinleyici)", () => {
  it("window error olayını bir kez raporlar, tekrarını 30 sn kısar", () => {
    const spy = stubSendBeacon();
    initErrorBeacon();
    const fire = () =>
      window.dispatchEvent(
        new ErrorEvent("error", { message: "aynı hata", lineno: 1, colno: 1 }),
      );
    fire();
    fire();
    expect(spy).toHaveBeenCalledTimes(1);
    const report = JSON.parse(spy.mock.calls[0][1] as string);
    expect(report.kind).toBe("error");
    expect(report.message).toBe("aynı hata");
  });

  it("unhandledrejection olayını raporlar", () => {
    const spy = stubSendBeacon();
    initErrorBeacon();
    // jsdom PromiseRejectionEvent kurucusunu uygulamaz — reason elle takılır
    const event = new Event("unhandledrejection");
    (event as unknown as { reason: unknown }).reason = new Error("reddedildi");
    window.dispatchEvent(event);
    expect(spy).toHaveBeenCalledTimes(1);
    const report = JSON.parse(spy.mock.calls[0][1] as string);
    expect(report.kind).toBe("unhandledrejection");
    expect(report.message).toBe("reddedildi");
  });
});

describe("reportCaughtRenderError (Faz 4.4: ErrorBoundary köprüsü)", () => {
  it("Error'ı [ErrorBoundary] önekiyle kind=error olarak raporlar", () => {
    const spy = stubSendBeacon();
    const err = new Error("render patladı");

    reportCaughtRenderError(err, "in App\n  in div");

    expect(spy).toHaveBeenCalledTimes(1);
    const report = JSON.parse(spy.mock.calls[0][1] as string);
    // Backend beyaz listesi {"error","unhandledrejection"} — yeni kind "unknown"a
    // düşerdi; ayrım mesaj önekiyle yapılır.
    expect(report.kind).toBe("error");
    expect(report.message).toBe("[ErrorBoundary] render patladı");
    expect(report.stack).toBe(err.stack); // Error stack'i componentStack'e tercih edilir
  });

  it("Error olmayan değeri stringleştirir ve stack olarak componentStack'e düşer", () => {
    const spy = stubSendBeacon();

    reportCaughtRenderError({ code: 7 }, "in App");

    const report = JSON.parse(spy.mock.calls[0][1] as string);
    expect(report.message).toBe('[ErrorBoundary] {"code":7}');
    expect(report.stack).toBe("in App");
  });

  it("aynı render hatası 30 sn penceresinde bir kez gider (ortak kısma)", () => {
    const spy = stubSendBeacon();
    const err = new Error("döngüdeki hata");

    reportCaughtRenderError(err);
    reportCaughtRenderError(err);

    expect(spy).toHaveBeenCalledTimes(1);
  });
});
