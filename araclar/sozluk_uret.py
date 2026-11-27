"""Çevirix çevrimdışı sokak sözlüğü üreticisi.

Kullanım:  python araclar/sozluk_uret.py
dahili/assets/sokak_sozlugu.json dosyasındaki elle yazılmış kalıpları korur (üzerine yazmaz),
aşağıdaki listelerden on binlerce yeni kalıp üretip aynı dosyaya ekler.
Anahtarlar Çevirix'in kendi anahtar fonksiyonuyla (pc/cevirix/sozluk.py) üretilir, yani
telefon ve PC sürümü bu kalıpları birebir bulur.

Tüm replikler özgün ve kalıp cümlelerdir (oyun senaryolarından alıntı yoktur); GTA, Red Dead,
Call of Duty, Battlefield, Mafia, Watch Dogs, Far Cry, Spider-Man, The Last of Us, Cyberpunk,
yarış ve spor oyunlarında sık görülen görev, telsiz, menü ve sokak konuşması tiplerini kapsar.
"""
import json
import os
import sys

BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
sys.path.insert(0, BURA)
sys.path.insert(0, os.path.join(KOK, "pc"))

from tr import Ad, Fiil, buyuk, soru, u2, u4  # noqa: E402
from cevirix.sozluk import Sozluk  # noqa: E402
import elle  # noqa: E402

DOSYA = os.path.join(KOK, "dahili", "assets", "sokak_sozlugu.json")

# =====================================================================================
# FİİL ÖBEKLERİ  (İngilizce yalın hal, Türkçe emir kipi)
# =====================================================================================
FIILLER = [
    ("go", "git"), ("leave", "ayrıl"), ("go home", "eve git"), ("go back", "geri dön"),
    ("turn back", "geri dön"), ("get in the car", "arabaya bin"), ("get out of the car", "arabadan in"),
    ("get in the truck", "kamyona bin"), ("get in the van", "minibüse bin"), ("get on the bike", "motora bin"),
    ("get off the bike", "motordan in"), ("get on the horse", "ata bin"), ("get in the boat", "tekneye bin"),
    ("get in the chopper", "helikoptere bin"), ("get out of here", "buradan çık"),
    ("get away from here", "buradan uzaklaş"), ("run", "koş"), ("hide", "saklan"), ("wait here", "burada bekle"),
    ("stay here", "burada kal"), ("stay in the car", "arabada kal"), ("come back", "geri gel"),
    ("come here", "buraya gel"), ("come inside", "içeri gel"), ("move", "hareket et"),
    ("calm down", "sakinleş"), ("relax", "rahatla"), ("shut up", "sus"), ("be quiet", "sessiz ol"),
    ("be careful", "dikkatli ol"), ("talk to him", "onunla konuş"), ("talk to her", "onunla konuş"),
    ("talk to them", "onlarla konuş"), ("call the police", "polisi ara"), ("call him", "onu ara"),
    ("call her", "onu ara"), ("call an ambulance", "ambulans çağır"), ("call a taxi", "taksi çağır"),
    ("find him", "onu bul"), ("find her", "onu bul"), ("find them", "onları bul"), ("find it", "onu bul"),
    ("find the money", "parayı bul"), ("get the money", "parayı al"), ("count the money", "parayı say"),
    ("hide the money", "parayı sakla"), ("split the money", "parayı paylaş"),
    ("give him the money", "parayı ona ver"), ("kill him", "onu öldür"), ("kill her", "onu öldür"),
    ("kill them", "onları öldür"), ("take him out", "onu indir"), ("take them out", "onları indir"),
    ("shoot him", "onu vur"), ("shoot them", "onları vur"), ("shoot the tires", "lastiklere ateş et"),
    ("open fire", "ateş aç"), ("stop him", "onu durdur"), ("stop them", "onları durdur"),
    ("catch him", "onu yakala"), ("catch them", "onları yakala"), ("chase him", "onu kovala"),
    ("lose the cops", "polisleri ek"), ("lose them", "onları ek"), ("lose the police", "polisi ek"),
    ("check it out", "bir bak"), ("look around", "etrafa bak"), ("search the car", "arabayı ara"),
    ("search the house", "evi ara"), ("search the body", "cesedi ara"), ("open the door", "kapıyı aç"),
    ("close the door", "kapıyı kapat"), ("break the door", "kapıyı kır"), ("kick the door", "kapıyı tekmele"),
    ("open the safe", "kasayı aç"), ("crack the safe", "kasayı kır"), ("open the trunk", "bagajı aç"),
    ("grab the bag", "çantayı kap"), ("drop the gun", "silahı bırak"), ("put the gun down", "silahı indir"),
    ("reload", "şarjör değiştir"), ("fix the car", "arabayı tamir et"), ("steal a car", "bir araba çal"),
    ("steal that car", "o arabayı çal"), ("drive", "sür"), ("drive faster", "daha hızlı sür"),
    ("slow down", "yavaşla"), ("speed up", "hızlan"), ("park the car", "arabayı park et"),
    ("fill up the tank", "depoyu doldur"), ("change clothes", "kıyafet değiştir"),
    ("take a shower", "duş al"), ("get some sleep", "biraz uyu"), ("get some rest", "biraz dinlen"),
    ("get something to eat", "bir şeyler atıştır"), ("get a drink", "bir şey iç"),
    ("see a doctor", "doktora görün"), ("think about it", "bunu düşün"), ("talk about it", "bunu konuş"),
    ("tell him", "ona söyle"), ("tell her", "ona söyle"), ("tell them", "onlara söyle"),
    ("tell the truth", "doğruyu söyle"), ("trust him", "ona güven"), ("trust them", "onlara güven"),
    ("help him", "ona yardım et"), ("help her", "ona yardım et"), ("help them", "onlara yardım et"),
    ("save her", "onu kurtar"), ("save him", "onu kurtar"), ("save them", "onları kurtar"),
    ("protect her", "onu koru"), ("protect him", "onu koru"), ("work", "çalış"),
    ("make some money", "biraz para kazan"), ("make a deal", "anlaşma yap"), ("sell the car", "arabayı sat"),
    ("buy a gun", "bir silah al"), ("buy some ammo", "biraz mermi al"), ("buy a car", "bir araba al"),
    ("pick him up", "onu al"), ("pick her up", "onu al"), ("pick up the package", "paketi al"),
    ("deliver the package", "paketi teslim et"), ("drop off the package", "paketi bırak"),
    ("get rid of the car", "arabadan kurtul"), ("get rid of the body", "cesetten kurtul"),
    ("get rid of the gun", "silahtan kurtul"), ("ditch the car", "arabayı bir yere bırak"),
    ("burn it", "onu yak"), ("burn it down", "orayı yak"), ("blow it up", "onu havaya uçur"),
    ("plant the bomb", "bombayı yerleştir"), ("cut the power", "elektriği kes"),
    ("hack the system", "sistemi hackle"), ("hack the camera", "kamerayı hackle"),
    ("take a picture", "fotoğraf çek"), ("record this", "bunu kaydet", "kayded"),
    ("climb up", "yukarı tırman"), ("jump", "atla"), ("swim", "yüz"), ("land the plane", "uçağı indir"),
    ("take off", "havalan"), ("go upstairs", "yukarı çık"), ("go downstairs", "aşağı in"),
    ("get to the roof", "çatıya çık"), ("take cover", "siper al"), ("get to cover", "siper al"),
    ("fall back", "geri çekil"), ("back off", "geri çekil"), ("push forward", "ilerle"),
    ("move up", "ilerle"), ("flank them", "onları yandan sar"), ("hold this position", "burayı tut"),
    ("defend the point", "noktayı savun"), ("call in an airstrike", "hava saldırısı iste"),
    ("lay low", "bir süre ortadan kaybol"), ("disappear", "ortadan kaybol"), ("dance", "dans et"),
    ("celebrate", "kutla"), ("get drunk", "sarhoş ol"), ("wake up", "uyan"), ("get dressed", "giyin"),
    ("pack up", "toparlan"), ("pull over", "kenara çek"), ("turn around", "geri dön"),
    ("turn left", "sola dön"), ("turn right", "sağa dön"), ("go straight", "düz git"),
    ("hit the gas", "gaza bas"), ("hit the brakes", "frene bas"), ("ram them", "onlara çarp"),
    ("run them off the road", "onları yoldan çıkar"), ("get closer", "yaklaş"), ("catch up", "yetiş"),
    ("get ahead of them", "onları geç"), ("do it", "bunu yap"), ("do this", "bunu yap"),
    ("finish it", "bunu bitir"), ("finish the job", "işi bitir"), ("end this", "bu işi bitir"),
    ("fix this", "bunu düzelt"), ("deal with it", "bununla ilgilen"), ("handle it", "hallet", "halled"),
    ("take care of it", "hallet", "halled"), ("forget about it", "bunu unut"), ("check the map", "haritaya bak"),
    ("answer the phone", "telefonu aç"),
    ("text him", "ona mesaj at"), ("send the location", "konumu gönder"), ("meet him", "onunla buluş"),
    ("meet them", "onlarla buluş"), ("see him", "onu gör"), ("ask him", "ona sor"), ("ask her", "ona sor"),
    ("pay the debt", "borcu öde"), ("pay the rent", "kirayı öde"), ("pay him", "ona parasını ver"),
    ("get the car", "arabayı al"), ("get the keys", "anahtarları al"),
    ("find the keys", "anahtarları bul"), ("find a way out", "bir çıkış yolu bul"),
    ("find a car", "bir araba bul"), ("find a place to hide", "saklanacak bir yer bul"),
    ("rob the bank", "bankayı soy"), ("rob the store", "dükkanı soy"), ("rob him", "onu soy"),
    ("break in", "içeri dal"), ("sneak in", "gizlice içeri gir"), ("get inside", "içeri gir"),
    ("go inside", "içeri gir"), ("go outside", "dışarı çık"), ("get out", "dışarı çık"),
    ("get away", "kaç"), ("escape", "kaç"), ("leave town", "şehri terk et"),
    ("leave the city", "şehirden ayrıl"), ("go to Vice City", "Vice City'ye git"),
    ("go to the hospital", "hastaneye git"), ("go to the police", "polise git"),
    ("go to the safehouse", "güvenli eve git"), ("go to the airport", "havalimanına git"),
    ("go to the club", "kulübe git"), ("go to the beach", "plaja git"), ("go to work", "işe git"),
    ("go to sleep", "uyu"), ("go to jail", "hapse gir"), ("get a job", "bir iş bul"),
    ("quit", "bırak"), ("start over", "baştan başla"), ("try again", "tekrar dene"),
    ("keep going", "devam et"), ("keep driving", "sürmeye devam et"), ("keep looking", "aramaya devam et"),
    ("stop the car", "arabayı durdur"), ("stop the truck", "kamyonu durdur"), ("follow that car", "o arabayı takip et"),
    ("follow him", "onu takip et"), ("follow them", "onları takip et"), ("follow the car", "arabayı takip et"),
    ("watch him", "onu izle"), ("watch the door", "kapıyı gözle"), ("keep an eye on him", "onu gözle"),
    ("wait for him", "onu bekle"), ("wait for them", "onları bekle"), ("wait for the signal", "işareti bekle"),
    ("get ready", "hazırlan"), ("gear up", "teçhizat kuşan"), ("suit up", "hazırlan"),
    ("load the truck", "kamyonu yükle"), ("unload the truck", "kamyonu boşalt"), ("tie him up", "onu bağla"),
    ("untie him", "onun iplerini çöz"), ("let him go", "onu bırak"), ("let her go", "onu bırak"),
    ("let them go", "onları bırak"), ("search him", "üstünü ara"), ("arrest him", "onu tutukla"),
    ("cuff him", "onu kelepçele"), ("knock him out", "onu bayılt"), ("wake him up", "onu uyandır"),
    ("bring him here", "onu buraya getir"), ("bring her here", "onu buraya getir"),
    ("bring the car around", "arabayı getir"), ("bring the money", "parayı getir"),
    ("take the money", "parayı al"), ("take the car", "arabayı al"), ("take the bag", "çantayı al"),
    ("take him home", "onu eve götür"), ("take her home", "onu eve götür"),
    ("take him to the hospital", "onu hastaneye götür"), ("drive me home", "beni eve bırak"),
    ("drop me off", "beni bırak"), ("pick me up", "beni al"), ("wait for me", "beni bekle"),
    ("cover me", "beni koru"), ("help me", "bana yardım et"), ("call me", "beni ara"),
    ("trust me", "bana güven"), ("follow me", "beni takip et"), ("listen to me", "beni dinle"),
    ("look at me", "bana bak"), ("talk to me", "benimle konuş"), ("come with me", "benimle gel"),
]
# "me" içeren öbekler yalnız "sen" öznesi olan kalıplarda kullanılır
def _benli(en):
    return " me" in en or en.endswith(" me")


# (İngilizce biçimler, Türkçe üretici, ben-li öbeklere uygun mu)
F = lambda *a: a  # noqa: E731
FIIL_KALIPLARI = [
    (["{vp}"], lambda f: f.emir() + ".", True),
    (["Don't {vp}", "Do not {vp}"], lambda f: f.olumsuz_emir() + ".", True),
    (["Let's {vp}", "Let us {vp}"], lambda f: f.istek("biz") + ".", False),
    (["I'm going to {vp}", "I'll {vp}", "Imma {vp}"], lambda f: f.gelecek("ben") + ".", False),
    (["We're going to {vp}", "We'll {vp}"], lambda f: f.gelecek("biz") + ".", False),
    (["I need to {vp}", "I have to {vp}", "I gotta {vp}"],
     lambda f: f.isim("mem") + " lazım.", False),
    (["We need to {vp}", "We have to {vp}", "We gotta {vp}"],
     lambda f: f.isim("memiz") + " lazım.", False),
    (["You need to {vp}", "You have to {vp}", "You gotta {vp}"],
     lambda f: f.isim("men") + " lazım.", True),
    (["Can you {vp}?", "Could you {vp}?"], lambda f: f.yeterlik("sen?") + "?", True),
    (["I can't {vp}", "I cannot {vp}"], lambda f: f.olumsuz_yeterlik("ben") + ".", False),
    (["You can't {vp}", "You cannot {vp}"], lambda f: f.olumsuz_yeterlik("sen") + ".", True),
    (["I want to {vp}", "I wanna {vp}"], lambda f: f.mastar() + " istiyorum.", False),
    (["I don't want to {vp}", "I don't wanna {vp}"], lambda f: f.mastar() + " istemiyorum.", False),
    (["Do you want to {vp}?", "You wanna {vp}?"],
     lambda f: f.mastar() + " ister misin?", True),
    (["Are you going to {vp}?"], lambda f: f.gelecek("sen?") + "?", True),
    (["Did you {vp}?"], lambda f: f.gecmis("sen?") + "?", True),
    (["We should {vp}", "Maybe we should {vp}"], lambda f: f.sart("biz") + " iyi olur.", False),
    (["You should {vp}", "You better {vp}"],
     lambda f: f.sart("sen") + " iyi olur.", True),
    (["I'm trying to {vp}", "I am trying to {vp}"], lambda f: f.isim("meye") + " çalışıyorum!", False),
    (["I told you to {vp}"], lambda f: "Sana " + f.isim("meni") + " söyledim.", True),
    (["Are you ready to {vp}?"],
     lambda f: f.isim("meye") + " hazır mısın?", True),
    (["We need to {vp} now"],
     lambda f: "Hemen " + f.isim("memiz") + " lazım.", False),
    (["Just {vp}"], lambda f: f.emir() + " işte!", True),
    (["{vp} now"], lambda f: "Hemen " + f.emir() + "!", True),
    (["You don't have to {vp}"], lambda f: f.isim("mene") + " gerek yok.", True),
]


# =====================================================================================
# YERLER
# =====================================================================================
def Y(en, tr, **k):
    return Ad("the " + en, tr, **k)


YERLER = [
    Y("bank", "banka"), Y("hospital", "hastane"), Y("police station", "polis karakolu", iyelik=True),
    Y("safehouse", "güvenli ev"), Y("hideout", "sığınak", yum="sığınağ"), Y("airport", "havalimanı", iyelik=True),
    Y("docks", "rıhtım"), Y("port", "liman"), Y("harbor", "liman"), Y("marina", "marina"),
    Y("beach", "plaj"), Y("club", "kulüp", yum="kulüb"), Y("nightclub", "gece kulübü", iyelik=True),
    Y("bar", "bar"), Y("strip club", "striptiz kulübü", iyelik=True), Y("casino", "kumarhane"),
    Y("hotel", "otel"), Y("motel", "motel"), Y("apartment", "daire"), Y("house", "ev"),
    Y("mansion", "malikane"), Y("garage", "garaj"), Y("warehouse", "depo"), Y("factory", "fabrika"),
    Y("gas station", "benzinlik", yum="benzinliğ"), Y("store", "dükkan"), Y("shop", "dükkan"),
    Y("liquor store", "içki dükkanı", iyelik=True), Y("gun store", "silah dükkanı", iyelik=True),
    Y("ammo shop", "silah dükkanı", iyelik=True), Y("pawn shop", "rehinci dükkanı", iyelik=True),
    Y("jewelry store", "kuyumcu"), Y("supermarket", "süpermarket"), Y("mall", "alışveriş merkezi", iyelik=True),
    Y("diner", "lokanta"), Y("restaurant", "restoran"), Y("burger place", "burgerci"),
    Y("parking lot", "otopark"), Y("parking garage", "katlı otopark"), Y("rooftop", "çatı"),
    Y("roof", "çatı"), Y("alley", "ara sokak", yum="ara sokağ"), Y("street", "sokak", yum="sokağ"),
    Y("highway", "otoyol"), Y("freeway", "otoyol"), Y("bridge", "köprü"), Y("tunnel", "tünel"),
    Y("train station", "tren istasyonu", iyelik=True), Y("bus station", "otogar"),
    Y("subway", "metro"), Y("airfield", "pist"), Y("helipad", "helikopter pisti", iyelik=True),
    Y("hangar", "hangar"), Y("military base", "askeri üs"), Y("base", "üs"), Y("prison", "hapishane"),
    Y("jail", "hapishane"), Y("courthouse", "adliye"), Y("city hall", "belediye binası", iyelik=True),
    Y("church", "kilise"), Y("cemetery", "mezarlık", yum="mezarlığ"), Y("park", "park"),
    Y("stadium", "stadyum"), Y("gym", "spor salonu", iyelik=True), Y("school", "okul"),
    Y("office", "ofis"), Y("building", "bina"), Y("tower", "kule"), Y("construction site", "inşaat"),
    Y("junkyard", "hurdalık", yum="hurdalığ"), Y("scrapyard", "hurdalık", yum="hurdalığ"),
    Y("chop shop", "parçacı"), Y("mod shop", "modifiye dükkanı", iyelik=True), Y("car wash", "oto yıkama"),
    Y("trailer park", "karavan parkı", iyelik=True), Y("trailer", "karavan"), Y("farm", "çiftlik", yum="çiftliğ"),
    Y("ranch", "çiftlik", yum="çiftliğ"), Y("barn", "ahır"), Y("swamp", "bataklık", yum="bataklığ"),
    Y("island", "ada"), Y("lighthouse", "deniz feneri", iyelik=True), Y("pier", "iskele"),
    Y("yacht", "yat"), Y("boat", "tekne"), Y("ship", "gemi"), Y("lab", "laboratuvar"),
    Y("drug lab", "uyuşturucu laboratuvarı", iyelik=True), Y("stash house", "zula evi", iyelik=True),
    Y("trap house", "torbacı evi", iyelik=True), Y("meeting point", "buluşma noktası", iyelik=True),
    Y("drop-off point", "teslim noktası", iyelik=True), Y("drop point", "teslim noktası", iyelik=True),
    Y("pickup point", "alım noktası", iyelik=True), Y("checkpoint", "kontrol noktası", iyelik=True),
    Y("rendezvous point", "buluşma noktası", iyelik=True), Y("extraction point", "tahliye noktası", iyelik=True),
    Y("landing zone", "iniş bölgesi", iyelik=True), Y("objective", "hedef"), Y("target area", "hedef bölge"),
    Y("vault", "kasa dairesi", iyelik=True), Y("server room", "sunucu odası", iyelik=True),
    Y("control room", "kontrol odası", iyelik=True), Y("basement", "bodrum"), Y("attic", "çatı katı", iyelik=True),
    Y("elevator", "asansör"), Y("stairs", "merdiven"), Y("back door", "arka kapı"), Y("front door", "ön kapı"),
    Y("exit", "çıkış"), Y("entrance", "giriş"), Y("gate", "kapı"), Y("fence", "çit"), Y("wall", "duvar"),
    Y("tracks", "raylar"), Y("train yard", "tren deposu", iyelik=True), Y("power plant", "elektrik santrali", iyelik=True),
    Y("refinery", "rafineri"), Y("oil rig", "petrol platformu", iyelik=True), Y("dam", "baraj"),
    Y("mountain", "dağ"), Y("hill", "tepe"), Y("forest", "orman"), Y("woods", "orman"), Y("river", "nehir", yum="nehr"),
    Y("lake", "göl"), Y("cave", "mağara"), Y("desert", "çöl"), Y("canyon", "kanyon"), Y("camp", "kamp"),
    Y("village", "köy"), Y("town", "kasaba"), Y("saloon", "salon"), Y("sheriff's office", "şerif ofisi", iyelik=True),
    Y("train", "tren"), Y("stagecoach", "posta arabası", iyelik=True), Y("motorcycle club", "motor kulübü", iyelik=True),
    Y("tattoo parlor", "dövmeci"), Y("barber shop", "berber"), Y("clothing store", "giyim mağazası", iyelik=True),
    Y("pharmacy", "eczane"), Y("clinic", "klinik", yum="kliniğ"), Y("morgue", "morg"),
    Y("studio", "stüdyo"), Y("penthouse", "çatı katı dairesi", iyelik=True), Y("pool", "havuz"),
    Y("crime scene", "olay yeri", iyelik=True), Y("safe zone", "güvenli bölge"), Y("bunker", "sığınak", yum="sığınağ"),
    Y("waypoint", "işaretli nokta"), Y("marker", "işaret"), Y("blip", "işaret"), Y("yellow marker", "sarı işaret"),
    Y("location", "konum"), Y("destination", "varış noktası", iyelik=True), Y("finish line", "bitiş çizgisi", iyelik=True),
    Y("starting line", "başlangıç çizgisi", iyelik=True), Y("next checkpoint", "sonraki kontrol noktası", iyelik=True),
    Ad("Vice City", "Vice City", ozel=True, okunus="siti"), Ad("Leonida", "Leonida", ozel=True),
    Ad("Port Gellhorn", "Port Gellhorn", ozel=True, okunus="gelhorn"), Ad("Ambrosia", "Ambrosia", ozel=True),
    Ad("Grassrivers", "Grassrivers", ozel=True, okunus="grasrivırs"), Ad("the Leonida Keys", "Leonida Keys", ozel=True, okunus="kiys"),
    Ad("Mount Kalaga", "Mount Kalaga", ozel=True), Ad("Los Santos", "Los Santos", ozel=True),
    Ad("Liberty City", "Liberty City", ozel=True, okunus="siti"), Ad("Blaine County", "Blaine County", ozel=True, okunus="kaunti"),
    Ad("Sandy Shores", "Sandy Shores", ozel=True, okunus="şors"), Ad("Paleto Bay", "Paleto Bay", ozel=True, okunus="bey"),
    Ad("Saint Denis", "Saint Denis", ozel=True, okunus="deni"), Ad("Valentine", "Valentine", ozel=True, okunus="velentayn"),
    Ad("Night City", "Night City", ozel=True, okunus="siti"), Ad("Manhattan", "Manhattan", ozel=True),
]

YER_KALIPLARI = [
    (["Go to {X}", "Head to {X}", "Get to {X}"], lambda a: f"{a.ine} git."),
    (["Drive to {X}"], lambda a: f"{a.ine} sür."),
    (["Return to {X}", "Go back to {X}"], lambda a: f"{a.ine} geri dön."),
    (["Take him to {X}"], lambda a: f"Onu {a.ine} götür."),
    (["Take me to {X}"], lambda a: f"Beni {a.ine} götür."),
    (["Take the car to {X}"], lambda a: f"Arabayı {a.ine} götür."),
    (["Deliver the package to {X}", "Take the package to {X}"], lambda a: f"Paketi {a.ine} teslim et."),
    (["Meet me at {X}"], lambda a: f"{a.inde} buluşalım."),
    (["I'll meet you at {X}", "See you at {X}"], lambda a: f"{a.inde} görüşürüz."),
    (["Meet your contact at {X}", "Meet the contact at {X}"], lambda a: f"Bağlantınla {a.inde} buluş."),
    (["I'm at {X}", "I am at {X}"], lambda a: f"{a.bulunma_kisi('ben')}."),
    (["I'm going to {X}", "I'm on my way to {X}"], lambda a: f"{a.ine} gidiyorum."),
    (["Let's go to {X}", "Let's head to {X}"], lambda a: f"{a.ine} gidelim."),
    (["Where's {X}?", "Where is {X}?"], lambda a: f"{a.yalin} nerede?"),
    (["Wait at {X}"], lambda a: f"{a.inde} bekle."),
    (["Enter {X}", "Get inside {X}"], lambda a: f"{a.ine} gir."),
    (["Leave {X}", "Get out of {X}"], lambda a: f"{a.inden} çık."),
    (["Find {X}", "Locate {X}"], lambda a: f"{a.ini} bul."),
    (["You're near {X}", "You are close to {X}"], lambda a: f"{a.ine} yakınsın."),
    (["{X} is closed"], lambda a: f"{buyuk(a.yalin)} kapalı."),
    (["{X} is on fire", "{X} is burning"], lambda a: f"{buyuk(a.yalin)} yanıyor!"),
    (["Go to {X} and wait", "Head to {X} and wait"], lambda a: f"{a.ine} git ve bekle."),
]

# =====================================================================================
# ARAÇLAR
# =====================================================================================
def A(en, tr, an="a", **k):
    return Ad("the " + en, tr, an=f"{an} {en}", **k)


ARACLAR = [
    A("car", "araba"), A("truck", "kamyon"), A("van", "minibüs"), A("bike", "motor"),
    A("motorcycle", "motosiklet", yum="motosiklet"), A("boat", "tekne"), A("speedboat", "sürat teknesi", iyelik=True),
    A("plane", "uçak", yum="uçağ"), A("jet", "jet"), A("chopper", "helikopter"), A("helicopter", "helikopter"),
    A("police car", "polis arabası", iyelik=True), A("cop car", "polis arabası", iyelik=True),
    A("ambulance", "ambulans", an="an"), A("fire truck", "itfaiye aracı", iyelik=True), A("tank", "tank"),
    A("jet ski", "jet ski", okunus="ski"), A("bus", "otobüs"), A("taxi", "taksi"), A("cab", "taksi"),
    A("limo", "limuzin"), A("sports car", "spor araba"), A("getaway car", "kaçış arabası", iyelik=True),
    A("armored truck", "zırhlı kamyon", an="an"), A("tow truck", "çekici"), A("garbage truck", "çöp kamyonu", iyelik=True),
    A("pickup", "kamyonet"), A("SUV", "cip", an="an"), A("horse", "at"), A("wagon", "at arabası", iyelik=True),
    A("stagecoach", "posta arabası", iyelik=True), A("train", "tren"), A("tractor", "traktör"),
    A("semi", "tır"), A("trailer", "dorse"), A("quad", "ATV", ozel=True, okunus="tivi"), A("buggy", "buggy", okunus="bagi"),
    A("airboat", "bataklık teknesi", iyelik=True, an="an"), A("yacht", "yat"), A("submarine", "denizaltı", iyelik=True),
    A("drone", "dron"), A("rc car", "oyuncak araba"), A("muscle car", "muscle araba"),
    A("lowrider", "lowrider", okunus="lovraydır"), A("convertible", "üstü açık araba"), A("delivery van", "kargo minibüsü", iyelik=True),
    A("ice cream truck", "dondurma kamyonu", iyelik=True, an="an"), A("motorbike", "motor"), A("dirt bike", "kros motoru", iyelik=True),
    A("scooter", "skuter"), A("bicycle", "bisiklet", yum="bisiklet"), A("gunship", "savaş helikopteri", iyelik=True),
    A("APC", "zırhlı araç", an="an", yum="arac"), A("humvee", "askeri cip"),
    A("enemy vehicle", "düşman aracı", iyelik=True, an="an"), A("target vehicle", "hedef araç"),
    A("convoy", "konvoy"), A("escort", "eskort"),
]

ARAC_KALIPLARI = [
    (["Get in {X}", "Get into {X}"], lambda a: f"{a.ine} bin."),
    (["Get out of {X}", "Exit {X}"], lambda a: f"{a.inden} in."),
    (["Steal {X}"], lambda a: f"{a.ini} çal."),
    (["Find {X}", "Locate {X}"], lambda a: f"{a.ini} bul."),
    (["Destroy {X}", "Take out {X}"], lambda a: f"{a.ini} yok et."),
    (["Follow {X}"], lambda a: f"{a.ini} takip et."),
    (["Chase {X}", "Chase down {X}"], lambda a: f"{a.ini} kovala."),
    (["Stop {X}"], lambda a: f"{a.ini} durdur."),
    (["Lose {X}"], lambda a: f"{a.ini} ek."),
    (["Don't damage {X}", "Do not damage {X}"], lambda a: f"{a.ini} hasara uğratma."),
    (["{X} is getting away"], lambda a: f"{buyuk(a.yalin)} kaçıyor!"),
    (["{X} got away"], lambda a: f"{buyuk(a.yalin)} kaçtı."),
    (["{X} is badly damaged", "{X} is heavily damaged"], lambda a: f"{buyuk(a.yalin)} ağır hasar aldı."),
    (["{X} was destroyed"], lambda a: f"{buyuk(a.yalin)} yok edildi."),
    (["You destroyed {X}", "You wrecked {X}"], lambda a: f"{a.ini} mahvettin."),
    (["You lost {X}"], lambda a: f"{a.ini} kaçırdın."),
    (["Where's {X}?", "Where is {X}?"], lambda a: f"{buyuk(a.yalin)} nerede?"),
    (["{X} incoming"], lambda a: f"{buyuk(a.yalin)} geliyor!"),
    (["Don't lose {X}"], lambda a: f"{a.ini} kaçırma!"),
    (["Enemy {N}"], lambda a: f"Düşman {a.yalin}!"),
]
ARAC_KALIPLARI_BIR = [  # "a car" biçimi
    (["Steal {A}", "Jack {A}", "Grab {A}"], lambda a: f"Bir {a.yalin} çal."),
    (["Find {A}", "Get {A}"], lambda a: f"Bir {a.yalin} bul."),
    (["I need {A}"], lambda a: f"Bana bir {a.yalin} lazım."),
    (["We need {A}"], lambda a: f"Bize bir {a.yalin} lazım."),
    (["Get me {A}", "Find me {A}"], lambda a: f"Bana bir {a.yalin} bul."),
    (["Get in {A}"], lambda a: f"Bir {a.ine} bin."),
]

# =====================================================================================
# KİŞİLER / HEDEFLER
# =====================================================================================
KISILER = [
    Y("target", "hedef"), Y("guard", "koruma"), Y("guards", "korumalar"), Y("driver", "şoför"),
    Y("cop", "polis"), Y("cops", "polisler"), Y("police", "polis"), Y("witness", "tanık", yum="tanığ"),
    Y("informant", "muhbir"), Y("snitch", "ispiyoncu"), Y("rat", "köstebek", yum="köstebeğ"),
    Y("dealer", "torbacı"), Y("boss", "patron"), Y("bodyguard", "koruma"), Y("bodyguards", "korumalar"),
    Y("hostage", "rehine"), Y("hostages", "rehineler"), Y("gang members", "çete üyeleri", iyelik=True),
    Y("bikers", "motorcular"), Y("pilot", "pilot"), Y("sniper", "keskin nişancı"), Y("agent", "ajan"),
    Y("agents", "ajanlar"), Y("detective", "dedektif"), Y("suspect", "şüpheli"), Y("prisoner", "mahkum"),
    Y("scientist", "bilim insanı", iyelik=True), Y("doctor", "doktor"), Y("lawyer", "avukat"),
    Y("mayor", "belediye başkanı", iyelik=True), Y("senator", "senatör"), Y("shooter", "saldırgan"),
    Y("thief", "hırsız"), Y("robbers", "soyguncular"), Y("soldiers", "askerler"), Y("enemies", "düşmanlar"),
    Y("enemy", "düşman"), Y("infected", "enfekteler"), Y("zombies", "zombiler"), Y("bounty", "ödüllü kaçak", yum="ödüllü kaçağ"),
    Y("outlaw", "kanun kaçağı", iyelik=True), Y("sheriff", "şerif"), Y("deputies", "şerif yardımcıları", iyelik=True),
    Y("gunmen", "silahlı adamlar"), Y("mechanic", "tamirci"), Y("bartender", "barmen"), Y("girl", "kız"),
    Y("kid", "çocuk", yum="çocuğ"), Y("old man", "yaşlı adam"), Y("woman", "kadın"), Y("guy", "adam"),
    Y("man", "adam"), Y("courier", "kurye"), Y("buyer", "alıcı"), Y("seller", "satıcı"), Y("contact", "bağlantı"),
    Y("hacker", "hacker", okunus="hakır"), Y("crew", "ekip", yum="ekib"), Y("team", "ekip", yum="ekib"),
    Y("VIP", "VIP", ozel=True, okunus="viaypi"), Y("convoy", "konvoy"), Y("cartel", "kartel"),
    Y("gang leader", "çete lideri", iyelik=True), Y("leader", "lider"), Y("officer", "memur"),
    Y("security guard", "güvenlik görevlisi", iyelik=True), Y("security", "güvenlik"), Y("crowd", "kalabalık", yum="kalabalığ"),
    Y("victim", "kurban"), Y("victims", "kurbanlar"), Y("survivors", "hayatta kalanlar"), Y("survivor", "hayatta kalan"),
    Y("mercenaries", "paralı askerler"), Y("pursuers", "takipçiler"), Y("assassin", "suikastçı"),
    Y("FBI agents", "FBI ajanları", iyelik=True), Y("SWAT team", "SWAT ekibi", iyelik=True), Y("bank manager", "banka müdürü", iyelik=True),
    Y("cashier", "kasiyer"), Y("clerk", "tezgahtar"), Y("photographer", "fotoğrafçı"), Y("reporter", "muhabir"),
]

KISI_KALIPLARI = [
    (["Kill {X}", "Eliminate {X}"], lambda a: f"{a.ini} öldür."),
    (["Take out {X}"], lambda a: f"{a.ini} etkisiz hale getir."),
    (["Follow {X}"], lambda a: f"{a.ini} takip et."),
    (["Catch {X}"], lambda a: f"{a.ini} yakala."),
    (["Find {X}", "Look for {X}"], lambda a: f"{a.ini} bul."),
    (["Protect {X}"], lambda a: f"{a.ini} koru."),
    (["Rescue {X}", "Save {X}"], lambda a: f"{a.ini} kurtar."),
    (["Talk to {X}", "Speak to {X}"], lambda a: f"{a.ile} konuş."),
    (["Lose {X}"], lambda a: f"{a.ini} ek."),
    (["Don't kill {X}", "Do not kill {X}"], lambda a: f"{a.ini} öldürme."),
    (["Don't let {X} escape", "Don't let {X} get away"], lambda a: f"{a.ini} kaçırma!"),
    (["{X} is getting away"], lambda a: f"{buyuk(a.yalin)} kaçıyor!"),
    (["{X} got away"], lambda a: f"{buyuk(a.yalin)} kaçtı."),
    (["{X} is dead"], lambda a: f"{buyuk(a.yalin)} öldü."),
    (["{X} was killed"], lambda a: f"{buyuk(a.yalin)} öldürüldü."),
    (["{X} spotted you"], lambda a: f"{buyuk(a.yalin)} seni gördü!"),
    (["{X} is down"], lambda a: f"{buyuk(a.yalin)} etkisiz hale getirildi."),
    (["{X} is coming"], lambda a: f"{buyuk(a.yalin)} geliyor!"),
    (["You killed {X}"], lambda a: f"{a.ini} öldürdün."),
    (["You lost {X}"], lambda a: f"{a.ini} kaçırdın."),
    (["Where's {X}?", "Where is {X}?"], lambda a: f"{buyuk(a.yalin)} nerede?"),
    (["I see {X}"], lambda a: f"{buyuk(a.ini)} görüyorum."),
    (["I lost {X}"], lambda a: f"{buyuk(a.ini)} kaybettim."),
]

# =====================================================================================
# EŞYALAR
# =====================================================================================
ESYALAR = [
    Y("money", "para"), Y("cash", "nakit"), Y("bag", "çanta"), Y("briefcase", "evrak çantası", iyelik=True),
    Y("package", "paket"), Y("drugs", "uyuşturucu"), Y("product", "mal"), Y("stash", "zula"),
    Y("gun", "silah"), Y("weapons", "silahlar"), Y("guns", "silahlar"), Y("ammo", "mermi"), Y("phone", "telefon"),
    Y("laptop", "laptop"), Y("hard drive", "hard disk", okunus="disk"), Y("files", "dosyalar"),
    Y("documents", "belgeler"), Y("keys", "anahtarlar"), Y("key", "anahtar"), Y("keycard", "kart anahtar"),
    Y("access card", "giriş kartı", iyelik=True), Y("car keys", "araba anahtarları", iyelik=True), Y("diamonds", "elmaslar"),
    Y("gold", "altın"), Y("jewelry", "mücevherler"), Y("painting", "tablo"), Y("bomb", "bomba"),
    Y("explosives", "patlayıcılar"), Y("detonator", "fünye"), Y("tracker", "takip cihazı", iyelik=True),
    Y("camera", "kamera"), Y("evidence", "kanıt"), Y("photos", "fotoğraflar"), Y("USB drive", "USB bellek", yum="USB belleğ"),
    Y("flash drive", "flash bellek", yum="flash belleğ"), Y("codes", "kodlar"), Y("map", "harita"), Y("radio", "telsiz"),
    Y("medkit", "ilk yardım çantası", iyelik=True), Y("supplies", "malzemeler"), Y("fuel", "yakıt"), Y("gas can", "benzin bidonu", iyelik=True),
    Y("parts", "parçalar"), Y("crate", "sandık", yum="sandığ"), Y("crates", "sandıklar"), Y("shipment", "sevkiyat"),
    Y("cargo", "kargo"), Y("loot", "ganimet"), Y("chip", "çip"), Y("sample", "numune"), Y("vaccine", "aşı"),
    Y("antidote", "panzehir"), Y("necklace", "kolye"), Y("watch", "saat", okunus="saet"), Y("ring", "yüzük", yum="yüzüğ"),
    Y("wallet", "cüzdan"), Y("badge", "rozet"), Y("ID", "kimlik", yum="kimliğ"), Y("passport", "pasaport"),
    Y("ticket", "bilet"), Y("bottle", "şişe"), Y("cigarettes", "sigaralar"), Y("lighter", "çakmak", yum="çakmağ"),
    Y("flashlight", "fener"), Y("rope", "halat"), Y("shovel", "kürek", yum="küreğ"), Y("crowbar", "levye"),
    Y("toolbox", "alet çantası", iyelik=True), Y("lockpick", "maymuncuk", yum="maymuncuğ"), Y("knife", "bıçak", yum="bıçağ"),
    Y("bat", "sopa"), Y("rifle", "tüfek", yum="tüfeğ"), Y("shotgun", "pompalı"), Y("pistol", "tabanca"),
    Y("sniper rifle", "keskin nişancı tüfeği", iyelik=True), Y("RPG", "RPG", ozel=True, okunus="arpici"),
    Y("grenade", "bomba"), Y("grenades", "bombalar"), Y("mask", "maske"), Y("masks", "maskeler"),
    Y("uniform", "üniforma"), Y("disguise", "kılık", yum="kılığ"), Y("body", "ceset", yum="cesed"), Y("bodies", "cesetler"),
    Y("tape", "kaset"), Y("recording", "kayıt", yum="kayd"), Y("contract", "sözleşme"), Y("deed", "tapu"),
    Y("ledger", "defter"), Y("money bag", "para çantası", iyelik=True), Y("duffel bag", "spor çantası", iyelik=True),
    Y("artifact", "eser"), Y("relic", "kalıntı"), Y("treasure", "hazine"), Y("chest", "sandık", yum="sandığ"),
    Y("safe", "kasa"), Y("intel", "istihbarat"), Y("blueprints", "planlar"), Y("plans", "planlar"),
    Y("hostage", "rehine"), Y("dog", "köpek", yum="köpeğ"), Y("horse", "at"), Y("car", "araba"),
    Y("cocaine", "kokain"), Y("weed", "ot"), Y("pills", "haplar"), Y("meth", "met"), Y("cigars", "purolar"),
    Y("wine", "şarap"), Y("beer", "bira"), Y("food", "yemek"), Y("water", "su", okunus="su"), Y("battery", "pil"),
    Y("generator", "jeneratör"), Y("fuse", "sigorta"), Y("valve", "vana"), Y("switch", "şalter"), Y("lever", "kol"),
]

ESYA_KALIPLARI = [
    (["Get {X}", "Grab {X}", "Take {X}"], lambda a: f"{a.ini} al."),
    (["Find {X}", "Look for {X}"], lambda a: f"{a.ini} bul."),
    (["Steal {X}"], lambda a: f"{a.ini} çal."),
    (["Hide {X}"], lambda a: f"{a.ini} sakla."),
    (["Drop {X}"], lambda a: f"{a.ini} bırak!"),
    (["Give me {X}"], lambda a: f"{a.ini} bana ver."),
    (["Bring {X}"], lambda a: f"{a.ini} getir."),
    (["Deliver {X}"], lambda a: f"{a.ini} teslim et."),
    (["Where's {X}?", "Where is {X}?"], lambda a: f"{buyuk(a.yalin)} nerede?"),
    (["Do you have {X}?", "You got {X}?"], lambda a: f"{buyuk(a.yalin)} sende mi?"),
    (["I got {X}", "I have {X}"], lambda a: f"{buyuk(a.yalin)} bende."),
    (["We got {X}", "We have {X}"], lambda a: f"{buyuk(a.yalin)} bizde."),
    (["Put {X} in the car"], lambda a: f"{a.ini} arabaya koy."),
    (["Put {X} in the trunk"], lambda a: f"{a.ini} bagaja koy."),
    (["Don't lose {X}"], lambda a: f"{a.ini} kaybetme."),
    (["I lost {X}"], lambda a: f"{buyuk(a.ini)} kaybettim."),
    (["{X} is missing"], lambda a: f"{buyuk(a.yalin)} ortada yok!"),
    (["I need {X}"], lambda a: f"Bana {a.yalin} lazım."),
    (["Get {X} back"], lambda a: f"{a.ini} geri al."),
    (["{X} acquired", "{X} collected"], lambda a: f"{buyuk(a.yalin)} alındı."),
    (["{X} destroyed"], lambda a: f"{buyuk(a.yalin)} yok edildi."),
]

# =====================================================================================
# TELSİZ / ÇATIŞMA
# =====================================================================================
BIRIMLER = [("enemy", "düşman"), ("sniper", "keskin nişancı"), ("tank", "tank"), ("chopper", "helikopter"),
            ("helicopter", "helikopter"), ("shooter", "saldırgan"), ("gunman", "silahlı adam"), ("RPG", "RPG"),
            ("heavy", "ağır zırhlı"), ("drone", "dron"), ("vehicle", "araç"), ("infantry", "piyade"),
            ("cop", "polis"), ("hostile", "düşman"), ("enemies", "düşmanlar"), ("contact", "temas"),
            ("machine gunner", "makineli tüfekçi"), ("armor", "zırhlı araç"), ("jet", "jet"), ("mortar", "havan")]
YONLER = [("on the left", "solda"), ("on the right", "sağda"), ("left", "solda"), ("right", "sağda"),
          ("behind us", "arkamızda"), ("behind you", "arkanda"), ("behind", "arkada"), ("up ahead", "ileride"),
          ("ahead", "ileride"), ("on the roof", "çatıda"), ("on the rooftop", "çatıda"), ("upstairs", "üst katta"),
          ("downstairs", "alt katta"), ("in the building", "binada"), ("in the window", "pencerede"),
          ("on the bridge", "köprüde"), ("on the hill", "tepede"), ("in the trees", "ağaçların arasında"),
          ("in the woods", "ormanda"), ("near the car", "arabanın yanında"), ("north", "kuzeyde"), ("south", "güneyde"),
          ("east", "doğuda"), ("west", "batıda"), ("in the air", "havada"), ("on the ground", "yerde"),
          ("at the gate", "kapıda"), ("in the alley", "ara sokakta"), ("across the street", "karşı sokakta"),
          ("on the balcony", "balkonda"), ("in the tower", "kulede"), ("on our six", "arkamızda"),
          ("on your six", "arkanda"), ("on the flank", "kanatta"), ("everywhere", "her yerde")]
TEKIL_DEGIL = {"enemies", "infantry", "armor", "contact", "hostile"}
SAATLER = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
SAAT_TR = ["bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on", "on bir", "on iki"]
SAAT_TR_DE = ["birde", "ikide", "üçte", "dörtte", "beşte", "altıda", "yedide", "sekizde", "dokuzda", "onda",
              "on birde", "on ikide"]


# =====================================================================================
# TUŞ İPUÇLARI  (Press X to ...)
# =====================================================================================
TUSLAR = ["X", "O", "L1", "L2", "R1", "R2"]
TUS_TR = {"Cross": "Çarpı", "Circle": "Daire", "Square": "Kare", "Triangle": "Üçgen", "Touchpad": "Dokunmatik Yüzey",
          "Create": "Oluştur", "Options": "Options", "Share": "Share"}
EYLEMLER = [
    ("enter the vehicle", "araca bin"), ("exit the vehicle", "araçtan in"), ("enter vehicle", "araca bin"),
    ("aim", "nişan al"), ("shoot", "ateş et"), ("fire", "ateş et"), ("reload", "şarjör değiştir"), ("jump", "zıpla"),
    ("sprint", "koş"), ("run", "koş"), ("crouch", "eğil"), ("take cover", "siper al"), ("interact", "etkileşime geç"),
    ("open the door", "kapıyı aç"), ("open", "aç"), ("pick up", "yerden al"), ("talk", "konuş"), ("skip", "geç"),
    ("skip cutscene", "ara sahneyi geç"), ("continue", "devam et"), ("open the map", "haritayı aç"),
    ("open the phone", "telefonu aç"), ("use the phone", "telefonu kullan"), ("switch weapons", "silah değiştir"),
    ("change weapon", "silah değiştir"), ("use the medkit", "ilk yardım çantasını kullan"), ("heal", "iyileş"),
    ("hail a taxi", "taksi çağır"), ("call a taxi", "taksi çağır"), ("start the engine", "motoru çalıştır"),
    ("turn on the radio", "radyoyu aç"), ("change radio station", "radyo kanalını değiştir"),
    ("honk", "korna çal"), ("use the handbrake", "el frenini çek"), ("handbrake", "el frenini çek"),
    ("look behind", "arkana bak"), ("look back", "arkana bak"), ("open the trunk", "bagajı aç"), ("search", "ara"),
    ("loot", "ganimeti topla"), ("loot the body", "cesedi yağmala"), ("climb", "tırman"), ("dive", "dal"),
    ("hack", "hackle"), ("lockpick", "kilidi aç"), ("pick the lock", "kilidi aç"), ("open the inventory", "envanteri aç"),
    ("open the menu", "menüyü aç"), ("pause", "oyunu duraklat"), ("accept", "kabul et"), ("accept the mission", "görevi kabul et"),
    ("start the mission", "görevi başlat"), ("start", "başla"), ("retry", "tekrar dene"), ("buy", "satın al"), ("sell", "sat"),
    ("confirm", "onayla"), ("cancel", "iptal et"), ("go back", "geri dön"), ("back", "geri dön"), ("select", "seç"),
    ("zoom", "yakınlaştır"), ("zoom in", "yakınlaştır"), ("toggle the flashlight", "feneri aç kapat"),
    ("whistle", "ıslık çal"), ("mount the horse", "ata bin"), ("mount", "ata bin"), ("dismount", "attan in"),
    ("call your horse", "atını çağır"), ("switch character", "karakter değiştir"), ("use special ability", "özel yeteneği kullan"),
    ("take a photo", "fotoğraf çek"), ("set a waypoint", "rota işareti koy"), ("place a waypoint", "rota işareti koy"),
    ("drop", "yere bırak"), ("throw", "fırlat"), ("throw a grenade", "bomba fırlat"), ("melee", "yakın dövüş yap"),
    ("punch", "yumruk at"), ("kick", "tekme at"), ("block", "blok yap"), ("dodge", "kaç"), ("roll", "yuvarlan"),
    ("parry", "savuştur"), ("counter", "karşılık ver"), ("grab", "yakala"), ("surrender", "teslim ol"),
    ("hands up", "ellerini kaldır"), ("answer", "cevap ver"), ("answer the call", "aramayı cevapla"),
    ("hang up", "telefonu kapat"), ("reject", "reddet"), ("decline", "reddet"), ("respawn", "yeniden doğ"),
    ("revive", "canlandır"), ("ping", "işaretle"), ("mark", "işaretle"), ("mark target", "hedefi işaretle"),
    ("scan", "tara"), ("use", "kullan"), ("equip", "kuşan"), ("inspect", "incele"), ("read", "oku"),
    ("examine", "incele"), ("sit", "otur"), ("sleep", "uyu"), ("save", "kaydet", "kayded"), ("wait", "bekle"),
    ("rotate", "döndür"), ("view", "görüntüle"), ("change camera", "kamerayı değiştir"), ("cinematic camera", "sinematik kamerayı aç"),
    ("hold breath", "nefesini tut"), ("steady aim", "nişanı sabitle"), ("free aim", "serbest nişan al"),
    ("lock on", "hedefe kilitlen"), ("shoot from vehicle", "araçtan ateş et"), ("lean", "eğil"),
    ("vault", "üstünden atla"), ("slide", "kay"), ("boost", "nitro kullan"), ("use nitro", "nitro kullan"),
    ("drift", "drift yap"), ("brake", "fren yap"), ("accelerate", "gaza bas"), ("reverse", "geri git"),
    ("open garage", "garajı aç"), ("customize", "özelleştir"), ("upgrade", "geliştir"), ("craft", "üret"),
    ("fast travel", "hızlı seyahat et"), ("track", "takip et"), ("track mission", "görevi takip et"),
    ("join", "katıl"), ("invite", "davet et"), ("ready up", "hazır ol"), ("quit", "çık"), ("exit", "çık"),
]


def tus_tr(t):
    return TUS_TR.get(t, t)


# =====================================================================================
# SAYILAR
# =====================================================================================
SAYI_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
SAYI_TR = ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on", "on bir", "on iki",
           "on üç", "on dört", "on beş", "on altı", "on yedi", "on sekiz", "on dokuz", "yirmi"]


def ana():
    s = Sozluk(DOSYA)
    with open(DOSYA, encoding="utf-8") as f:
        root = json.load(f)
    eski = dict(root["phrases"])
    yeni = {}
    sayac = {}

    def ekle(en, tr, grup):
        k = s._key(en)
        if not k or k in eski or k in yeni:
            return
        yeni[k] = tr
        sayac[grup] = sayac.get(grup, 0) + 1

    # --- elle yazılmış özgün replikler
    for en, tr in elle.KALIPLAR:
        ekle(en, tr, "elle")

    # --- fiil kalıpları
    for satir in FIILLER:
        f = Fiil(satir[0], satir[1], satir[2] if len(satir) > 2 else None)
        benli = _benli(f.en)
        for bicimler, uret, ben_uygun in FIIL_KALIPLARI:
            if benli and not ben_uygun:
                continue
            if bicimler[0] == "Go {vp}" and f.en.split()[0] in ("go", "get", "come", "leave"):
                continue
            tr = buyuk(uret(f))
            for b in bicimler:
                ekle(b.replace("{vp}", f.en), tr, "fiil")

    # --- yerler
    for a in YERLER:
        for bicimler, uret in YER_KALIPLARI:
            tr = buyuk(uret(a))
            for b in bicimler:
                ekle(b.replace("{X}", a.en), tr, "yer")

    # --- araçlar
    for a in ARACLAR:
        isim = a.en[4:]
        for bicimler, uret in ARAC_KALIPLARI:
            tr = buyuk(uret(a))
            for b in bicimler:
                ekle(b.replace("{X}", a.en).replace("{N}", isim), tr, "arac")
        for bicimler, uret in ARAC_KALIPLARI_BIR:
            tr = buyuk(uret(a))
            for b in bicimler:
                ekle(b.replace("{A}", a.an), tr, "arac")

    # --- kişiler
    for a in KISILER:
        for bicimler, uret in KISI_KALIPLARI:
            tr = buyuk(uret(a))
            for b in bicimler:
                ekle(b.replace("{X}", a.en), tr, "kisi")

    # --- eşyalar
    for a in ESYALAR:
        for bicimler, uret in ESYA_KALIPLARI:
            tr = buyuk(uret(a))
            for b in bicimler:
                ekle(b.replace("{X}", a.en), tr, "esya")

    # --- telsiz
    for ben, btr in BIRIMLER:
        for yen, ytr in YONLER:
            ekle(f"{ben} {yen}!", f"{buyuk(btr)} {ytr}!", "telsiz")
            if ben not in TEKIL_DEGIL:
                art = "an" if ben[0] in "aeiou" else "a"
                ekle(f"There's {art} {ben} {yen}!", f"{buyuk(ytr)} bir {btr} var!", "telsiz")
                ekle(f"I see {art} {ben} {yen}", f"{buyuk(ytr)} bir {btr} görüyorum.", "telsiz")
            ekle(f"Watch out, {ben} {yen}!", f"Dikkat, {ytr} {btr} var!", "telsiz")
        for i, (sa, st) in enumerate(zip(SAATLER, SAAT_TR_DE)):
            ekle(f"{ben} at {sa} o'clock!", f"{buyuk(btr)} saat {st}!", "telsiz")
            ekle(f"{ben} at {i + 1} o'clock!", f"{buyuk(btr)} saat {st}!", "telsiz")
            ekle(f"{ben}, {sa} o'clock!", f"{buyuk(btr)}, saat {st}!", "telsiz")
        if ben in ("contact", "hostile"):
            continue
        ekle(f"{ben} down!", f"{buyuk(btr)} indirildi!", "telsiz")
        ekle(f"{ben} spotted!", f"{buyuk(btr)} görüldü!", "telsiz")
        ekle(f"{ben} incoming!", f"{buyuk(btr)} geliyor!", "telsiz")
        ekle(f"{ben} eliminated", f"{buyuk(btr)} yok edildi.", "telsiz")
    for yen, ytr in YONLER:
        ekle(f"Contact {yen}!", f"Temas, {ytr}!", "telsiz")
        ekle(f"Movement {yen}", f"{buyuk(ytr)} hareket var.", "telsiz")
        ekle(f"Enemies {yen}!", f"Düşmanlar {ytr}!", "telsiz")
        ekle(f"They're {yen}!", f"{buyuk(ytr)}l{u2(ytr)}r!", "telsiz")
        ekle(f"Watch {yen}!", f"{buyuk(ytr)} dikkat!", "telsiz")
        ekle(f"Clear {yen}", f"{buyuk(ytr)} temiz.", "telsiz")
        ekle(f"Shots fired {yen}!", f"{buyuk(ytr)} ateş açıldı!", "telsiz")

    # --- tuş ipuçları
    for satir in EYLEMLER:
        f = Fiil(satir[0], satir[1], satir[2] if len(satir) > 2 else None)
        m = f.mastar()
        for t in TUSLAR:
            tt = tus_tr(t)
            ekle(f"Press {t} to {f.en}", f"{buyuk(m)} için {tt} tuşuna bas.", "tus")
            ekle(f"Hold {t} to {f.en}", f"{buyuk(m)} için {tt} tuşunu basılı tut.", "tus")
        ekle(f"Press to {f.en}", f"{buyuk(m)} için bas.", "tus")
        ekle(f"Hold to {f.en}", f"{buyuk(m)} için basılı tut.", "tus")

    # --- sayılar
    for n in range(1, 31):
        ekle(f"Wave {n}", f"Dalga {n}", "sayi")
        ekle(f"Round {n}", f"Raunt {n}", "sayi")
        ekle(f"Level {n}", f"Seviye {n}", "sayi")
        ekle(f"Chapter {n}", f"Bölüm {n}", "sayi")
        ekle(f"Mission {n}", f"Görev {n}", "sayi")
        ekle(f"Rank {n}", f"Rütbe {n}", "sayi")
        ekle(f"Day {n}", f"Gün {n}", "sayi")
        ekle(f"Wave {n} complete", f"Dalga {n} tamamlandı", "sayi")
        ekle(f"Level {n} complete", f"Seviye {n} tamamlandı", "sayi")
        ekle(f"Reached level {n}", f"Seviye {n} oldun", "sayi")
        ekle(f"{n} kills", f"{n} leş", "sayi")
        ekle(f"{n} enemies remaining", f"{n} düşman kaldı", "sayi")
        ekle(f"{n} enemies left", f"{n} düşman kaldı", "sayi")
        ekle(f"{n} targets remaining", f"{n} hedef kaldı", "sayi")
        ekle(f"{n} seconds left", f"{n} saniye kaldı", "sayi")
        ekle(f"{n} minutes left", f"{n} dakika kaldı", "sayi")
        ekle(f"You have {n} seconds", f"{n} saniyen var.", "sayi")
        ekle(f"You have {n} minutes", f"{n} dakikan var.", "sayi")
        ekle(f"Kill {n} enemies", f"{n} düşman öldür.", "sayi")
        ekle(f"Collect {n} packages", f"{n} paket topla.", "sayi")
        ekle(f"Wanted level {n}", f"Aranma seviyesi {n}", "sayi")
        ekle(f"Respawn in {n}", f"{n} saniye içinde yeniden doğacaksın", "sayi")
        ekle(f"Respawning in {n}", f"{n} saniye içinde yeniden doğuluyor", "sayi")
        ekle(f"{n} players", f"{n} oyuncu", "sayi")
        ekle(f"Player {n}", f"Oyuncu {n}", "sayi")
        ekle(f"Part {n}", f"Kısım {n}", "sayi")
        ekle(f"Episode {n}", f"Bölüm {n}", "sayi")
    for n in range(2, 9):
        for m in range(1, n + 1):
            ekle(f"Lap {m} of {n}", f"Tur {m}/{n}", "sayi")
            ekle(f"Lap {m}/{n}", f"Tur {m}/{n}", "sayi")
            ekle(f"Position {m} of {n}", f"Sıralama {m}/{n}", "sayi")
            ekle(f"{m} of {n}", f"{m}/{n}", "sayi")
    for n in range(1, len(SAYI_EN)):
        e, t = SAYI_EN[n], SAYI_TR[n]
        ekle(f"You have {e} seconds", f"{buyuk(t)} saniyen var.", "sayi")
        ekle(f"You have {e} minutes", f"{buyuk(t)} dakikan var.", "sayi")
        ekle(f"You've got {e} minutes", f"{buyuk(t)} dakikan var.", "sayi")
        ekle(f"{e} minutes", f"{buyuk(t)} dakika.", "sayi")
        ekle(f"{e} more minutes", f"{buyuk(t)} dakika daha.", "sayi")
        ekle(f"Give me {e} minutes", f"Bana {t} dakika ver.", "sayi")
        ekle(f"I need {e} minutes", f"{buyuk(t)} dakikaya ihtiyacım var.", "sayi")
        ekle(f"{e} seconds", f"{buyuk(t)} saniye.", "sayi")
        ekle(f"{e} guys", f"{buyuk(t)} kişi.", "sayi")
        ekle(f"There are {e} of them", f"{buyuk(t)} kişiler.".replace(f"{buyuk(t)} kişiler.", f"Onlar {t} kişi."), "sayi")
        ekle(f"{e} grand", f"{buyuk(t)} bin dolar.", "sayi")
        ekle(f"{e} hundred bucks", f"{buyuk(t)} yüz dolar.".replace("Bir yüz", "Yüz"), "sayi")
        ekle(f"{e} million dollars", f"{buyuk(t)} milyon dolar.", "sayi")
        ekle(f"{e} thousand dollars", f"{buyuk(t)} bin dolar.".replace("Bir bin", "Bin"), "sayi")

    root["phrases"] = {**eski, **yeni}
    root["version"] = max(2, int(root.get("version", 1)) + 1) if len(yeni) else root.get("version", 1)
    with open(DOSYA, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write(f'"version": {root["version"]},\n')
        f.write('"phrases": {\n')
        satirlar = [json.dumps(k, ensure_ascii=False) + ": " + json.dumps(v, ensure_ascii=False)
                    for k, v in root["phrases"].items()]
        f.write(",\n".join(satirlar))
        f.write("\n},\n")
        for anahtar in ("pre", "post", "vocatives"):
            f.write(f'"{anahtar}": ' + json.dumps(root[anahtar], ensure_ascii=False, indent=0) +
                    ("" if anahtar == "vocatives" else ",") + "\n")
        f.write("}\n")
    print("Eski:", len(eski), " Yeni:", len(yeni), " Toplam:", len(root["phrases"]))
    for g, n in sorted(sayac.items(), key=lambda x: -x[1]):
        print(f"  {g:8s} {n}")


if __name__ == "__main__":
    ana()
