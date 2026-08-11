# docs/kararlar — kalıcı mimari kararlar

Geri alınması pahalı olan ya da tekrar tekrar sorgulanan kararların gerekçesi burada
tutulur: **karar + bağlam + gerekçe + reddedilen alternatifler**.

**Durum: iskelet.** Mevcut kararların derlenmesi G007 görevinde yapılacak.

## Dosya biçimi

`NNN-kisa-baslik.md`, içinde:

```
# NNN — <karar>
- **Durum:** kabul | değiştirildi (bkz. NNN) | geri alındı
- **Bağlam:** hangi problem
- **Karar:** ne yapıldı
- **Gerekçe:** neden bu
- **Reddedilenler:** hangi alternatif, neden değil
```

Karar bir plan adımı değil, **kalıcı bir tercih** olmalı; tek seferlik iş kalemleri
[`docs/plan/`](../plan/) altına ya da `gorevler/` kuyruğuna yazılır.
