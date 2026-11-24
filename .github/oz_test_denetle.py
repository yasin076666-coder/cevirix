"""Çevirix PC öz test sonucunu denetler (cevirix-pc.yml çağırır).

Hatalar GitHub "annotation" olarak da yazılır; böylece günlüğe giriş yapmadan da görülebilir.
"""
import json
import sys

# Windows konsolu varsayılan olarak cp1252: Türkçe harfler yazılamaz
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def notu_yaz(baslik, metin):
    metin = metin.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={baslik}::{metin[:3500]}")


try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    notu_yaz("oz_test.json okunamadi", f"Program test sonucunu yazmadı: {e}")
    sys.exit(1)

hatalar = []
kod = sys.argv[2] if len(sys.argv) > 2 else "?"
if d.get("son_baslayan") != "bitti":
    hatalar.append(f"Program '{d.get('son_baslayan')}' adımında çöktü (çıkış kodu {kod})")
if "gotta" not in (d.get("ocr") or "").lower():
    hatalar.append("OCR yazıyı okuyamadı")
if (d.get("sozluk") or 0) <= 1000:
    hatalar.append("Sokak sözlüğü yüklenmedi")
if not d.get("sokak"):
    hatalar.append("Sokak dili katmanı çalışmadı")
for ad in ("pencere", "gta", "tv", "web", "arayuz"):
    if d.get(ad) != "tamam":
        hatalar.append(f"{ad} denetimi başarısız")
ses = d.get("ses") or {}
if "ses_hata" in d or str(ses.get("sorun") or "").startswith("Windows ses motoru açılamadı"):
    hatalar.append("Ses motoru paketin içinde açılamadı")
for k, v in d.items():
    if k.endswith("_hata"):
        print(f"--- {k} ---\n{v}")
        notu_yaz(k, str(v)[-3000:])
ozet = {k: v for k, v in d.items() if not k.endswith("_hata")}
print(f"::notice title=Oz test sonucu::{json.dumps(ozet, ensure_ascii=False)[:3000]}")
if hatalar:
    notu_yaz("OZ TEST BASARISIZ", "; ".join(hatalar))
    sys.exit(1)
print("OZ TEST TAMAM")
