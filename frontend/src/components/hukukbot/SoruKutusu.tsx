import { useCallback, useEffect, useRef, useState } from "react";
import { SohbetGirdisi } from "@/components/SohbetGirdisi";
import { metneEkle, useVoiceInput } from "@/hooks/useVoiceInput";

type SoruKutusuProps = {
  /** Yanıt akarken kutu kilitlidir; gönder düğmesinin yerinde "Durdur" durur. */
  gonderiliyor: boolean;
  onGonder: (soru: string) => void;
  onDurdur: () => void;
  autoFocus?: boolean;
  /** Dışarıdan kutuya metin koyar (boş sohbetteki örnek soru çipleri). `tik` aynı metnin tekrar seçimini ayırır. */
  disMetin?: { metin: string; tik: number } | null;
};

/**
 * Giriş kutusu (G205): Enter gönderir, Shift+Enter yeni satır (IME birleştirmesi sırasında Enter
 * gönderMEZ); boş/yalnız boşluk soru gönderilmez; gönderim sürerken textarea kilitli. Görünüm ve tuş
 * davranışı ortak `SohbetGirdisi`'nde (rapor asistanıyla aynı kutu).
 * G217: mikrofon düğmesi (`MicButton`) — yazıya çevrilen metin kutudaki metnin SONUNA eklenir, odak kutuya
 * döner; soru OTOMATİK GÖNDERİLMEZ (kullanıcı okuyup düzeltir). Örnek soru çipi (`disMetin`) de aynı ilkeyle
 * yalnız kutuyu doldurur. Ses Hukukbot'a değil HUKDOK `/api/transcribe`'a gider.
 */
export function SoruKutusu({ gonderiliyor, onGonder, onDurdur, autoFocus, disMetin }: SoruKutusuProps) {
  const [metin, setMetin] = useState("");
  const kutuRef = useRef<HTMLTextAreaElement | null>(null);

  // Örnek soru: kutudaki metnin YERİNE geçer, odak kutuya gelir; gönderim OTOMATİK DEĞİL.
  useEffect(() => {
    if (!disMetin) return;
    setMetin(disMetin.metin);
    kutuRef.current?.focus();
  }, [disMetin]);

  const sesMetni = useCallback((gelen: string) => {
    setMetin(prev => metneEkle(prev, gelen));
    kutuRef.current?.focus();
  }, []);
  const ses = useVoiceInput({ onMetin: sesMetni });

  const gonder = () => {
    onGonder(metin.trim());
    setMetin("");
  };

  return (
    <SohbetGirdisi
      value={metin}
      onChange={setMetin}
      onGonder={gonder}
      gonderiliyor={gonderiliyor}
      onDurdur={onDurdur}
      ses={ses}
      ariaLabel="Hukukbot'a soru"
      testId="hukukbot-soru"
      textareaRef={kutuRef}
      placeholder={gonderiliyor ? "Yanıt bekleniyor..." : "Hukukbot'a sorun…"}
      autoFocus={autoFocus}
    />
  );
}
