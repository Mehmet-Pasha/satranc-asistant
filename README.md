# ♞ Satranç Antrenman Asistanı

chess.com ve Lichess'te **bilgisayara (bot) karşı** oynarken veya antrenman yaparken
kullanılan Stockfish destekli yardımcı panel. Resmi Stockfish motoruyla çalışır.

> ⚠️ Bu araç antrenman/öğrenme amaçlıdır. Gerçek oyunculara karşı (rated) oyunlarda
> kullanmak platform kurallarına aykırıdır ve kalıcı ban sebebidir.

## Kurulum (Windows)

1. `build_exe.bat` dosyasına çift tıkla. (Python kurulu değilse önce
   https://www.python.org/downloads/ adresinden kur — kurulumda
   **"Add python.exe to PATH"** işaretli olsun.)
2. Script her şeyi yapar: kütüphaneler + resmi Stockfish + `dist\SatrancAsistan\` klasörü.
3. Programı başlat: `dist\SatrancAsistan\SatrancAsistan.exe`
   *(klasörü birlikte taşı; `stockfish` klasörü yanında kalmalı)*

Elle kurmak istersen: `pip install PyQt6 numpy mss pyautogui keyboard`
sonra Stockfish'i https://stockfishchess.org/download/ adresinden indir,
`stockfish/stockfish.exe` olarak programın yanına koy.

## Kullanım (her site için BİR KEZ kurulum)

1. **① Tahtayı Bul (otomatik)** → program tahtayı ekranda kendisi bulur
   (2-6 saniye). Oyun **başlangıç diziliminde** açıksa referansı da kendisi
   alır ve profili kaydeder — tek düğme yeter.
   Bulamazsa elle seçim ekranı açılır: tahtanın köşesinden köşesine sürükle.
2. Otomatik referans alınamadıysa: oyunu **başlangıç diziliminde** aç
   (hamle yapılmamış) → **② Referans Al**.
3. Siyah tarafı oynuyorsan **"Siyah altta"** kutusunu işaretle.

### Önerilen temalar (chess.com)
- Tahta: **Green** veya **Brown** (düz renk) — otomatik bulma düz renk ister
- Taşlar: **Standard** veya **Neo** (düz renk, yüksek kontrast)
- Kaçın: 3D tahtalar, doku/foto temalar (Marble, Wood…), saydam/outline taşlar
- Lichess: varsayılan tema + taşlar sorunsuz.

## Modlar

| Tuş / Düğme | Ne yapar |
|---|---|
| **İpucu (F10)** | Bir basışta tek en iyi hamleyi altın okla gösterir. |
| **Canlı Ok (F11)** | Açık kaldığı sürece en iyi hamleyi sürekli oklar (sadece senin sıran seçeneği var). |
| **Oto Oyna (F12)** | Motoru devralır: hamleleri tıklayarak kendi oynar. Tekrar F12 = durdur. |
| Okları Sil (F9) | Ekranı temizler. |

Değerlendirme (avantaj skoru) panelin altında görünür.

## İpuçları / Sınırlar

- Kalibrasyonu yaptıktan sonra **zoom/tema değiştirme**; değiştirirsen yeniden kalibre et.
- Okunamama olursa "Tanıma hassasiyeti"ni biraz artır (26 → 30).
- Terfi ederken panel "otomatik vezir" tıklar; çalışmazsa veziri elle seç.
- Panel penceresi her zaman üstte durur; taşımaktan çekinme.
- Bot oyunlarında sıra takibi otomatiktir; oyunu ortadan yüklersen
  "Sıra başlangıcı"nı o anki sıradaşına ayarla.