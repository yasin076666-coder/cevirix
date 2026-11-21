# Çevirix

PS5 oyunlarını (GTA 6 vb.) Türkçe altyazıyla oynamak için iki uygulama:

- **CevirixTelefon.apk** (Samsung Galaxy S8+): PS Remote Play ekranındaki İngilizce altyazıyı okur, Gemini ile sokak diline uygun Türkçeye çevirir (internet yoksa telefonun içinde çevirir), isterseniz sesli okur.
- **CevirixTV.apk** (Philips Android TV): Türkçe altyazıyı HDMI görüntüsünün, yani oyunun üstüne yazar.

Telefon ve TV aynı Wi-Fi ağında olmalı. TV telefonu kendiliğinden bulur. Bağlantı koparsa iki taraf da kendiliğinden yeniden bağlanır.

## Derleme (bilgisayarsız, GitHub ile)
1. GitHub'da yeni bir depo açın (Private önerilir).
2. `kaynak.zip` dosyasını depoya yükleyin.
3. `.github/workflows/derle.yml` adlı yeni bir dosya oluşturup bu paketteki aynı adlı dosyanın içeriğini yapıştırın.
4. Actions sekmesinde derleme biter (5-10 dk). APK'lar **Releases** bölümüne gelir.

Ayrıntılı adımlar için kurulum rehberine bakın.

## Teknik özet
- Telefon: MediaProjection ile ekran yakalama → sadece altyazı şeridi → ML Kit OCR → Gemini (yoksa ML Kit çevrimdışı) → WebSocket (port 8765) + NSD duyurusu → Android TTS.
- TV: NSD ile telefonu bulma + elle IP yedeği → OkHttp WebSocket (5 sn ping, 1-5 sn yeniden bağlanma) → TYPE_APPLICATION_OVERLAY katmanı.
- İki uygulama da aynı sabit anahtarla imzalanır; yeni sürüm eskisinin üstüne kurulur.
