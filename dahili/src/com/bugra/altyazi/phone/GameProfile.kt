package com.bugra.altyazi.phone

/** Desteklenen oyunlar: altyazı yeri, Gemini'ye oyun bilgisi, çevrilmeyecek adlar ve oyuna özel okuyucular. */
enum class GameProfile(
    val id: String,
    val title: String,
    val roiTop: Int,
    val roiBottom: Int,
    /** Gemini'ye verilen oyun ve üslup notu. */
    val note: String,
    /** Çevrilmeden kalacak adlar (satır satır). */
    val terms: String,
    /** GTA 6 oyun içi telefon ve harita kartı okuyucusu. */
    val gtaPhone: Boolean,
    /** Menü/görev balonlarında okunmayacak sabit arayüz köşeleri (sol, üst, sağ, alt; 0–1). */
    val hudZones: List<FloatArray>,
) {
    GTA6(
        "gta6", "GTA 6", 72, 96,
        "Oyun: GTA 6 (Vice City, Leonida; Lucia ve Jason). Doğal Türk sokak dili, yerinde küfür.",
        Glossary.DEFAULT, true,
        listOf(floatArrayOf(0f, 0.70f, 0.24f, 1f), floatArrayOf(0.72f, 0.84f, 1f, 1f), floatArrayOf(0.78f, 0f, 1f, 0.12f)),
    ),
    GTA5(
        "gta5", "GTA V", 74, 96,
        "Oyun: GTA V (Los Santos, Blaine County; Michael, Franklin, Trevor). Doğal Türk sokak ve çete dili, yerinde küfür.",
        """Michael
Franklin
Trevor
Lamar
Lester
Jimmy
Tracey
Amanda
Chop
Ron
Wade
Simeon
Devin Weston
Los Santos
Blaine County
Sandy Shores
Paleto Bay
Vinewood
Grove Street
Mount Chiliad
LSPD
FIB
IAA
Merryweather
Ammu-Nation
Los Santos Customs
Ballas
Families
Vagos
Lost MC""", false,
        listOf(floatArrayOf(0f, 0.70f, 0.24f, 1f), floatArrayOf(0.72f, 0.84f, 1f, 1f), floatArrayOf(0.80f, 0f, 1f, 0.14f)),
    ),
    COD(
        "cod", "Call of Duty", 70, 93,
        "Oyun: Call of Duty. Askerî operasyon ve telsiz dili: kısa, net, emir kipinde. Rütbeleri ve askerî terimleri Türk Silahlı Kuvvetleri'nde kullanıldığı gibi yaz (Sergeant=Çavuş, Captain=Yüzbaşı, Lieutenant=Teğmen, Colonel=Albay, General=General). Sokak argosu yok ama askerlerin küfürlerini yumuşatma.",
        """Price
Soap
Ghost
Gaz
Roach
Shepherd
Makarov
Laswell
Farah
Alex
Nikolai
Graves
Kate Laswell
Task Force 141
Shadow Company
KorTac
Konni
Al-Qatala
Warzone
Verdansk
Urzikstan
Al Mazrah
Zakhaev
Black Ops
Mason
Woods
Hudson
Adler""", false,
        listOf(floatArrayOf(0f, 0f, 0.22f, 0.30f), floatArrayOf(0.74f, 0.82f, 1f, 1f), floatArrayOf(0.80f, 0f, 1f, 0.12f)),
    ),
    BATTLEFIELD(
        "bf", "Battlefield", 70, 93,
        "Oyun: Battlefield. Askerî savaş ve telsiz dili: kısa, net, emir kipinde. Rütbeleri ve askerî terimleri Türk Silahlı Kuvvetleri'ndeki karşılıklarıyla yaz. Sokak argosu yok ama askerlerin küfürlerini yumuşatma.",
        """Dagger
Murphy
Haynes
Mackay
Kimble
Irish
Recker
Pac
Pax Armata
NATO
Conquest
Breakthrough
Rush
Portal
Hazard Zone
Squad""", false,
        listOf(floatArrayOf(0f, 0f, 0.22f, 0.30f), floatArrayOf(0.74f, 0.82f, 1f, 1f)),
    ),
    OTHER(
        "other", "Diğer", 72, 96,
        "Oyun: bir video oyunu. Karakterin konuşma tarzına uygun, doğal ve akıcı Türkçe.",
        "", false,
        emptyList(),
    );

    companion object {
        fun of(id: String?): GameProfile = entries.firstOrNull { it.id == id } ?: GTA6
        val current: GameProfile get() = of(Prefs.game)
    }
}
