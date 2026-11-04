// Keep graph labels as readable as the rest of the interface.
Chart.defaults.font.size = 18;

// Garde l’ordre du menu à jour même avec un modèle HTML déjà en cache.
$('#menu_button_info').insertAfter('#menu_button_multi');

// Older pages cached by the running server receive the same separate scroll area.
const captureContainer = document.querySelector('.cardre_captures');
if (captureContainer && !captureContainer.querySelector('.capture-scroll')) {
    const scrollArea = document.createElement('div');
    scrollArea.className = 'capture-scroll';
    Array.from(captureContainer.children).forEach(function(child) {
        if (!child.classList.contains('capture-toolbar')) scrollArea.appendChild(child);
    });
    captureContainer.appendChild(scrollArea);
}

$( document ).ready(function() {
    setTimeout(function() { 
        init();
    }, 500);
  
});

      function loaderInit(){  
        // $(".sprit div").fadeOut();
        $(".sprit .main").fadeOut();
        containeur_size = $(".sprit").parent().width();
        $(".img_eldenring").css("display","flex");
        val = 100;
        max_val =16352; // LARGEUR DE L'IMAGE

        diviseur = 23
        one_frame = max_val / diviseur;
        new_width = Math.ceil((containeur_size - one_frame) * diviseur) + max_val + (one_frame * 2);
      
       
        const myloader = setInterval(loader, 60);
            function loader() {
                
                if(val >= -1){
                $(".sprit").css("background-position", val+"% 50%").css("background-size", new_width+"px 100% ");
                val -= 4.54;
                    if(val > 50 && $(".nav_menu").css("opacity") != "1" && $(".nav_menu").css("opacity") != 1){
                    $(".nav_menu").css("opacity","1");  
                  
                   
                    }
                } else {
            
                clearInterval(myloader);
                $(".sprit").remove();
                
                }
            }
            
}






var notify_top = 0;

let previewImageRequest = 0;
let previewPollGeneration = 0;
let previewPollTimer = null;

function updateLivePreview(capture, detected) {
    const box = document.querySelector('.live-preview');
    const image = box && box.querySelector('img');
    if (!image) return;
    image.dataset.detected = detected ? '1' : '0';
    if (!image.dataset.previewBound) {
        image.dataset.previewBound = '1';
        image.addEventListener('load', function() {
            box.classList.toggle('has-image', image.dataset.detected === '1' && image.naturalWidth > 0);
        });
        image.addEventListener('error', function() { box.classList.remove('has-image'); });
    }
    if (!detected || !capture) {
        previewImageRequest++;
        box.classList.remove('has-image');
        return;
    }
    const source = 'data:image/jpg;base64,' + capture;
    if (image.getAttribute('src') === source && image.complete && image.naturalWidth > 0) {
        box.classList.add('has-image');
        return;
    }
    const request = ++previewImageRequest;
    const next = new Image();
    next.onload = function() {
        if (request === previewImageRequest && image.dataset.detected === '1') image.src = source;
    };
    next.onerror = function() {
        if (request === previewImageRequest) box.classList.remove('has-image');
    };
    next.src = source;
}

function stopPreviewPolling() {
    previewPollGeneration++;
    clearTimeout(previewPollTimer);
}

function startPreviewPolling() {
    stopPreviewPolling();
    const generation = previewPollGeneration;
    let revision = -1;
    let latestCapture = '';
    let lastDetected = null;
    async function poll() {
        let delay = 0;
        try {
            const params = new URLSearchParams({after:String(revision), wait:'1'});
            if (lastDetected !== null) params.set('detected', lastDetected ? '1' : '0');
            const response = await fetch('/live-preview?' + params.toString(), {cache:'no-store'});
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            if (generation !== previewPollGeneration) return;
            const detected = data.gameDetected === true;
            const changed = data.revision !== revision || detected !== lastDetected;
            revision = data.revision;
            if (data.capture !== null) latestCapture = data.capture;
            if (changed) updateLivePreview(latestCapture, detected);
            lastDetected = detected;
            delay = Number(data.retryAfter) || 0;
        } catch (_) { delay = 500; /* Keep the last frame during a brief connection failure. */ }
        if (generation === previewPollGeneration) previewPollTimer = setTimeout(poll, delay);
    }
    poll();
}

var runApp = setInterval(intervall, 3000);
clearInterval(runApp);
var interface_en = window.interface_en;
var interface_fr = window.interface_fr;
var interface_spa = window.interface_spa;
var interface_ita = window.interface_ita;
var interface_deu = window.interface_deu;
var interface_rus = window.interface_rus;
var interface_jap = window.interface_jap;
var interface_chi = window.interface_chi;
var interface_por = window.interface_por;
var interface_nld = window.interface_nld;

var interface_nor = window.interface_nor;
var interface_fin = window.interface_fin;
var interface_dan = window.interface_dan;
var interface_tur = window.interface_tur;
var interface_kor = window.interface_kor;
var interface_ell = window.interface_ell;
var interface_pol = window.interface_pol;
var interface_ces = window.interface_ces;
var interface_ron = window.interface_ron;
var interface_ara = window.interface_ara;
var interface_heb = window.interface_heb;
var interface_active = [""];



var text_en = ["Start", "Counter Off", "Stop", "Counter On", "Loading...", "Game detected", "Game not detected", "Commencing combat", "Combat ends in your victory", "Combat ends in your loss", "Victory", "Defeat", "The fight ends in a draw", "Egality"];
var text_fr = ["Start", "Détection désactivée", "Stop", "Détection activée", "Chargement...", "Jeu au premier plan", "Jeu non visible pour la capture", "Début du combat", "Vous remportez la victoire !", "Vous avez perdu", "Victory", "Defeat", "Le combat s\'achève par une égalité", "Egality"];
var text_spa = ["Inicio", "Contador desactivado", "Parar", "Contador activado", "Cargando...", "Juego detectado", "Juego no detectado", "Comenzando combate", "El combate termina con tu victoria", "El combate termina con tu derrota", "Victoria", "Derrota", "El combate termina en empate", "Igualdad"];
var text_ita = ["Inizio", "Contatore disattivato", "Stop", "Contatore attivato", "Caricamento...", "Gioco rilevato", "Gioco non rilevato", "Inizio combattimento", "Il combattimento termina con la tua vittoria", "Il combattimento termina con la tua sconfitta", "Vittoria", "Sconfitta", "Il combattimento finisce in pareggio", "Pareggio"];
var text_deu = ["Start", "Zähler aus", "Stop", "Zähler an", "Ladevorgang...", "Spiel erkannt", "Spiel nicht erkannt", "Beginn des Kampfes", "Kampf endet mit deinem Sieg", "Kampf endet mit deiner Niederlage", "Sieg", "Niederlage", "Das Spiel endet unentschieden", "Unentschieden"];
var text_rus = ["Старт", "Счетчик выключен", "Стоп", "Счетчик включен", "Загрузка...", "Игра обнаружена", "Игра не обнаружена", "Начало боя", "Бой заканчивается твоей победой", "Бой заканчивается твоим поражением", "Победа", "Поражение", "Бой заканчивается в ничью", "Ничья"];
var text_jap = ["スタート", "カウンター オフ", "ストップ", "カウンター オン", "ローディング中...", "ゲームが検出されました", "ゲームが検出されませんでした", "戦闘を開始します", "戦闘はあなたの勝利で終わりました", "戦闘はあなたの敗北で終わりました", "勝利", "敗北", "引き分けで戦闘は終了しました"];
var text_chi = ["开始", "计数器关闭", "停止", "计数器打开", "载入中...", "检测到游戏", "未检测到游戏", "开始战斗", "战斗以你的胜利结束", "战斗以你的失败结束", "胜利", "失败", "战斗以平局结束"];
var text_por = ["Começar", "Contador desligado", "Parar", "Contador ligado", "Carregando...", "Jogo detectado", "Jogo não detectado", "Iniciando combate", "Combate termina com sua vitória", "Combate termina com sua derrota", "Vitória", "Derrota", "O combate termina em empate"];
var text_nld = ["Start", "Teller Uit", "Stop", "Teller Aan", "Bezig met laden...", "Spel gedetecteerd", "Spel niet gedetecteerd", "Beginnen met vechten", "Gevecht eindigt in jouw overwinning", "Gevecht eindigt in jouw verlies", "Overwinning", "Nederlaag", "Het gevecht eindigt in een gelijkspel"];
var text_nor = ["Start", "Teller deaktivert", "Stopp", "Teller aktivert", "Laster...", "Spill oppdaget", "Spill ikke oppdaget", "Kampen startet", "Du vinner!" , "Du har tapt", "Seier", "Nederlag", "Kampen ender med uavgjort", "Likestilling"];
var text_fin = ["Aloita", "Laskuri Pois Päältä", "Pysäytä", "Laskuri Päällä", "Ladataan...", "Peli havaittu", "Peliä ei havaittu", "Aloita taistelu", "Taistelu päättyy voittoosi", "Taistelu päättyy tappioosi", "Voitto", "Tappio", "Taistelu päättyy tasapeliin"];
var text_dan = ["Start", "Tæller Fra", "Stop", "Tæller Til", "Indlæser...", "Spil fundet", "Spil ikke fundet", "Begynd kampen", "Kampen ender i din sejr", "Kampen ender i dit nederlag", "Sejr", "Nederlag", "Kampen ender uafgjort"];
var text_tur = ["Başla", "Sayaç Kapalı", "Durdur", "Sayaç Açık", "Yükleniyor...", "Oyun Algılandı", "Oyun Algılanmadı", "Savaşı Başlat", "Savaş senin zaferinle sona eriyor", "Savaş senin yenilginle sona eriyor", "Zafer", "Yenilgi", "Savaş beraberlikle sona eriyor"];
var text_kor = ["시작", "카운터 끄기", "정지", "카운터 켜기", "로딩 중...", "게임 감지됨", "게임 감지 안됨", "전투 시작", "전투 종료 - 당신의 승리", "전투 종료 - 당신의 패배", "승리", "패배", "전투는 무승부로 끝납니다"];
var text_ell = ["Έναρξη", "Απενεργοποίηση Μετρητή", "Διακοπή", "Ενεργοποίηση Μετρητή", "Φόρτωση...", "Το παιχνίδι ανιχνεύτηκε", "Το παιχνίδι δεν ανιχνεύτηκε", "Έναρξη μάχης", "Η μάχη τελειώνει με τη νίκη σας", "Η μάχη τελειώνει με την ήττα σας", "Νίκη", "Ήττα", "Η μάχη τελειώνει ισόπαλη"];
var text_pol = ["Start", "Wyłącz licznik", "Stop", "Włącz licznik", "Ładowanie...", "Wykryto grę", "Nie wykryto gry", "Rozpocznij walkę", "Walka kończy się twoim zwycięstwem", "Walka kończy się twoją porażką", "Zwycięstwo", "Porażka", "Walka kończy się remisem"];
var text_ces = ["Start", "Vypnout čítač", "Stop", "Zapnout čítač", "Načítání...", "Detekována hra", "Hra nenalezena", "Zahájit boj", "Boj končí vaším vítězstvím", "Boj končí vaší porážkou", "Vítězství", "Porážka", "Boj končí remízou"];
var text_ron = ["Start", "Dezactivare Contor", "Stop", "Activare Contor", "Se încarcă...", "Joc detectat", "Joc negăsit", "Pornire luptă", "Lupta se încheie cu victoria ta", "Lupta se încheie cu înfrângerea ta", "Victorie", "Înfrângere", "Lupta se încheie la egalitate"];
var text_ara = ["ابدأ", "إيقاف العداد", "توقف", "تشغيل العداد", "جارٍ التحميل...", "لعبة مكتشفة", "لم يتم اكتشاف اللعبة", "بدء المعركة", "تنتهي المعركة بفوزك", "تنتهي المعركة بخسارتك", "النصر", "الهزيمة", "تنتهي المعركة بالتعادل"];
var text_heb = ["התחלה", "כיבוי מונה", "עצירה", "הפעלת מונה", "טוען...", "זוהתה משחק", "לא זוהה משחק", "התחל קרב", "הקרב מסתיים בניצחונך", "הקרב מסתיים בהפסדך", "ניצחון", "הפסד", "הקרב מסתיים בתיקו"];
var text_active = [""];
var game_detection_state = false;
var steam_overlay_state = false;

function renderGameDetection() {
    const label = steam_overlay_state ? appT('steam_overlay_open', 'Overlay Steam ouvert') : (text_active[game_detection_state ? 5 : 6] || 'Jeu non visible pour la capture');
    const container = document.querySelector('.live b');
    if (!container) return;
    const text = document.createElement('span');
    text.className = 'game_detect';
    text.textContent = label + ' ';
    const indicator = document.createElement('span');
    indicator.className = game_detection_state ? 'live_on' : 'live_off';
    container.replaceChildren(text, indicator);
}



var day_eng= ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
var day_fra= ["lundi","mardi","merdredi", "jeudi", "vendredi", "samedi", "dimanche"];
var day_spa= ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
var day_ita= ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
var day_deu= ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
var day_rus= ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"];
var day_jap= ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"];
var day_chi= ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"];
var day_por = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"];
var day_nld = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"];
var day_nor = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];
var day_fin = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"];
var day_dan = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];
var day_tur = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"];
var day_kor = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"];
var day_ell = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"];
var day_pol = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"];
var day_ces = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"];
var day_ron = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"];
var day_ara = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"];
var day_heb = ["יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "יום שבת", "יום ראשון"];

var days_active = "";


function launchLanguages(language){
    if(language == "eng"){
        text_active = text_en;
        interface_active = interface_en;
        days_active = day_eng;
            $('#table_multi').DataTable().destroy();
            $('#table_multi').DataTable();
    }
    if(language == "fra"){
        text_active = text_fr
        interface_active = interface_fr;
        days_active = day_fra;
            $.getJSON("/static/table_fra.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "spa"){
        text_active = text_fr
        interface_active = interface_spa;
        days_active = day_spa;
            $.getJSON("/static/table_spa.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "ita"){
        text_active = text_ita
        interface_active = interface_ita;
        days_active = day_ita;
            $.getJSON("/static/table_ita.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "deu"){
        text_active = text_deu
        interface_active = interface_deu;
        days_active = day_deu;
            $.getJSON("/static/table_deu.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "rus"){
        text_active = text_rus
        interface_active = interface_rus;
        days_active = day_rus;
            $.getJSON("/static/table_rus.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "jap"){
        text_active = text_jap
        interface_active = interface_jap;
        days_active = day_jap;
            $.getJSON("/static/table_jap.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "chi"){
        text_active = text_chi
        interface_active = interface_chi;
        days_active = day_chi;
            $.getJSON("/static/table_chi.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "por"){
        text_active = text_por
        interface_active = interface_por;
        days_active = day_por;
            $.getJSON("/static/table_por.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "nld"){
        text_active = text_nld
        interface_active = interface_nld;
        days_active = day_nld;
            $.getJSON("/static/table_nld.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
 
    if(language == "nor"){
        text_active = text_nor
        interface_active = interface_nor;
        days_active = day_nor;
            $.getJSON("/static/table_nor.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "fin"){
        text_active = text_fin
        interface_active = interface_fin;
        days_active = day_fin;
            $.getJSON("/static/table_fin.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "dan"){
        text_active = text_dan
        interface_active = interface_dan;
        days_active = day_dan;
            $.getJSON("/static/table_dan.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "tur"){
        text_active = text_tur
        interface_active = interface_tur;
        days_active = day_tur;
            $.getJSON("/static/table_tur.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "kor"){
        text_active = text_kor
        interface_active = interface_kor;
        days_active = day_kor;
            $.getJSON("/static/table_kor.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "ell"){
        text_active = text_ell
        interface_active = interface_ell;
        days_active = day_ell;
            $.getJSON("/static/table_ell.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "pol"){
        text_active = text_pol
        interface_active = interface_pol;
        days_active = day_pol;
            $.getJSON("/static/table_pol.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "ces"){
        text_active = text_ces
        interface_active = interface_ces;
        days_active = day_ces;
            $.getJSON("/static/table_ces.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
  
    if(language == "ron"){
        text_active = text_ron
        interface_active = interface_ron;
        days_active = day_ron;
            $.getJSON("/static/table_ron.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "ara"){
        text_active = text_ara
        interface_active = interface_ara;
        days_active = day_ara;
            $.getJSON("/static/table_ara.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }
    if(language == "heb"){
        text_active = text_heb
        interface_active = interface_heb;
        days_active = day_heb;
            $.getJSON("/static/table_heb.json", function(data){
                    $('#table_multi').DataTable().destroy();
                    $('#table_multi').DataTable({
                        "language": data     
                    });      
            });
    }

    const localePack = window.ELDEN_UI_PACKS && window.ELDEN_UI_PACKS[language];
    if (localePack) {
        interface_active = localePack.legacy;
        text_active = localePack.counter.slice();
        text_active[1] = localePack.modern.detection_disabled;
        text_active[3] = localePack.modern.detection_enabled;
        const formatter = new Intl.DateTimeFormat(localePack.html_lang, {weekday:'long', timeZone:'UTC'});
        days_active = Array.from({length:7}, (_, i) => formatter.format(new Date(Date.UTC(2024, 0, 1 + i))));
    }
    if(interface_active == undefined){
        text_active = text_en;
        interface_active = interface_en;
        days_active = day_eng;
            $('#table_multi').DataTable().destroy();
            $('#table_multi').DataTable();
    }
    $(".languages span").addClass("hide");
    $(".languages span[lang="+language+"]").removeClass("hide");
    $(".victory").text(interface_active[0]);
    $(".defeat").text(interface_active[1]);
    $(".egality").text(interface_active[2]);
    $("#menu_button_captures").text(interface_active[3]);
    $("#menu_button_settings").text(interface_active[4]);
    $(".presentation .p-1").html(interface_active[5]);
    $(".presentation .p-2").html(interface_active[6]);
    $(".no_capture").text(interface_active[7]);
    $(".pseudo_cadre label").text(interface_active[10]);
    $(".descri_profil .d-1").html(interface_active[11]);
    $(".panel_pseudo .d-2").html(interface_active[12]);
    $(".panel_pseudo .d-3").html(interface_active[13]);
    $(".panel_pseudo .d-4").html(interface_active[14]);
    $(".panel_pseudo #save_pseudo").text(interface_active[15]);
    $(".panel_img label").text(interface_active[16]);
    $(".panel_img #capture_img_profil").text(interface_active[17]);
    $(".panel_img .dp-1").html(interface_active[18]);
   
    $(".panel_user #sync_multi").text(interface_active[21]);
    $(".panel_user table .t-1").text(interface_active[22]);
    $(".panel_user table .t-2").text(interface_active[23]);
    $(".panel_user table .t-3").text(interface_active[24]);
    $(".btn-chart button[mode='24h']").text(interface_active[25]);
    $(".btn-chart button[mode='48h']").text(interface_active[26]);
    $(".btn-chart button[mode='7j']").text(interface_active[27]);
    $(".btn-chart button[mode='30j']").text(interface_active[28]);
    $(".btn-chart button[mode='all']").text(interface_active[29]);
    $(".panel_user table .tb-1").text(interface_active[30]);
    $(".panel_user table .tb-2").text(interface_active[31]);
    $(".panel_user table .tb-3").text(interface_active[32]);
    $(".panel_user table .tb-4").text(interface_active[33]);
    $(".panel_user table .tb-5").text(interface_active[34]);
    $(".panel_user table .tb-6").text(interface_active[35]);
    $(".panel_user table .tb-7").text(interface_active[36]);
    $(".panel_user table .tb-8").text(interface_active[37]);
    $(".panel_user table .tb-9").text(interface_active[38]);
    $(".panel_user table .tb-10").text(interface_active[39]);
    $(".panel_user table .tb-11").text(interface_active[40]);
    $("#start").text($("#start").hasClass("active") ? text_active[2] : text_active[0]);
    $(".monitor-starting").text(text_active[4]);
    $(".language_tr").text(interface_active[42]);
    $(".language_tr").text(interface_active[42]);
    $(".autoStrat_tr").text(interface_active[43]);
    $(".auto_start span[auto_start='false']").text(interface_active[44]);
    $(".auto_start span[auto_start='true']").text(interface_active[45]);
    $(".reEcr_tr").text(interface_active[46]);
    $(".zoomEcr_tr").text(interface_active[47]);
    $(".md_h_tr").text(interface_active[48]);
    $(".notif_notReady").html(interface_active[49]);
    $(".notif_warn span").text(interface_active[50]);
    $(".full_screen").text(interface_active[51]);
    $(".vt_pseudo_tr").text(interface_active[52]);
    $(".vt_avatar_tr").text(interface_active[53]);
    $(".vt_niveau_tr").text(interface_active[54]);
    $("#capture_img_profil, #capture_img_level").text(interface_active[55]);
    $("#save_img, #save_lvl").text(interface_active[56]);
    $(".dp-2-tr").html(interface_active[58]);
    $(".lvl_save").text(interface_active[59]);
    $(".tr-60").text(interface_active[60]);
    $("#close_nav").text(interface_active[61]);
    $("#close_app").text(interface_active[62]);
    $(".no_capture").text(interface_active[63]);
    $(".btr_1").text(interface_active[64]);
    $(".btr_2").text(interface_active[65]);
    $(".btr_3").text(interface_active[66]);
    $(".btr_4").text(interface_active[67]);
    $(".btr_5").text(interface_active[68]);
    $(".btr_6").text(interface_active[69]);
    $(".btr_7").text(interface_active[70]);
    $(".btr_8").text(interface_active[71]);
    $(".btr_9").text(interface_active[72]);
    $(".btr_10").text(interface_active[73]);
    $(".niv_tr").html(interface_active[74]);
    $(".ratio").text(interface_active[76]);
    $(".combats").text(interface_active[77]);
    $(".noResult").text(interface_active[78]);
    $(".abandons").text(interface_active[79]);
    $(".fight_exit").text(interface_active[80]);
    $(".connexionError").text(interface_active[81]);
    $(".gameExit").text(interface_active[82]);
    $("#menu_button_info").text(interface_active[83]);
    $("#menu_button_multi").text(interface_active[84]);
    $(".score").text(interface_active[85]);
    $(".serie_victory").text(interface_active[86]);
    $(".serie_defeat").text(interface_active[87]);
    $(".avatr_save").text(interface_active[88]);
    if (window.uiApplyLanguage) window.uiApplyLanguage(language);
    renderGameDetection();
}



// list_lang = ["eng", "fra", "spa", "ita", "deu", "rus", "jap", "chi", "por", "nld", "nor", "fin", "dan", "tur", "kor", "ell", "pol", "ces", "ron", "ara", "heb"]

list_lang = ["eng", "fra", "deu", "ita", "spaes", "spaar", "por", "pol", "rus", "jap", "kor", "chi", "zht", "tha", "ara"]



let start_ready = true;
$("#start").click(function(){
    if(start_ready == true){
    if (!$(this).hasClass("active") && $(".cadre_settings").is(":visible")) {
        $("#menu_button_settings").click();
    }
    start_ready = false;

    if($(this).hasClass("active")){
        $(this).removeClass("active").text(text_active[0]);
        if($(".pre_laod").length != 0){
            $(".pre_laod").remove();
        }
        clearInterval(runApp);
        stopPreviewPolling();
            $.ajax({
                url: "/stop",
                type :"GET",
                contentType: "application/json"
                , success: function(response){
                    $(".preview_img_profil").css("display","none");
                    $("#capture_img_profil").show();
                    runUser = setInterval(intervall_user, 3000);
                    clearInterval(runUser);
                    $(".monitor-status").remove();
                    sidebarTracking = false;
                    renderSidebar();
                    $(".cadreStats").append("<p class='elden-off simple'>"+text_active[1]+"</p>");
                    $(".live_on").addClass("live_off").removeClass("live_on");
                    start_ready = true;
                    setTimeout(function() {
                        $('.cadreStats').scrollTop($('.cadreStats')[0].scrollHeight);
                    }, 0);
                }, error:function(){
                    console.log("error")
                }
            })

    } else {

    
    launchChart(mode_chart, 1);  
    $(".presentation").remove();
    $(this).addClass("active").text(text_active[2]);
    $(".cadreStats").fadeIn();
    $(".cadre").css("background","rgba(0,0,0,0.99)");
    $(".cadreStats .monitor-status").remove();
    $(".cadreStats").append($("<p class='elden-on simple monitor-status monitor-starting'>").text(text_active[4]));
    setTimeout(function() {
        $('.cadreStats').scrollTop($('.cadreStats')[0].scrollHeight);
        if($(".cadre_user").is(":hidden")){
            $(".cadre_user").show();
            $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
            $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
        }
    }, 200);
    runApp = setInterval(intervall, 3000);
    $.ajax({
        url: "/start",
        type :"GET",
        contentType: "application/json"
        , success: function(response){
            start_ready = true;
            sidebarTracking = true;
            sidebarGameRunning = null;
            sidebarMonitorReady = false;
            renderSidebar();
            loadProfileLegend();
            startPreviewPolling();
        }, error:function(response){
            clearInterval(runApp);
            $('#start').removeClass('active').text(text_active[0]);
            start_ready = true;
            $('.monitor-starting').remove();
            $('.cadreStats').append($('<p class="elden-off simple">').text(appT('monitor_start_error', 'Impossible de démarrer le suivi. Réessaie dans quelques instants.')));
            $('.live_on').addClass('live_off').removeClass('live_on');
        }
    })
}
if(!$(".modal_chart").hasClass("hide")){
    $(".modal_chart").addClass("hide");
    $(".containeur_chart").show();
    launchChart(mode_chart, 1);
}
if($("#menu_button_captures").hasClass("active")){
    $("#menu_button_captures").click();
}    
    }
});

$( window ).resize(function() {
   
    $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
    $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
    initSetting();
});



var selected_stats_mode = 'Arena';
var detected_stats_mode = null;
var stats_request_version = 0;

function appT(key, french) { return window.uiT ? window.uiT(key, french) : french; }
function statsModeLabel(mode) {
    return mode === 'Invasion' ? appT('invasion', 'Invasions') : mode === 'Defense' ? appT('defense', 'Monde envahi') : appT('arena', 'Arène 1v1');
}

function renderInfoStats(user) {
    const fields = {
        ratio_count: 7, score_count: 16, abandons_count: 12, combats_count: 9,
        noResult_count: 10, fight_exit_count: 11, victory_count: 2, defeat_count: 3,
        egality_count: 4, serie_victory_count: 13, serie_defeat_count: 14,
        connexionError_count: 17, gameExit_count: 18
    };
    Object.keys(fields).forEach(function(field) {
        $('#stats_panel .' + field).text(user[fields[field]]);
    });
    $('#stats_mode_error').hide();
}

function updateStatsModeVisibility() {
    $('#stats_panel .arena-draw-row').toggle(selected_stats_mode === 'Arena');
}

function refreshInfoStats() {
    const mode = selected_stats_mode;
    const version = ++stats_request_version;
    $.get('/modeStats', {mode: mode}, function(response) {
        if (version === stats_request_version && mode === selected_stats_mode && response.request === 'success') {
            renderInfoStats(response.user);
        }
    }).fail(function() {
        if (version === stats_request_version) $('#stats_mode_error').text(appT('stats_unavailable', 'Statistiques indisponibles.')).show();
    });
}

$('#stats_mode_choice').on('change', function() {
    const choice = $(this).val();
    selected_stats_mode = choice === 'auto' ? (detected_stats_mode || 'Arena') : choice;
    updateStatsModeVisibility();
    refreshInfoStats();
    launchChart(mode_chart, 1);
});

function intervall(){
   
    $.ajax({
        url: "/interval",
        type :"GET",
        contentType: "application/json"
        , success: function(response){
            if (response.monitor_error || response.monitor_running === false) {
                $('.monitor-status').remove();
            }
            if (response.monitor_error && $('#start').hasClass('active')) {
                clearInterval(runApp);
                stopPreviewPolling();
                $('#start').removeClass('active').text(text_active[0]);
                start_ready = true;
                $('.cadreStats').append($('<p class="elden-off simple">').text(appT('monitor_capture_error', 'La capture s’est arrêtée à cause d’une erreur. Un journal a été enregistré.')));
                $('.live_on').addClass('live_off').removeClass('live_on');
            } else if (response.monitor_running === false && $('#start').hasClass('active') && start_ready) {
                clearInterval(runApp);
                stopPreviewPolling();
                $('#start').removeClass('active').text(text_active[0]);
                $('.cadreStats').append($('<p class="elden-off simple">').text(appT('monitor_stopped', 'Le suivi est arrêté. Clique sur Start pour le relancer.')));
                $('.live_on').addClass('live_off').removeClass('live_on');
            }
            let time_actuel = response["time_actuel"];
            let time_max = 180;
            let fight = response["fight"];
            let detectedMode = response["mode_detected"] ? response["mode"] : null;
            let effectiveMode = detectedMode || 'Arena';
            let invasion = effectiveMode !== "Arena";
            detected_stats_mode = detectedMode;
            sidebarTracking = response.monitor_running === true;
            sidebarGameRunning = response.game_running;
            sidebarMonitorReady = response.monitor_ready === true;
            renderSidebar();
            renderMonitorStatus();
            renderSessionSummary(response.session_summary);
            $('.counteur .egality').closest('li').toggle(effectiveMode === 'Arena');
            $('#stats_mode_choice option[value="auto"]').text(detectedMode ? appT('automatic', 'Automatique') + ' · ' + statsModeLabel(detectedMode) : appT('automatic_detection', 'Détection automatique'));
            if ($('#stats_mode_choice').val() === 'auto' && selected_stats_mode !== effectiveMode) {
                selected_stats_mode = effectiveMode;
                updateStatsModeVisibility();
                launchChart(mode_chart, 1);
            }
            time_actuel = Math.ceil(invasion ? time_actuel : time_max - time_actuel)
            if(fight == true){
                $(".live i").fadeIn()
                if(time_actuel>0){
                if(invasion){
                    $(".live i .live-timer-value").text(time_actuel).css("color", "#fff").removeClass("animation_simple");
                } else if(time_actuel <= 30 && time_actuel > 10){
                    $(".live i .live-timer-value").text(time_actuel).css("color","orange");
                } else {
                    if(time_actuel <= 10 ){
                        $(".live i .live-timer-value").text(time_actuel).css("color","red");
                    }else {
                        $(".live i .live-timer-value").text(time_actuel).css("color","#fff");;
                    }
                }
            } else {
                $(".live i .live-timer-value").text("0").css("color","red").addClass("animation_simple");
            }
            } else {
                setTimeout(function() {
                    $(".live i").fadeOut();
                    $(".live i .live-timer-value").text("0");
                }, 5000);   
            }
            let text = response["datas"]["text"];
            if($(".live").is(":hidden")){
                $(".live").fadeIn();
                
            }
          
            game_detection_state = response["gameDetected"] === true;
            steam_overlay_state = response["steamOverlay"] === true;
            renderGameDetection();
            let text_list = ""
            if(response["datas"]["text"] != ""){
                 text_list = text.split(",").map(function(entry) { return entry.replace(/Time:/g, appT('time', 'Temps') + ':'); })
            }
            let score = response["user"][16];
            var victory = response["user"][2]
            var defeat = response["user"][3]
            var egality = response["user"][4]
            let combats = response["user"][9];
            let noResult = response["user"][10];
            let fight_exit = response["user"][11];
            let abandons = response["user"][12];
            let serie_victoir = response["user"][13];
            let serie_defeat = response["user"][14];
            let connexionError = response["user"][17];
            let gameExit = response["user"][18];
            let ratio = response["user"][7];
            let userLvl = response["user"][19];
            $(".counteur .victory_count").text(victory);
            $(".counteur .defeat_count").text(defeat);
            $(".counteur .egality_count").text(egality);
            if ($('#stats_mode_choice').val() === 'auto') {
                stats_request_version++;
                renderInfoStats(response.user);
            } else {
                refreshInfoStats();
            }
            $(".userLvl_count").text(userLvl);
            var tampo_text = ""
            var victory_res = false;
            var defeat_res = false;
            var egality_res = false;
            var lets_go = false;
            let last_msg = $('.cadreStats p:last-child').text();
            for(let i =0; i< text_list.length; i++){
                const startMarker = '<!--search-start-->';
                const updateMarker = '<!--search-update-->';
                let entry = text_list[i].trimStart();
                // The monitor state now confirms readiness; this legacy startup
                // event is not a detection to show as a second counter entry.
                if (/^Let\x27s gooo !\s*\[/.test(entry)) continue;
                const noResultMarker = '<!--invasion-no-result-->';
                const connectionCorrectionMarker = '<!--connection-correction-->';
                let isSearchStart = entry.startsWith(startMarker);
                let isInvasionNoResult = entry.startsWith(noResultMarker);
                if (entry.startsWith(connectionCorrectionMarker)) {
                    const content = entry.slice(connectionCorrectionMarker.length);
                    const previous = $('.cadreStats p.invasion-no-result-entry').last();
                    if (previous.length) previous.html(content);
                    else $('.cadreStats').append($('<p class="simple animation_simple">').html(content));
                    continue;
                }
                if (isInvasionNoResult) text_list[i] = entry.slice(noResultMarker.length);
                if (entry.startsWith(updateMarker)) {
                    const content = entry.slice(updateMarker.length);
                    const previous = $('.cadreStats p.invasion-search-entry').last();
                    if (previous.length) previous.html(content);
                    else $('.cadreStats').append($('<p class="simple animation_simple invasion-search-entry">').html(content));
                    continue;
                }
                if (isSearchStart) text_list[i] = entry.slice(startMarker.length);
                last_msg = $('.cadreStats p:last-child').text();
                if(text_list[i] != tampo_text && last_msg != text_list[i]){
                    tampo_text = text_list[i];
                    if(text_list[i].indexOf("Let's gooo !") != -1){
                        lets_go = true;
                        start_ready = true;
                    }
                    if($(".pre_laod").length != 0){
                        $(".pre_laod").remove();
                    }

                    
                    if(last_msg == text_active[7] && text_active[7].indexOf("-") == -1){
                        $('.cadreStats p:last-child').append("<br>"+ text_list[i]);
                        if($(".notif_notReady").length != 0){
                           
                            notify_b64 = response["notif_base64"].toString();
                         
                            notif_global = notify_b64;
                            let size = response["size_notification"];
                            size_notify = size;
                            $(".edit_notif, #rang_notify").show();
                            $(".notif_notReady").remove();
                            initSetting();
                          
                        }
                       
                    } else {
                       
                    if(last_msg.indexOf(text_active[4]) != -1 && text_list[i].indexOf("Let's gooo !") != -1){
                        text_list[i] = text_list[i].replace("Let's gooo ! ","").replace("[","").replace("]","");
                        $('.cadreStats p:last-child').html(text_active[3]+" <br>"+text_list[i]);

                       
                        
                    } else {
                        
                       
                            
                            if(lets_go == true && text_list[i].indexOf("]") != -1){
                                text_list[i] = text_list[i].replace("Let's gooo ! ","").replace("[","").replace("]","");
                                $(".cadreStats").append("<p class='simple animation_simple pre_laod2'>"+text_list[i]+"</p>");
                                lets_go = false;
                            } else {
                                $(".cadreStats").append("<p class='simple animation_simple'>"+text_list[i]+"</p>");
                            }
                        
                    }
                    
                   
                    }
                
                if (isSearchStart) $('.cadreStats p:last-child').addClass('invasion-search-entry');
                if (isInvasionNoResult) $('.cadreStats p:last-child').addClass('invasion-no-result-entry');
                if(text_list[i].indexOf(text_active[8]) != -1){
                    victory_res = true;
                    text_list[i] = text_list[i].replace(text_active[8],"");
                    $('.cadreStats p:last-child').addClass("simple_victory");
                }
                if(text_list[i].indexOf(text_active[9]) != -1){
                    defeat_res = true;
                    text_list[i] = text_list[i].replace(text_active[9],"");
                    $('.cadreStats p:last-child').addClass("simple_defeat");
                }
                if(text_list[i].indexOf(text_active[12]) != -1){
                    egality_res = true;
                    text_list[i] = text_list[i].replace(text_active[12],"");
                    $('.cadreStats p:last-child').addClass("simple_egality");
                }
                if(defeat_res || victory_res || egality_res){
                    setTimeout(function() {
                        $('.cadreStats').scrollTop($('.cadreStats')[0].scrollHeight);
                    }, 0);
                }
                
                
                
                if(victory_res == true && text_list[i].indexOf(appT('time', 'Temps') + ':') != -1){
                    getCapture(text_active[10], text_list[i]);
              
                }
                if(defeat_res == true && text_list[i].indexOf(appT('time', 'Temps') + ':') != -1){
                    getCapture(text_active[11], text_list[i]);
                  
                }
                if(egality_res == true && text_list[i].indexOf(appT('time', 'Temps') + ':') != -1){
                    getCapture(text_active[13], text_list[i]);
                 
                }
                }
               

            }
            last_msg = $('.cadreStats p:last-child').text();
            setTimeout(function() {
                $('.cadreStats').scrollTop($('.cadreStats')[0].scrollHeight);
            }, 0);
            setTimeout(function() {
                $(".simple.animation_simple").removeClass("animation_simple");
            }, 3000);
        }, error:function(){
            console.log("error");
            clearInterval(runApp);
            window.close();
        }
    })


}
var status_capture = "";
var captures_posted = 0;
function getCapture(result, Time){

    $.ajax({
        url: "/capture",
        type :"GET",
        contentType: "application/json"
        , success: function(response){
            if($(".para_capture").length == 1){
                $(".no_capture").remove();
            }
        syncMulti();  
          $(".modal_chart").addClass("hide");
          $(".containeur_chart").show();
          launchChart(mode_chart, 1);
     
          let date_select = response["date"];
          let class_text = "";
          
        if(result == "Victory"){ 
                  class_text = "victory_text";
              }
        if(result == "Defeat"){    
                  class_text = "defeat_text";
              }
        if(result == "Egality"){
                  class_text = "egality_text";
              }

              
       
           
            var last_id_find = parseInt($(".para_capture .posted").first().text()) + 1 ;
           
            if((status_capture == class_text || status_capture == null || status_capture == "") &&
               ($('#capture_mode').val() === 'all' || $('#capture_mode').val() === response.mode)){
                if (last_id_find == NaN || last_id_find == null || last_id_find == "" || last_id_find == "NaN" || $.isNumeric(last_id_find) == false){
                    last_id_find = "1"; 
                    
                }
                let captureMode = response.mode === 'Invasion' ? appT('invasion', 'Invasions') + ' · ' : response.mode === 'Defense' ? appT('defense', 'Monde envahi') + ' · ' : '';
                let opponent = response.opponent ? ' · ' + $('<span>').text(response.opponent).html() : '';
                let visibleResult = result === 'Victory' ? appT('victory', 'Victory') : result === 'Defeat' ? appT('defeat', 'Defeat') : appT('draw', 'Egality');
                $(".capture-scroll").prepend("<div class='para_capture "+class_text+" add_para'><span><b>"+captureMode+visibleResult+opponent+"</b> "+Time+"</span><div class='img'><img src='data:image/jpg;base64,"+response["datas"]+"'/> </div><div class='posted'>"+last_id_find+"</div><div class='datePosted'>"+date_select+"</div></div>");
                
            }
           
        }, error:function(){
            window.close();
        }
    })



}








$(".cadre_sign img, .nav_menu h1").hover(function(){
    $(".nav_menu h1").css("filter"," drop-shadow(0 0 20px #a68d60)");
    $(".cadre_sign img").css("filter"," drop-shadow(0 0 20px #a68d60)");

}, function(){
    $(".nav_menu h1").css("filter"," none");
    $(".cadre_sign img").css("filter"," none");
});

// Remove obsolete sidebar fields if a running server still has the old template cached.
document.getElementById('session_streak')?.remove();
document.getElementById('sidebar_peers')?.closest('.sidebar-summary-row')?.remove();

// Profile legend and live summary are shared by all browser tabs.
let sidebarSession = null;
function renderSessionSummary(data) {
    if (data) sidebarSession = data;
    if (!sidebarSession) return;
    $('#session_combats').text(sidebarSession.combats);
    $('#session_victories').text(sidebarSession.victories);
    $('#session_defeats').text(sidebarSession.defeats);
    const last = sidebarSession.last;
    const label = document.getElementById('sidebar_last_combat');
    if (!last) {
        label.textContent = appT('last_combat_empty', 'Aucun combat enregistré.');
        return;
    }
    const outcomes = {
        victory: appT('victory', 'Victoire'), defeat: appT('defeat', 'Défaite'),
        draw: appT('draw', 'Égalité'), no_result: appT('no_result', 'Sans résultat'),
        connection_error: appT('session_connection_error', 'Erreur de connexion')
    };
    label.textContent = [outcomes[last.result] || outcomes.no_result, statsModeLabel(last.mode), last.opponent || ''].filter(Boolean).join(' · ');
}
function renderProfileLegend(value) {
    const node = document.getElementById('sidebar_legend');
    node.textContent = value || '';
    node.hidden = !value;
}
let legendVersion = 0;
let legendSavedVersion = 0;
let legendSaving = false;
let legendSaveTimer = null;
function loadProfileLegend() {
    $.get('/profile-legend', function(data) {
        if (data.request !== 'success') return;
        if (legendVersion === legendSavedVersion && !legendSaving) {
            $('#profile_legend').val(data.legend);
            renderProfileLegend(data.legend);
        }
        renderSessionSummary(data.session);
    });
}
function saveProfileLegend() {
    clearTimeout(legendSaveTimer);
    legendSaveTimer = null;
    if (legendSaving || legendVersion === legendSavedVersion) return;
    legendSaving = true;
    const version = legendVersion;
    const value = $('#profile_legend').val();
    $.ajax({url:'/profile-legend', type:'POST', contentType:'application/json',
        data:JSON.stringify({legend:value})
    }).done(function(data) {
        legendSavedVersion = version;
        if (legendVersion === version) {
            renderProfileLegend(data.legend);
        }
    }).fail(function() {
        if (legendVersion === version) {
            $('#profile_legend_status').text(appT('profile_legend_error', 'Impossible d’enregistrer la légende.'));
        }
    }).always(function() {
        legendSaving = false;
        if (legendVersion !== version) saveProfileLegend();
    });
}
$('#profile_legend').on('input', function() {
    legendVersion++;
    renderProfileLegend(this.value);
    $('#profile_legend_status').text('');
    clearTimeout(legendSaveTimer);
    legendSaveTimer = setTimeout(saveProfileLegend, 500);
}).on('blur', saveProfileLegend);
$(loadProfileLegend);

// The profile drawer is independent from the statistics page.
let sidebarTracking = false;
let sidebarGameRunning = null;
let sidebarMonitorReady = false;
function renderMonitorStatus() {
    const node = $('.cadreStats .monitor-status');
    if (!node.length || !sidebarTracking) return;
    let label;
    if (!sidebarMonitorReady) label = text_active[4];
    else if (sidebarGameRunning === false) label = appT('sidebar_game_waiting', 'En attente du jeu');
    else if (sidebarGameRunning !== true) label = appT('sidebar_game_checking', 'Vérification du jeu…');
    else label = appT('detection_enabled', 'Détection activée');
    node.text(label).toggleClass('monitor-starting', !sidebarMonitorReady);
}
function renderSidebar() {
    const tracking = document.getElementById('sidebar_tracking');
    const mode = document.getElementById('sidebar_mode');
    if (!tracking || !mode) return;
    if (!sidebarTracking) {
        tracking.textContent = appT('detection_disabled', 'Détection désactivée');
    } else if (sidebarGameRunning === false) {
        tracking.textContent = appT('sidebar_game_waiting', 'En attente du jeu');
    } else if (sidebarGameRunning !== true || !sidebarMonitorReady) {
        tracking.textContent = appT('sidebar_game_checking', 'Vérification du jeu…');
    } else {
        tracking.textContent = appT('detection_enabled', 'Détection activée');
    }
    mode.textContent = detected_stats_mode ? statsModeLabel(detected_stats_mode) : appT('unknown_mode', 'Mode non déterminé');
}
function setSidebarOpen(open) {
    document.body.classList.toggle('profile-sidebar-open', open);
    const button = document.getElementById('sidebar_toggle');
    button.setAttribute('aria-expanded', String(open));
    button.dataset.i18nAria = open ? 'sidebar_close' : 'sidebar_open';
    button.dataset.i18nAriaFr = open ? 'Fermer le panneau de profil' : 'Ouvrir le panneau de profil';
    button.setAttribute('aria-label', appT(button.dataset.i18nAria, button.dataset.i18nAriaFr));
    try { localStorage.setItem('trackerProfileSidebarOpen', open ? '1' : '0'); } catch (_) {}
    if (myChart && typeof myChart.resize === 'function') setTimeout(() => myChart.resize(), 670);
}
let initialSidebarOpen = true;
try { initialSidebarOpen = localStorage.getItem('trackerProfileSidebarOpen') !== '0'; } catch (_) {}
setSidebarOpen(initialSidebarOpen);
document.getElementById('sidebar_toggle').addEventListener('click', function() {
    setSidebarOpen(!document.body.classList.contains('profile-sidebar-open'));
});
document.addEventListener('ui-language-change', function() {
    renderSidebar();
    renderMonitorStatus();
    renderSessionSummary();
    const button = document.getElementById('sidebar_toggle');
    button.setAttribute('aria-label', appT(button.dataset.i18nAria, button.dataset.i18nAriaFr));
});
function closeStatistics() {
    document.getElementById('stats_panel').hidden = true;
    document.getElementById('menu_button_info').classList.remove('active');
    if (!$('.modal_chart').hasClass('hide')) {
        $('.modal_chart').addClass('hide');
        $('.containeur_chart').show();
        mode_window = 1;
        launchChart(mode_chart, 1);
    }
}
$('#menu_button_info').on('click', function() {
    const panel = document.getElementById('stats_panel');
    if (!panel.hidden) { closeStatistics(); return; }
    ['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_players', 'menu_button_history'].forEach(function(id) {
        const button = document.getElementById(id);
        if (button.classList.contains('active')) button.click();
    });
    panel.hidden = false;
    this.classList.add('active');
    updateStatsModeVisibility();
    refreshInfoStats();
    launchChart(mode_chart, 1);
    setTimeout(function() { if (myChart && typeof myChart.resize === 'function') myChart.resize(); }, 100);
});
['menu_button_captures', 'menu_button_multi', 'menu_button_settings', 'menu_button_players', 'menu_button_history', 'start'].forEach(function(id) {
    document.getElementById(id).addEventListener('click', closeStatistics);
});
var menu_settings = false; 
$("#menu_button_settings").click(function(){
    if(menu_settings == true){
       
        if($(".presentation").length != 0){
            $(".presentation").fadeIn();
        }
        $(".cadre_resu").fadeIn();
        $(this).removeClass("active");
        $(".cadre_settings").css("display","none");
        setTimeout(function() {
            $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
            $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
        }, 200);
        menu_settings = false;
    } else {
        if($(".presentation").length != 0){
            $(".presentation").fadeOut();
        }
        if($("#menu_button_multi").hasClass("active")){
            $("#menu_button_multi").click();
        }
        if($("#menu_button_captures").hasClass("active")){
            $("#menu_button_captures").click();
        }
        $(".cadre_resu").hide();
        $(this).addClass("active");
        $(".cadre_settings").css("display","flex");
        menu_settings = true
        $(".contente_header_settings .btn_menu_settings").first().click();
        $(".setting_user_detail").addClass("hide");
        $(".detail_pseudo").addClass("hide");
        $("#save_lvl").addClass("hide");
        $(".lvl_save").addClass("hide");
        $(".preview_img_profil").hide();
        $(".setting_user_level").addClass("hide");
        $(".detail_pseudo").addClass("hide");
        $(".detail_img").addClass("hide");
        $("#capture_img_profil").show();
        $("#save_img").addClass("hide");
        $(".avatr_save").hide();
        preview_img_profil = false;
        clearInterval(runUser);
    }
    setTimeout(function() {
        $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
        $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
    }, 200);
    if(!$(".modal_chart").hasClass("hide")){
        $(".modal_chart").addClass("hide");
        $(".containeur_chart").show();
        launchChart(mode_chart, 1);
    }
});
var menu_multi = false;
$("#menu_button_multi").click(function(){
     
    if(menu_multi == true){
        $(this).removeClass("active");
        $(".cadre_multi").hide();
        // $(".sub_carde_user .cadre_user").remove();
        menu_multi = false;
    } else {
        if($("#menu_button_captures").hasClass("active")){
            $("#menu_button_captures").click();
        }
        if($("#menu_button_settings").hasClass("active")){
            $("#menu_button_settings").click();
        }
        if(!document.body.classList.contains("profile-sidebar-open")){
            $(".modal_chart").addClass("hide");
            $(".containeur_chart").show();
            launchChart(mode_chart, 1);
        }
        $("#sync_multi").click();
        // $(".sub_carde_user .cadre_user").remove();
        // $(".sub_carde_user").append($(".cadre_user ").clone());
        $(this).addClass("active");
        $(".cadre_multi").show();
        menu_multi = true
        syncMulti();
       
        setTimeout(function() {
            $("input#pseudo").focus();
        }, 200);
    }
   setTimeout(function() {
        $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
        $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
    }, 200);
    if(!$(".modal_chart").hasClass("hide")){
        $(".modal_chart").addClass("hide");
        $(".containeur_chart").show();
        launchChart(mode_chart, 1);
    }
});
var menu_capture = false;
$("#menu_button_captures").click(function(){

    if(menu_capture == true){
        $(this).removeClass("active");
        $(".cadre").css("height","97.5%");
            $(".capture-toolbar").hide();
        if($(".cadre_user").hasClass("hide")){
            $(".cadre_user").removeClass("hide");
        }
        $(".up_capture .min_up").text("/\\");
        $(".up_capture .sub_up").attr("style","clip-path: polygon(0 0, 100% 0, 100% 100%, 50% 70%, 0 100%);");
        $(".up_capture .min_up").attr("style","clip-path: polygon(10% 5%, 90% 5%, 90% 90%, 50% 59%, 10% 90%);")
        if($(".para_capture").length == 0){
            $(".no_capture").hide();
        }
      
        up_capture = false;
        menu_capture = false;
    } else {
        if($(".para_capture").length == 0){
            $(".no_capture").show();
        }
        if($("#menu_button_multi").hasClass("active")){
            $("#menu_button_multi").click();
        }
        if($("#menu_button_settings").hasClass("active")){
            $("#menu_button_settings").click();
        }
        $(".capture-toolbar").css('display', 'flex');
        $(this).addClass("active");
        $(".cadre").css("height","60%");
        $(".cardre_captures").css("height","calc(40% - 20px)");
        menu_capture = true
        setTimeout(function() {
            $('.cadreStats').scrollTop($('.cadreStats')[0].scrollHeight);
        }, 500);
       
    }
    setTimeout(function() {
        $('.capture-scroll').scrollTop(0);
    }, 100);
    setTimeout(function() {
        $(".cadre_user img").css("max-height",($(".cadre_user").height() / 3)+"px");
        $(".cadre_user .scroll_card").css("height",($(".cadre_user").height() - $(".header_carde.img_user").height()) - 5+"px");
       
    }, 300);
    if(!$(".modal_chart").hasClass("hide")){
        $(".modal_chart").addClass("hide");
        $(".containeur_chart").show();
        launchChart(mode_chart, 1);
    }
});



$(function() {
    const content = $('#capture_viewer_overlay .capture-viewer-content');
    if (content.length && !content.find('.capture-viewer-nav').length) {
        content.append($('<button type="button" class="capture-viewer-nav capture-viewer-prev">‹</button>').attr('aria-label', appT('previous_capture', 'Capture précédente')));
        content.append($('<button type="button" class="capture-viewer-nav capture-viewer-next">›</button>').attr('aria-label', appT('next_capture', 'Capture suivante')));
    }
});

let captureViewerIndex = -1;

function visibleCaptureCards() {
    return $('.cardre_captures .para_capture:visible').toArray();
}

function showCaptureViewer(index) {
    const cards = visibleCaptureCards();
    if (index < 0 || index >= cards.length) return;
    captureViewerIndex = index;
    $('.capture-viewer-card').remove();
    $('.capture_absolute_launch').removeClass('capture_absolute_launch');
    const card = $(cards[index]);
    const copy = card.clone().addClass('capture-viewer-card').removeClass('add_para capture_absolute_launch');
    $('#capture_viewer_overlay .capture-viewer-content').append(copy);
    card.addClass('capture_absolute_launch');
    $('.capture-viewer-prev').prop('disabled', index === 0);
    $('.capture-viewer-next').prop('disabled', index === cards.length - 1);
}

function closeCaptureViewer() {
    $('#capture_viewer_overlay').prop('hidden', true);
    $('.capture-viewer-card').remove();
    $('.capture_absolute_launch').removeClass('capture_absolute_launch');
    captureViewerIndex = -1;
}

$(document).on('click', '.cardre_captures .para_capture', function() {
    const index = visibleCaptureCards().indexOf(this);
    if (index < 0) return;
    closeCaptureViewer();
    showCaptureViewer(index);
    $('#capture_viewer_overlay').prop('hidden', false);
    $('.capture-viewer-close').trigger('focus');
});

document.addEventListener('pointerdown', function(event) {
    const overlay = document.getElementById('capture_viewer_overlay');
    if (!overlay.hidden && !event.target.closest('.capture-viewer-content')) closeCaptureViewer();
}, true);
document.addEventListener('focusin', function(event) {
    const overlay = document.getElementById('capture_viewer_overlay');
    if (!overlay.hidden && !event.target.closest('.capture-viewer-content')) closeCaptureViewer();
}, true);
$(document).on('click', '.capture-viewer-close', closeCaptureViewer);
$(document).on('click', '.capture-viewer-prev', function() { showCaptureViewer(captureViewerIndex - 1); });
$(document).on('click', '.capture-viewer-next', function() { showCaptureViewer(captureViewerIndex + 1); });
$(document).on('keydown', function(event) {
    if ($('#capture_viewer_overlay').prop('hidden')) return;
    if (event.key === 'Escape') closeCaptureViewer();
    if (event.key === 'ArrowLeft') { event.preventDefault(); showCaptureViewer(captureViewerIndex - 1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); showCaptureViewer(captureViewerIndex + 1); }
});



var up_capture = false;
$(".up_capture").click(function(){

    if(up_capture == true){
        $(".up_capture .min_up").text("/\\");
        $(".up_capture .sub_up").attr("style","clip-path: polygon(0 0, 100% 0, 100% 100%, 50% 70%, 0 100%);");
        $(".up_capture .min_up").attr("style","clip-path: polygon(10% 5%, 90% 5%, 90% 90%, 50% 59%, 10% 90%);")
        $(".cadre").css("height","60%");
        $(".cardre_captures").css("height","calc(40% - 20px)");
        up_capture = false;
    } else {
        $(".up_capture .min_up").text("\\/");
        $(".up_capture .sub_up").attr("style","clip-path: polygon(0 0, 100% 0, 100% 70%, 50% 100%, 0 70%);");
        $(".up_capture .min_up").attr("style","clip-path: polygon(10% 5%, 90% 5%, 90% 70%, 50% 90%, 10% 70%);")
        $(".cadre").css("height","10%");
        $(".cardre_captures").css("height","calc(90% - 20px)");
        up_capture = true
    } 

});
var firstInit = false;
var size_notify = [];
var notif_global = "";
function init(){
    
    $.ajax({
        url: "/init",
        type :"GET",
        contentType: "application/json"
        , success: function(response){
            let size = response["size_notification"];
            size_notify = size;
            
            let notif = response["notif"];
            notif_global = notif;
            let language_default = response["language_default"];
            let captures = response["captures"];
            let user = response["user"];
            let score = response["user"][16];
            let victory = response["user"][2];
            let defeat = response["user"][3];
            let egality = response["user"][4];
            let ratio = response["user"][7];
            let combats = response["user"][9];
            let noResult = response["user"][10];
            let fight_exit = response["user"][11];
            let abandons = response["user"][12];
            let serie_victoir = response["user"][13];
            let serie_defeat = response["user"][14];
            let connexionError = response["user"][17];
            let gameExit = response["user"][18];
            let userLvl = response["user"][19];
          
            // Global Notify top
            notify_top = response["settings"][4];
           
            if(notify_top != 0){
            
              
                $(".carde_info[info=captures]").remove();
            }
            if(response["user"][1] != ""){
                $(".carde_info[info=pseudo]").remove();
            }
       
            if(response["user"][6] != ""){
                $(".carde_info[info=avatar]").remove();
            }
            if(parseInt(response["user"][19]) > 0){
                $(".carde_info[info=niveau]").remove();
            }
            if(language_default == false){
                $(".carde_info[info=languages]").remove();
            }
            let autoStart = response["settings"][6];
            let resolution = response["settings"][2]+"x"+response["settings"][1];
            let zoomWindow = response["settings"][3];
            $(".score_count").text(score);
            $(".victory_count").text(victory);
            $(".defeat_count").text(defeat);
            $(".egality_count").text(egality);
            $(".abandons_count").text(abandons);
            $(".combats_count").text(combats);
            $(".noResult_count").text(noResult);
            $(".ratio_count").text(ratio);
            $(".fight_exit").text(fight_exit);
            $(".serie_victory_count").text(serie_victoir);
            $(".serie_defeat_count").text(serie_defeat);
            $(".resolution").text(resolution);
            $(".zoomWindow").text(zoomWindow+"%");
            $(".connexionError_count").text(connexionError);
            $(".gameExit_count").text(gameExit);
            $(".userLvl_count").text(userLvl);
            if(autoStart == "true"){
                $(".auto_start span").addClass("hide");
                $(".auto_start span[auto_start=true]").removeClass("hide");
                setTimeout(function() {
                    $("#start").click();
                }, 500);
               
            } else {
                $(".auto_start span").addClass("hide");
                $(".auto_start span[auto_start=false]").removeClass("hide");
            }
            
            if (user[1] != ''){

                $(".userName").text(user[1]).keyup();
                $("#pseudo").val(user[1]);
            }  

          
                   
              
                $(".panel_user").removeClass("hide");
               

             if(firstInit == false){

                if(user[6] != ''){
                    
                    $(".fakeImageuser").hide();
                    if($(".user_img_carde").length != 0){
                        $(".user_img_carde").attr("src","data:image/jpg;base64,"+user[6]);
                    }else {
                        $(".img_user").prepend("<img class='user_img_carde' src='data:image/jpg;base64,"+user[6]+"'>");
                    }
                    $(".panel_user p span").text(user[7]);
                }

                let langue_select = user[5];
        
                launchLanguages(langue_select);

                if($(".no_capture").length == 1 && response["captures"].length != 0){
                    // $(".no_capture").remove();
                } 
                  
             
                for(let i = 0; i < response["captures"][0].length;i++){

                    let victory_cp = response["captures"][0][i][2];
                    let defeat_cp = response["captures"][0][i][3];
                    let egality_cp = response["captures"][0][i][4];
                    
                    let result = "";
                    let class_text = "";
                
                    
                        if(victory_cp == 1){
                            result = appT('victory', 'Victory')
                            class_text = "victory_text";
                        }
                        if(defeat_cp == 1){
                            result = appT('defeat', 'Defeat')
                            class_text = "defeat_text";
                        }
                        if(egality_cp == 1){
                            result = appT('draw', 'Egality')
                            class_text = "egality_text";
                        }
                        if (response["captures"][0][i][7] !== "Arena") result = (response['captures'][0][i][7] === 'Defense' ? appT('defense', 'Monde envahi') : appT('invasion', 'Invasions')) + " · " + result;
                        if (response["captures"][0][i][1]) result += " · " + $('<span>').text(response["captures"][0][i][1]).html();
                        let date_select = response["captures"][0][i][6];

                        let Time = response["captures"][0][i][5];
                        let base64 = response["captures"][0][i][8];
                        let capture_ID = response["captures"][0][i][0] ;
                        $(".capture-scroll").prepend("<div class='para_capture "+class_text+"'><span><b>"+result+"</b><br> "+appT('time', 'Temps')+": "+Time+" s</span><div class='img'><img src='data:image/jpg;base64,"+base64+"'/> </div><div class='posted'>"+capture_ID+"</div><div class='datePosted'>"+date_select+"</div></div>");
                    
                }
                loaderInit();
                
               
            }
           
          
            firstInit = true;
        }, error:function(){
            console.log("error")
        }
    })

}
var scroll_request = false;
$('.capture-scroll').on('scroll', function() {

    if($('#capture_mode').val() !== 'all') return;
    if($(this).scrollTop() + $(this).innerHeight() + 100 >= $(this)[0].scrollHeight && scroll_request == false && $(".para_capture").length >= 50) {
   
        scroll_request = true;
        $(".capture-scroll").append("<div class='next_captures_loader'><span></span><span></span><span></span></div>");
        $.get("/nextCaptures", function(response){
            if(response["request"] == "success"){
                let last_id = response["captures"][0][0][0];
                array_capture = response["captures"][0].reverse();
                for(let i = 0; i < response["captures"][0].length;i++){

                    let victory_cp = array_capture[i][2];
                    let defeat_cp = array_capture[i][3];
                    let egality_cp = array_capture[i][4];
                    
                    let result = "";
                    let class_text = "";
                
                    
                        if(victory_cp == 1){
                            result = appT('victory', 'Victory')
                            class_text = "victory_text";
                        }
                        if(defeat_cp == 1){
                            result = appT('defeat', 'Defeat')
                            class_text = "defeat_text";
                        }
                        if(egality_cp == 1){
                            result = appT('draw', 'Egality')
                            class_text = "egality_text";
                        }
                        if (array_capture[i][7] !== "Arena") result = (array_capture[i][7] === 'Defense' ? appT('defense', 'Monde envahi') : appT('invasion', 'Invasions')) + " · " + result;
                        if (array_capture[i][1]) result += " · " + $('<span>').text(array_capture[i][1]).html();
                        let date_select = array_capture[i][6];

                        let Time = array_capture[i][5];
                        let base64 = array_capture[i][8];
                        let capture_ID = array_capture[i][0] ;
                        $(".capture-scroll").append("<div class='para_capture "+class_text+"'><span><b>"+result+"</b><br> "+appT('time', 'Temps')+": "+Time+" s</span><div class='img'><img src='data:image/jpg;base64,"+base64+"'/> </div><div class='posted'>"+capture_ID+"</div><div class='datePosted'>"+date_select+"</div></div>");
                       
                        
                }
                $(".cardre_captures .next_captures_loader").remove();
                if(last_id <= 1){
                    scroll_request = null;
                } else {
                    scroll_request = false;
                }
                
            }
         

        });
    }
})

$(".contente_header_settings .btn_menu_settings").click(function(e){

        
        if($(this).hasClass("active_setting") == false){
            if($(this).attr("menu") == "2" ){
                
                    initSetting();
            
            }
            if($(this).attr("menu") == "3"){
                setTimeout(function() {
                    $("#pseudo").focus();
                }, 100);
                
            }
            $(".contente_header_settings .btn_menu_settings").removeClass("active_setting");
            $(this).addClass("active_setting");
            $(".contente_settings").addClass("hide");
            $(".contente_settings[setting="+$(this).attr('menu')+"]").removeClass("hide");
        }

});

$("input[type=text]#pseudo").click(function () {
    $(".setting_user_level").addClass("hide");
    $(".setting_user_detail").addClass("hide");
    $(".detail_pseudo").removeClass("hide");
});

$("input[type=text]#pseudo").keyup(function () {
 
    
    if(/^[a-zA-Z0-9]*$/.test($(this).val()) && $(this).val().length != 0) {
        $("#notcs").text("o").css("color","lime");
	    let pseudo_lengt = $(this).val().length;
      
	    if(pseudo_lengt != 0 && pseudo_lengt <= 16 && pseudo_lengt >= 3){
            $("#max21, #min3").text("o").css("color","lime");
        
            let pseudo = $(this).val();
           
            if(/^[a-zA-Z0-9]*$/.test(pseudo) && $(this).val().length != 0 && $(this).val().length <= 16 && $(this).val().length >= 3) {
                $.post("/addUser", {"pseudo": pseudo},function(response){
                    if(response["request"] == "success"){
                        
                        if (response["pseudo"] != ''){
                            $(".carde_info[info=pseudo]").fadeOut();
                            $(".userName").text(response["pseudo"]);
                            $(".panel_pseudo").remove();
                            $(".panel_img").removeClass("hide");
                            $("#save_pseudo").addClass("hide");
                        }
        
                    }
                    
                    
                }); 
            }

        } else {
            $("#max21, #min3").text("o").css("color","red");
            $('#save_pseudo').prop("disabled", true);
        }
    } else {

        let pseudo_lengt = $(this).val().length;
   
	    if(pseudo_lengt > 16 && pseudo_lengt < 3){
            $("#max21, #min3").text("o").css("color","red");
        }
        $("#notcs").text("o").css("color","red");
        $('#save_pseudo').prop("disabled", true);
    }
    $(".setting_user_level").addClass("hide");
    $(".setting_user_detail").addClass("hide");
    $(".detail_pseudo").removeClass("hide");
});


var runUser = setInterval(intervall_user, 3000);
clearInterval(runUser);
var preview_img_profil = false;
runUserFor = "";
function intervall_user(){

    $.ajax({
        url: "/monitor_user",
        type :"POST",
        data: {"mode":runUserFor}
        , success: function(response){
            let interval_img = response["interval"];
           
            if(interval_img.replace(" ","") != ""){
                if($(".preview_img_profil img").length == 0 && preview_img_profil == false && runUserFor == "img_avatar"){
                    preview_img_profil = true;
                    $(".preview_img_profil .loading").hide();
                    $(".fakeImageuser").hide();
                    $(".preview_img_profil").append("<img src='data:image/jpg;base64,"+interval_img+"'>");
                    $(".carde_info[info=avatar]").fadeOut();
                    $(".avatr_save").show();
                    $(".panel_img .profile-instructions").hide();
                    if($(".user_img_carde").length != 0){
                        $(".user_img_carde").attr("src","data:image/jpg;base64,"+interval_img);
                    }else {
                        $(".img_user").prepend("<img class='user_img_carde' src='data:image/jpg;base64,"+interval_img+"'>");
                    }
                    $("#save_img").removeClass("hide").prop("disabled", false);
                    clearInterval(runUser);
                    runUserFor = "";
                }
                if(runUserFor == "img_lvl"){
                    clearInterval(runUser);
                    $(".preview_img_level .loading").hide();
                    $(".lvl_save").removeClass("hide");
                    $(".setting_user_level .profile-instructions").hide();
                    $(".preview_img_level span").remove();
                    $(".preview_img_level").append("<span>"+interval_img+"</span>");
                    $("#save_lvl").removeClass("hide").prop("disabled", false);
                    $(".carde_info[info=niveau]").remove();
                    runUserFor = "";
                }
            } 
          
        }
        });

}

$("#capture_img_profil, #capture_img_level").click(function(){
    runUserFor = $(this).attr("mode");
    if($("#start").hasClass("active") == false){
        $("#start").click();
    }
    if(runUserFor == "img_avatar"){
        $(".preview_img_profil").css("display","flex");
        $(".preview_img_profil .loading").show();
    } else {
        $(".preview_img_level").css("display","flex");
        $(".preview_img_level .loading").show();
    }



    runUser = setInterval(intervall_user, 3000);
    $(this).hide();

});


$("#save_img").click(function(){
    if($(".preview_img_profil img").length != 0){
    
                $(".panel_user").removeClass("hide");
                // $("#menu_button_settings").click();
                $(".fakeImageuser").hide();
                $(".detail_img").addClass("hide");
                $("#save_img").addClass("hide").prop("disabled", true);
                clearInterval(runUser);   
    }
});
$("#save_lvl").click(function(){
    if($(".preview_img_level span").length != 0){

                // $(".panel_user").removeClass("hide");
                // $("#menu_button_settings").click();
                // $(".fakeImageuser").hide();
                $(".setting_user_level").addClass("hide");
                $("#save_lvl").addClass("hide").prop("disabled", true);
                clearInterval(runUser);   
    }
});
$("#changeAvatar").click(function(){
    $(".preview_img_profil").hide();
    $(".setting_user_level").addClass("hide");
    $(".detail_pseudo").addClass("hide");
    $(".detail_img").removeClass("hide");
    $("#capture_img_profil").show();
    $("#save_img").addClass("hide");
    $(".avatr_save").hide();
    $(".panel_img .profile-instructions").show();
    preview_img_profil = false;
    clearInterval(runUser);
    $(".preview_img_profil img").remove();
}); 
$("#changeLvl").click(function(){
    $("#capture_img_level").show();
    $(".preview_img_level").hide();
    $(".setting_user_level").removeClass("hide");
    $(".setting_user_detail").addClass("hide");
    $(".detail_pseudo").addClass("hide");
    $("#save_lvl").addClass("hide");
    $(".lvl_save").addClass("hide");
    $(".setting_user_level .profile-instructions").show();
    $(".preview_img_level span").remove();
   
});

function syncMulti(){
    var table = $('#table_multi').DataTable();

    $.get("/syncMulti", function(response){
        if(response["request"] == "success"){
            $("#multi_offline_notice").remove();
            if (!response["online"]) {
                $("#table_multi").before($('<p id="multi_offline_notice">').text(appT('leaderboard_offline', 'Classement indisponible : affichage des données locales.')));
            }
        
            // $(".cadre_loading").css("display","none");
            // $(".panel_multi_body table").removeClass("hide");
           
            datas = response["datas"]
            table.clear();
            
            // $("#sync_multi").css("opacity","1");
            for(let i=0;i<datas.length;i++){
                let number = i +1;
                let name = datas[i][2];
                let victory = datas[i][3];
                let defeat = datas[i][4];
                let egality = datas[i][5];
                let language = datas[i][6];
                let ratio = datas[i][7];
                let avatar = datas[i][8];
                let combats = datas[i][10];
                // let noResult = datas[i][11]
                // let fight_exit = datas[i][12]
                // let abandon = datas[i][13]
                // let maxVictory = datas[i][14]
                // let maxDefeat = datas[i][15]
                // let ratioTime = datas[i][16]
                let score = datas[i][17];
                let userLvl = datas[i][18];
                number = "<span user_id='"+datas[i][0]+"'>"+number+"</span>";
                if(avatar != ""){
                    avatar = "<img src='data:image/jpg;base64,"+avatar+"'/>";
                } else {
                    avatar = '<div class="fakeImageuser">?</div>';
                }
                if(language == "fra"){
                    language = "<img title='"+language+"' src='/static/France.png'/>"
                }
                if(language == "eng"){
                    language = "<img title='"+language+"' src='/static/English.png'/>"
                }
              
                table.row.add([number, language, name, avatar, userLvl,score,victory,defeat,egality,ratio,combats]);
                
             }
             table.draw(false);
        }
    }); 


}

counteur_loader = 22;
$('.load_fire').css("background-image", "url('/static/split1.png')");
centent_size = $('.load_fire').width();
unite_size = centent_size / counteur_loader;

for(let i=0; i< counteur_loader; i++){
   
        $('.load_fire').css("left", unite_size * i+"px");
    setTimeout(() => {
    }, 2000);

}



$(".auto_start button").click(function(){
    
    let div_hide = $(".auto_start span.hide");
    $(".auto_start span:not(.hide)").addClass("hide");
    div_hide.removeClass("hide");
    let selected = $(".auto_start span:not(.hide)").attr("auto_start");
    $.post("/autoStart", {"auto_start": selected},function(response){

    }); 

});



// SETTINGS

function initSetting() {
    if (window.initNotificationRegion) window.initNotificationRegion();
}

















$(".sub_v, .sub_d, .sub_e").click(function(){
   
    $(".para_capture").remove();
    
    $(".capture-scroll").append("<div class='next_captures_loader'><span></span><span></span><span></span></div>");
   
    if($(this).hasClass("sub_v") && !$(this).hasClass("active")){
        status_capture = "victory_text";
        $(".sub_v, .sub_d, .sub_e").removeClass("active");
        $(this).addClass("active");
    } else if($(this).hasClass("sub_d") && !$(this).hasClass("active")){
        status_capture = "defeat_text";
        $(".sub_v, .sub_d, .sub_e").removeClass("active");
        $(this).addClass("active");
    } else if($(this).hasClass("sub_e") && !$(this).hasClass("active")){
        status_capture = "egality_text";
        $(".sub_v, .sub_d, .sub_e").removeClass("active");
        $(this).addClass("active");
    } else {
        $(".sub_v, .sub_d, .sub_e").removeClass("active");
        status_capture = null;
    }
    scroll_request = true;
    
    $.get("/allCaptures", {mode: $('#capture_mode').val()}, function(response){
        if(response["request"] == "success" && response["captures"] != ""){
            let last_id = response["captures"][0][0];
            array_capture = response["captures"];
            count_status = 1;
            for(let i = 0; i < response["captures"].length;i++){
          
                let victory_cp = array_capture[i][2];
                let defeat_cp = array_capture[i][3];
                let egality_cp = array_capture[i][4];
                
                let result = "";
                let class_text = "";
            
                
                    if(victory_cp == 1){
                        result = appT('victory', 'Victory')
                        class_text = "victory_text";
                    }
                    if(defeat_cp == 1){
                        result = appT('defeat', 'Defeat')
                        class_text = "defeat_text";
                    }
                    if(egality_cp == 1){
                        result = appT('draw', 'Egality')
                        class_text = "egality_text";
                    }
                    if (array_capture[i][7] !== "Arena") result = (array_capture[i][7] === 'Defense' ? appT('defense', 'Monde envahi') : appT('invasion', 'Invasions')) + " · " + result;
                    if (array_capture[i][1]) result += " · " + $('<span>').text(array_capture[i][1]).html();
                    let date_select = array_capture[i][6];

                    let Time = array_capture[i][5];
                    let base64 = array_capture[i][8];
                    let capture_ID = array_capture[i][0] ;
                 
                    if(status_capture == class_text || status_capture == null){
                        if(status != null){
                            capture_ID = count_status;
                            $(".capture-scroll").prepend("<div class='para_capture "+class_text+"'><span><b>"+result+"</b><br> "+appT('time', 'Temps')+": "+Time+" s</span><div class='img'><img src='data:image/jpg;base64,"+base64+"'/> </div><div class='posted'>"+capture_ID+"</div><div class='datePosted'>"+date_select+"</div></div>");
                        } else {
                            $(".capture-scroll").append("<div class='para_capture "+class_text+"'><span><b>"+result+"</b><br> "+appT('time', 'Temps')+": "+Time+" s</span><div class='img'><img src='data:image/jpg;base64,"+base64+"'/> </div><div class='posted'>"+capture_ID+"</div><div class='datePosted'>"+date_select+"</div></div>");
                        }
                        count_status += 1;
                    }
                    
            }
            $(".cardre_captures .next_captures_loader").remove();
            if (!$('.no_capture').length) $('.capture-scroll').append('<div class="no_capture">Aucune capture disponible</div>');
            $('.no_capture').toggle($('.cardre_captures .para_capture').length === 0);
            if(last_id <= 1){
                scroll_request = null;
            } else {
                scroll_request = false;
            }
            
        } else {
            $(".cardre_captures .next_captures_loader").remove();
            if (!$('.no_capture').length) $('.capture-scroll').append('<div class="no_capture">Aucune capture disponible</div>');
            $('.no_capture').show();

        }
     

    });
    

});

$('#capture_mode').on('change', function() {
    const mode = $(this).val();
    $('.sub_e').toggle(mode === 'Arena' || mode === 'all');
    $('.sub_v, .sub_d, .sub_e').removeClass('active');
    $('.sub_v').addClass('active').trigger('click');
});


$("#close_nav").click(function(){

    window.close();


});


$(".carde_info").click(function(){
    let info_selected = $(this).attr("info");

    if(info_selected == "languages"){
        if($(".cadre_settings").is(":hidden")){
            $("#menu_button_settings").click();
        } else {
            $(".btn_menu_settings[menu=0]").click();
        }
    }
    if(info_selected == "captures"){
        if($(".cadre_settings").is(":hidden")){
            $("#menu_button_settings").click();
            $(".btn_menu_settings[menu=2]").click();
        } else {
            $(".btn_menu_settings[menu=2]").click();
            $(".detail_img").addClass("hide");
            $(".detail_pseudo").addClass("hide");
            $(".setting_user_level").removeClass("hide");
        }
    }
    if(info_selected == "niveau"){
        if($(".cadre_settings").is(":hidden")){
            $("#menu_button_settings").click();
            $(".btn_menu_settings[menu=3]").click();
        } else {
            $(".btn_menu_settings[menu=3]").click();
        }
        $("#changeLvl").click();
    }
    if(info_selected == "pseudo" || info_selected == "avatar"){
        if($(".cadre_settings").is(":hidden")){
            $("#menu_button_settings").click();
            $(".btn_menu_settings[menu=3]").click();
        } else {
            $(".btn_menu_settings[menu=3]").click();
        }
        if(info_selected == "pseudo"){
            $("#pseudo").click();
            
        }
        if(info_selected == "avatar"){
           $("#changeAvatar").click();
        }
    }

});  
$(document).on("click",".chartResize",function() {
  
    if($(this).hasClass("activax")){
        $(".modal_chart").addClass("hide");
        mode_window = 1
        launchChart(mode_chart, mode_window);
       
        $(".containeur_chart").show();
    } else {
        if($("#menu_button_captures").hasClass("active")){
            $("#menu_button_captures").click();
        }
        if($("#menu_button_settings").hasClass("active")){
            $("#menu_button_settings").click();
        }
        if($("#menu_button_multi").hasClass("active")){
            $("#menu_button_multi").click();
        }
        $(".modal_chart").removeClass("hide");
        mode_window = 2
        launchChart(mode_chart, mode_window);
     
        $(".containeur_chart").hide();
    }


});
if($("#menu_button_multi").hasClass("active")){
    $("#menu_button_multi").click();
}
if($("#menu_button_settings").hasClass("active")){
    $("#menu_button_settings").click();
}


mode_chart = "7j";
mode_window = 1
$(document).on("click",".btn-chart button[mode]",function() {
    
    if(!$(this).hasClass("chartResize")){
        $(".btn-chart button").removeClass("active");
        let mode = $(this).attr("mode"); 
        $(".btn-chart button[mode="+mode+"]").addClass("active");
        
        mode_chart = mode;
        if(mode == 1){
            $(".containeur_chart").show();
        }
        launchChart(mode, mode_window);
    }

});





var chart_loaded = false;
var myChart = 0;
var mode_find = false;
var window_chart_tampo = 0;
function launchChart(mode, window){
    mode_window = window
    if(chart_loaded == false && window == 1){
        $(".containeur_chart .cadre_chartJs canvas, #stats_user").remove();
        $(".containeur_chart .load_chart").show().empty().append("<div class='next_captures_loader'><span></span><span></span><span></span></div>");
        $(".modal_chart .cadre_chartJs canvas").remove();
        $(".modal_chart .load_chart").empty();
    }
    if(chart_loaded == false && window == 2){
        $(".containeur_chart .cadre_chartJs canvas, #stats_user").remove();
        $(".containeur_chart .load_chart").empty();
        $(".modal_chart .cadre_chartJs canvas").remove();
        $(".modal_chart .load_chart").show().empty().append("<div class='next_captures_loader'><span></span><span></span><span></span></div>");
    }

    const chartStatsMode = selected_stats_mode;
    $.get("/allCapturesChart", {mode: chartStatsMode}, function(response){
        if (chartStatsMode !== selected_stats_mode) return;
        if(response["request"] == "success"){
                captures = response["captures"];
                
                if(mode == "7j"){

                        mode_find = true;
                        var today = new Date();
                        var currentDay = today.getDay();
                        var days_tampo = days_active.slice();
                        var newDayOrder = days_tampo.splice(currentDay);
                        var date_select = newDayOrder.concat(days_tampo);
                    

                    // Initialiser les tableaux pour les victoires, défaites et égalités
                        var victoires = [0, 0, 0, 0, 0, 0, 0];
                        var defaites = [0, 0, 0, 0, 0, 0, 0];
                        var egalites = [0, 0, 0, 0, 0, 0, 0];

                        var today = new Date();
                        // Parcourir les entrées du tableau "captures"
                     
                        for (var i = 0; i < captures.length; i++) {
                            // Récupérer la date de l'entrée
                            let captureDate = new Date(new Date(captures[i][6]).setMinutes(0, 0, 0));
                       
                            let dayIndex = (captureDate.getDay() + 6) % 7;
                       
                            let day = days_active[dayIndex];
                            let dayNumber = captureDate.getUTCDate();
                            
                            let diff = (today.getTime() - captureDate.getTime()) / 86400000;

                            if (diff < 6) {
                            
                                if(day == undefined){
                                    day = days_active[days_active.length - 1];
                                }
                              
                                let formattedDate = day + " " + dayNumber ;
                                // Vérifier si la date de l'entrée est dans les 7 derniers jours
                                for (var j = 0; j < days_active.length; j++) {
                               
                                    if (day == days_active[j]) {
                                        // Incrémenter le compteur de victoires, défaites ou égalités en fonction de la valeur de l'entrée
                                        index = date_select.indexOf(days_active[j])
                                        if(index == undefined){
                                            index = 6
                                        }

                                        if (captures[i][2] == 1) {
                                            victoires[index]++;
                                        } else if (captures[i][3] == 1) {
                                            defaites[index]++;
                                        } else if (captures[i][4] == 1) {
                                            egalites[index]++;
                                        }
                                        
                                    } 
                                }
                            }
                        }
                } 
                if(mode == "24h"){

                    var victoires = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
                    var defaites = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
                    var egalites = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

                    var now = new Date();
                    var twentyFourHoursAgo = new Date(new Date(now - 24 * 60 * 60 * 1000).setMinutes(0, 0, 0));
                    var date_select = [];
                    for (var i = 23; i >= 0; i--) {
                    var date = new Date();
                    date.setHours(date.getHours() - i - 1);
                    var hours = date.getHours();
                    var minutes = date.getMinutes();
                    // date_select.push(hours + "h" + minutes + "m - "+ (hours + 1) + "h" + minutes+ "m");
                    date_select.push((hours + 1) + "h");
                    }

                    for (var i = 0; i < captures.length; i++) {
                    var captureDate = new Date(new Date(captures[i][6]).setMinutes(0, 0, 0));
                   
                    if (captureDate >= twentyFourHoursAgo) {
                    var victoire_capture = parseInt(captures[i][2]);
                    var defaites_capture = parseInt(captures[i][3]);
                    var egalites_capture = parseInt(captures[i][4]);

                    var index = Math.floor((now - captureDate) / (60 * 60 * 1000));

                    if (index >= 0 && index < 24) {
                    victoires[index] += victoire_capture;
                    defaites[index] += defaites_capture;
                    egalites[index] += egalites_capture;
                    }
                    }
                    }
                    victoires = victoires.reverse();
                    defaites = defaites.reverse();
                    egalites = egalites.reverse();

                }
                if(mode == "48h"){
                    
                    var victoires = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
                    var defaites = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
                    var egalites = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];

                    var now = new Date();
                    var HoursAgo = new Date(new Date(now - 48 * 60 * 60 * 1000).setMinutes(0, 0, 0));
                    var date_select = [];
                    for (var i = 47; i >= 0; i--) {
                    var date = new Date();
                    date.setHours(date.getHours() - i - 1);
                    var hours = date.getHours();
                    var minutes = date.getMinutes();
                    date_select.push((hours + 1) + "h");
                    }

                    for (var i = 0; i < captures.length; i++) {
                    var captureDate = new Date(new Date(captures[i][6]).setMinutes(0, 0, 0));
                    if (captureDate >= HoursAgo) {
                    var victoire_capture = parseInt(captures[i][2]);
                    var defaites_capture = parseInt(captures[i][3]);
                    var egalites_capture = parseInt(captures[i][4]);

                    var index = Math.floor((now - captureDate) / (60 * 60 * 1000));

                    if (index >= 0 && index < 48) {
                    victoires[index] += victoire_capture;
                    defaites[index] += defaites_capture;
                    egalites[index] += egalites_capture;
                    }
                    }
                    }
                    victoires = victoires.reverse();
                    defaites = defaites.reverse();
                    egalites = egalites.reverse();
                  

                }
                if(mode == "30j"){
                    var victoires = [];
                    var defaites = [];
                    var egalites = [];
                    var date_select = [];

                    var now = new Date();
                    var thirtyDaysAgo = new Date(now);
                    thirtyDaysAgo.setMonth(now.getMonth() - 1);

                    date_select.push(now.getDate() + "/" + (now.getMonth() + 1) + "/" + now.getFullYear().toString().slice(-2));
                    victoires.push(0);
                    defaites.push(0);
                    egalites.push(0);

                        for (var i = 0; i < 29; i++) {
                            if(i != 0){
                        var date = new Date();
                        date.setDate(date.getDate() - i);
                        if (date >= thirtyDaysAgo) {
                            var day = date.getDate();
                            var month = date.getMonth() + 1;
                            var year = date.getFullYear();
                            date_select.push(day + "/" + month + "/" + year.toString().slice(-2));
                            victoires.push(0);
                            defaites.push(0);
                            egalites.push(0);
                        }
                        }
                        }

                        for (var i = 0; i < captures.length; i++) {
                        var captureDate = new Date(captures[i][6]);
                        if (captureDate >= thirtyDaysAgo) {
                            var victoire_capture = parseInt(captures[i][2]);
                            var defaites_capture = parseInt(captures[i][3]);
                            var egalites_capture = parseInt(captures[i][4]);

                            var index = date_select.findIndex(function(d) {
                            return d === (captureDate.getDate() + "/" + (captureDate.getMonth() + 1) + "/" + captureDate.getFullYear().toString().slice(-2));
                            });
                          
                            if (index >= 0) {
                            victoires[index] += victoire_capture;
                            defaites[index] += defaites_capture;
                            egalites[index] += egalites_capture;
                            }
                        }
                        }
                    victoires=victoires.reverse();
                    defaites=defaites.reverse();
                    egalites=egalites.reverse();
                    date_select = date_select.reverse();
                }
                if(mode == "all"){

                    
                    var victoires = [];
                    var defaites = [];
                    var egalites = [];
                    var date_select = [];
                  
                    for (var i = 0; i < captures.length; i++) {
                        var captureDate = new Date(captures[i][6]);
                        var victoire_capture = parseInt(captures[i][2]);
                        var defaites_capture = parseInt(captures[i][3]);
                        var egalites_capture = parseInt(captures[i][4]);
                        var formattedDate = captureDate.toLocaleDateString();
                  
                        var index = date_select.indexOf(formattedDate);
                        if (index === -1) {
                            date_select.push(formattedDate);
                            index = date_select.length - 1;
                            victoires[index] = 0;
                            defaites[index] = 0;
                            egalites[index] = 0;
                        }
                        victoires[index] += victoire_capture;
                        defaites[index] += defaites_capture;
                        egalites[index] += egalites_capture;
                    }
                   
                }
                if(chart_loaded == false || window_chart_tampo != window){
                        window_chart_tampo = window;
                        if(window == 1){ 
                            $(".modal_chart canvas").remove();
                            $(".containeur_chart canvas").remove();
                            $(".containeur_chart .cadre_chartJs").append('<canvas id="stats_user"></canvas>');  
                        }
                        if(window == 2){ 
                            $(".containeur_chart canvas").remove();
                            $(".modal_chart canvas").remove();
                            $(".modal_chart .cadre_chartJs").append('<canvas id="stats_user"></canvas>');
                            
                        }
                var ctx_user = document.getElementById("stats_user").getContext('2d');
            
                    myChart = new Chart(ctx_user, {
                        type: 'line',
                        data: {
                            labels: date_select,
                            datasets: [
                                {
                                    label: appT('victories', 'Victoires'),
                                    data: victoires, // Specify the data values array
                                    fill: false,
                                    borderColor: '#32CD32', // Add custom color border (Line)
                                    backgroundColor: '#32CD32', // Add custom color background (Points and Fill)
                                    borderWidth: 1 // Specify bar border width
                                },
                                {
                                    label: appT('defeats', 'Défaites'),
                                    data: defaites, // Specify the data values array
                                    fill: false,
                                    borderColor: 'RGB(137, 18, 15)', // Add custom color border (Line)
                                    backgroundColor: 'RGB(137, 18, 15)', // Add custom color background (Points and Fill)
                                    borderWidth: 1 // Specify bar border width
                                },
                                {
                                    label: appT('draw', 'Égalité'),
                                    data: egalites, // Specify the data values array
                                    fill: false,
                                    borderColor: '#fff', // Add custom color border (Line)
                                    backgroundColor: '#fff', // Add custom color background (Points and Fill)
                                    borderWidth: 1 // Specify bar border width
                                }
                        ]},
                        options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { labels: { filter: function(item) {
                            return item.datasetIndex !== 2 || selected_stats_mode === 'Arena';
                        } } } }
                        }
                    });
                    $(".load_chart").hide();
                    chart_loaded = true;
                   
                } else {
                
                    myChart.data.datasets[0].data = victoires;
                    myChart.data.datasets[1].data = defaites;
                    myChart.data.datasets[2].data = egalites;
                    
                    myChart.data.labels = date_select;
                }
                myChart.setDatasetVisibility(2, chartStatsMode === 'Arena');
                myChart.update();
        }
        });
       
}

$('.full_screen').on('click', function(){
    // if already full screen; exit
    // else go fullscreen
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      $('.contente_settings[setting=2]').get(0).requestFullscreen();
    }
  });


  $("#close_app").click(function(){

  
    $.ajax({
        url: "/exit",
        type :"GET"
        , success: function(response){
            window.close();
        }, error:function(response){
            window.close();
        }
    })


  });
