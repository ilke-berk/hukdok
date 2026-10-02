// @vitest-environment jsdom
// Faz 5: arkaplan tazeleme çizgisi + gecikmeli bayrak. Kilitlenenler: kısa tazelemede hiç görünmez,
// göründüyse en az 400 ms kalır; yalnız EKRANDAKİ veri tazelenirken (önden yükleme ve ilk yükleme sayılmaz).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { useDelayedFlag } from "@/hooks/useDelayedFlag";
import { ArkaplanCizgisi, ekrandakiVeriTazeleniyor } from "./ArkaplanCizgisi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const ilerle = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });
// Bildirim → çizim → efekt → zamanlayıcı zinciri her act sonunda bir halka ilerler; gerçek zamanı
// taklit etmek için küçük adımlarla ilerlet.
const adimAdim = (ms: number) => { for (let t = 0; t < ms; t += 50) ilerle(50); };

describe("useDelayedFlag", () => {
  let gorunur = false;
  function Kopru({ flag }: { flag: boolean }) {
    gorunur = useDelayedFlag(flag, 250, 400);
    return null;
  }

  it("gecikmeden kısa süren bayrak hiç görünmez", () => {
    act(() => root.render(<Kopru flag />));
    ilerle(200);
    act(() => root.render(<Kopru flag={false} />));
    ilerle(500);
    expect(gorunur).toBe(false);
  });

  it("gecikmeyi aşınca görünür ve bayrak inse de en az minVisible kalır", () => {
    act(() => root.render(<Kopru flag />));
    ilerle(260);
    expect(gorunur).toBe(true);
    act(() => root.render(<Kopru flag={false} />));
    ilerle(100);
    expect(gorunur).toBe(true);
    ilerle(320);
    expect(gorunur).toBe(false);
  });
});

describe("ArkaplanCizgisi", () => {
  let queryClient: QueryClient;
  let cozucu: ((v: string) => void) | null;
  const yavasFn = () => new Promise<string>(r => { cozucu = r; });

  function Ekran() {
    useQuery({ queryKey: ["veri"], queryFn: yavasFn, staleTime: 0 });
    return <ArkaplanCizgisi />;
  }
  const cizgi = () => container.querySelector("[data-testid='arkaplan-cizgisi']");
  const ciz = (el: React.ReactElement) =>
    act(() => root.render(<QueryClientProvider client={queryClient}>{el}</QueryClientProvider>));

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    cozucu = null;
  });
  afterEach(() => queryClient.clear());

  it("ilk yükleme (elde veri yok) çizgi göstermez — iskelet zaten var", () => {
    ciz(<Ekran />);
    ilerle(1000);
    expect(cizgi()).toBeNull();
  });

  it("ekrandaki veri arkada tazelenirken 250 ms sonra görünür, yanıt gelince kaybolur", async () => {
    queryClient.setQueryData(["veri"], "eski");
    ciz(<Ekran />);       // staleTime 0 → mount'ta tazeleme başlar
    ilerle(100);
    expect(queryClient.isFetching({ predicate: ekrandakiVeriTazeleniyor })).toBe(1);
    expect(cizgi()).toBeNull();
    adimAdim(300);
    expect(cizgi()).not.toBeNull();
    await act(async () => { cozucu!("yeni"); });
    adimAdim(500);
    expect(cizgi()).toBeNull();
  });

  it("önden yükleme (gözlemcisiz sorgu) çizgi göstermez", () => {
    queryClient.setQueryData(["onyukleme"], "eski");
    ciz(<ArkaplanCizgisi />);
    act(() => { void queryClient.prefetchQuery({ queryKey: ["onyukleme"], queryFn: yavasFn, staleTime: 0 }); });
    ilerle(1000);
    expect(cizgi()).toBeNull();
  });
});
