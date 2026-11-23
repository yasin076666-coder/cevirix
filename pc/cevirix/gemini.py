"""Gemini ile GTA sokak diline uygun Türkçe çeviri (telefon sürümüyle aynı talimat)."""
import json
import ssl
import urllib.error
import urllib.request

VARSAYILAN_MODEL = "gemini-3.5-flash-lite"
YEDEK_MODELLER = ["gemini-3.5-flash-lite", "gemini-3-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
# Telefon sürümündeki model düğmeleri
MODEL_SECENEKLERI = [
    ("En hızlı (3.5 Flash-Lite)", "gemini-3.5-flash-lite"),
    ("En kaliteli (3.6 Flash)", "gemini-3.6-flash"),
    ("Yedek (2.5 Flash-Lite)", "gemini-2.5-flash-lite"),
]
DENEME_CUMLESI = "Yo bro, the cops are right behind us, we gotta bounce!"

SISTEM = """Sen GTA 6 için çalışan, sokak kültürünü çok iyi bilen profesyonel bir Türkçe oyun yerelleştirme uzmanısın.
Görevin: Ekrandan yazı tanıma (OCR) ile okunmuş İngilizce oyun altyazısını, karakterlerin ağzından çıkmış gibi doğal ve akıcı Türkçe sokak diliyle çevirmek.

Kurallar:
- Sadece Türkçe çeviriyi yaz. Açıklama, tırnak işareti, not veya alternatif yazma.
- Kitap dili kullanma. Samimi, canlı, sokak ağzı kullan: "bro/dude/man" için bağlama göre "kanka, birader, abi, lan"; "cops" için "aynasızlar, polisler"; "let's go/bounce" için "kaçalım, toz olalım" gibi. Abartma, her cümleye argo sıkıştırma; Türk bir oyuncunun doğal bulacağı şekilde yaz.
- Küfür ve sert ifadeleri yumuşatma ve sansürleme; Türkçedeki doğal karşılığıyla çevir.
- Kişi, şehir, mekan, marka ve araç adlarını (Lucia, Jason, Vice City, Leonida, Port Gellhorn vb.) çevirme.
- Satırın başında konuşmacı adı varsa (ör. "LUCIA: ...") adı aynen koru ve sadece konuşmayı çevir.
- OCR hatası varsa (eksik harf, bozuk kelime, birleşik kelimeler) cümlenin anlamını tahmin edip düzgün çevir.
- Metin bir diyalog değilse (menü, sayı, para, harita, anlamsız harfler) hiçbir şey yazma, boş yanıt ver.
- Çeviri altyazı gibi kısa ve hızlı okunur olsun."""

VARSAYILAN_TERIMLER = """Lucia
Jason
Vice City
Leonida
Leonida Keys
Port Gellhorn
Grassrivers
Ambrosia
Mount Kalaga
Vice-Dale
VCPD
Ammu-Nation
Weazel News
Cal Hampton
Boobie Ike
Dre'Quan
Raul Bautista
Brian Heder
Real Dimez"""


class GeminiHatasi(Exception):
    def __init__(self, kod, mesaj):
        super().__init__(mesaj)
        self.kod = kod

    @property
    def anahtar_sorunu(self):
        return self.kod in (401, 403) or "api key" in str(self).lower()


def acikla(e, model=""):
    """Hata için kısa Türkçe açıklama (telefon sürümüyle aynı)."""
    if isinstance(e, GeminiHatasi):
        if e.kod == 429:
            return "Gemini kotası doldu"
        if e.anahtar_sorunu:
            return "Gemini anahtarı geçersiz"
        if e.kod == 404:
            return f"Model bulunamadı ({model})"
        if e.kod >= 500:
            return "Gemini sunucusu yanıt vermedi"
        if e.kod == 0:
            return "İnternet bağlantısı yok veya yavaş"
        return f"Gemini hatası: {e}"
    return f"Gemini hatası: {e}"


def terim_notu(english, terimler_metni):
    keep, fixed = [], []
    for raw in (terimler_metni or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            src, dst = (x.strip() for x in line.split("=", 1))
            if src and src.lower() in english.lower():
                fixed.append(f"{src} → {dst}")
        elif line.lower() in english.lower():
            keep.append(line)
    if not keep and not fixed:
        return None
    s = "Terim sözlüğü:"
    if keep:
        s += " şu adları çevirme, aynen yaz: " + ", ".join(keep) + "."
    if fixed:
        s += " Şu karşılıkları kullan: " + "; ".join(fixed) + "."
    return s


def _thinking(model):
    if model.startswith("gemini-2.5"):
        return None if "pro" in model else {"thinkingBudget": 0}
    if model.startswith("gemini-3") or model.startswith("gemini-4"):
        return {"thinkingLevel": "minimal"}
    return None


class Gemini:
    def __init__(self):
        self._dusunmesiz = set()
        self._ctx = ssl.create_default_context()

    def istek_govdesi(self, english, baglam, terimler, model, dusunme=True):
        parcalar = []
        if baglam:
            parcalar.append("Önceki altyazılar (sadece bağlam için, bunları tekrar çevirme):")
            for en, tr in baglam:
                parcalar.append(f"EN: {en}\nTR: {tr}")
            parcalar.append("")
        not_ = terim_notu(english, terimler)
        if not_:
            parcalar.append(not_ + "\n")
        parcalar.append("Şimdi bu altyazıyı çevir:\n" + english)
        gen = {"temperature": 0.5, "maxOutputTokens": 300}
        if dusunme:
            t = _thinking(model)
            if t:
                gen["thinkingConfig"] = t
        return {
            "system_instruction": {"parts": [{"text": SISTEM}]},
            "contents": [{"role": "user", "parts": [{"text": "\n".join(parcalar)}]}],
            "generationConfig": gen,
            "safetySettings": [
                {"category": c, "threshold": "BLOCK_NONE"} for c in (
                    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
            ],
        }

    def _cagir(self, anahtar, model, govde):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(govde).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", "x-goog-api-key": anahtar.strip()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=9, context=self._ctx) as r:
                raw = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(raw)["error"]["message"]
            except Exception:
                msg = raw[:200]
            raise GeminiHatasi(e.code, msg)
        except Exception as e:  # bağlantı yok, zaman aşımı
            raise GeminiHatasi(0, f"İnternet/bağlantı hatası: {e}")
        return self.cozumle(raw)

    @staticmethod
    def cozumle(raw):
        root = json.loads(raw)
        cands = root.get("candidates") or []
        if not cands:
            raise GeminiHatasi(-1, "Gemini boş yanıt verdi")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text.strip().strip('"“”«»').strip()

    def cevir(self, anahtar, model, english, baglam=(), terimler=""):
        model = (model or VARSAYILAN_MODEL).strip()
        denenecek = [model] + [m for m in YEDEK_MODELLER if m != model]
        son_hata = None
        for m in denenecek:
            try:
                return self._tek(anahtar, m, english, list(baglam), terimler), m
            except GeminiHatasi as e:
                son_hata = e
                # Model bulunamadıysa sıradaki modeli dene; başka hatada dur.
                if e.kod == 404 or (e.kod == 400 and "model" in str(e).lower() and "not" in str(e).lower()):
                    continue
                raise
        raise son_hata

    def _tek(self, anahtar, model, english, baglam, terimler):
        dus = model not in self._dusunmesiz
        try:
            return self._cagir(anahtar, model, self.istek_govdesi(english, baglam, terimler, model, dus))
        except GeminiHatasi as e:
            if dus and e.kod == 400 and "thinking" in str(e).lower():
                self._dusunmesiz.add(model)
                return self._cagir(anahtar, model, self.istek_govdesi(english, baglam, terimler, model, False))
            raise
