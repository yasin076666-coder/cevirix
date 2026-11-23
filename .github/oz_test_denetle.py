"""Çevirix PC öz test sonucunu denetler (cevirix-pc.yml çağırır)."""
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
hatalar = []
if "gotta" not in (d.get("ocr") or "").lower():
    hatalar.append("OCR yazıyı okuyamadı")
if (d.get("sozluk") or 0) <= 1000:
    hatalar.append("Sokak sözlüğü yüklenmedi")
if not d.get("sokak"):
    hatalar.append("Sokak dili katmanı çalışmadı")
for ad in ("tv", "web", "arayuz"):
    if d.get(ad) != "tamam":
        hatalar.append(f"{ad} denetimi başarısız")
ses = d.get("ses") or {}
if "ses_hata" in d or str(ses.get("sorun") or "").startswith("Windows ses motoru açılamadı"):
    hatalar.append("Ses motoru paketin içinde açılamadı")
for k, v in d.items():
    if k.endswith("_hata"):
        print(f"--- {k} ---\n{v}")
if hatalar:
    print("OZ TEST BASARISIZ: " + "; ".join(hatalar))
    sys.exit(1)
print("OZ TEST TAMAM")
