from flask import Flask, jsonify, render_template_string, request
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import requests
from datetime import datetime, timedelta
import re

app = Flask(__name__)
# app.secret_key = "your_secret_key_here"

# Azure Blob Storage Settings (defaults)
ACCOUNT_NAME = "pandoradiagnosis"
ACCOUNT_URL = f"https://{ACCOUNT_NAME}.blob.core.windows.net"
ACCOUNT_KEY = "Y72BBA68S/24r3tuGEY+SKGhigd5m/O7m4k5WSUT8yfxUzB+hAITI74PXAnno2MeCERHqZi4a++o+AStOlZ7uw=="
BLOB_PREFIX = ""  # Optional prefix if needed

# Weather API settings (defaults)
API_KEY = "5ae04d623af44c5fa48154438251102"

# ---------------------------------------------------------------------------
# Dashboard HTML template (unchanged except for dynamic container and location)
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weather and Diagnosis Data</title>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; margin: 0; padding: 0; }
    .date-container { margin: 20px; padding: 10px; border: 1px solid #ccc; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .image-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 20px; }
    img { width: 100%; height: auto; border: 1px solid #ccc; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); cursor: pointer; transition: transform 0.3s ease; }
    #zoomed-image { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; flex-direction: column; }
    #zoom-img { max-width: 90%; max-height: 90%; border-radius: 8px; }
    .nav-buttons { position: absolute; top: 50%; width: 100%; display: flex; justify-content: space-between; }
    .nav-button { background: rgba(255,255,255,0.6); border: none; font-size: 30px; cursor: pointer; padding: 10px; border-radius: 50%; transition: 0.3s; }
    .nav-button:hover { background: rgba(255,255,255,0.9); }
    .close-button { position: absolute; top: 20px; right: 20px; background: rgba(255,255,255,0.6); border: none; font-size: 24px; cursor: pointer; padding: 10px; border-radius: 50%; transition: 0.3s; }
    .close-button:hover { background: rgba(255,255,255,0.9); }
    #legend-container { margin: 20px auto; padding: 15px; border: 1px solid #ccc; border-radius: 8px; background: #222; color: #fff; display: inline-block; text-align: left; }
    .legend-item { display: flex; align-items: center; font-size: 20px; margin-bottom: 5px; }
    .legend-icon { font-size: 25px; margin-right: 10px; }
  </style>
</head>
<body>
  <h1>Diagnostic Figures of Pandora</h1>
  <div id="content"></div>
  <div id="zoomed-image">
    <button class="close-button" onclick="closeZoom()">✖</button>
    <div class="nav-buttons">
      <button class="nav-button" onclick="prevImage()">⬅</button>
      <button class="nav-button" onclick="nextImage()">➡</button>
    </div>
    <img id="zoom-img" src="" alt="Zoomed Image">
  </div>
  <div id="weather-legend"></div>

<script>
    let images = [];
    let currentIndex = 0;

    // Fetch file URLs using the dynamic container name
    fetch('/get-files?container={{ container }}')
      .then(response => response.json())
      .then(data => {
        const content = document.getElementById('content');
        const sortedDates = Object.keys(data).sort((a, b) => new Date(b) - new Date(a));

        sortedDates.forEach(date => {
          const dateContainer = document.createElement('div');
          dateContainer.className = 'date-container';

          const dateObj = new Date(date);
          dateObj.setDate(dateObj.getDate() - 1); // previous day
          const previousDate = dateObj.toISOString().split('T')[0];
          
          const options = { year: 'numeric', month: 'short', day: 'numeric' };
          const formattedDate = new Date(date).toLocaleDateString(undefined, options);

          const dateTitle = document.createElement('h2');
          dateTitle.textContent = `Date: ${formattedDate}`;
          dateContainer.appendChild(dateTitle);

          const imageContainer = document.createElement('div');
          imageContainer.className = 'image-container';

          data[date].forEach(url => {
            images.push(url);
            const img = document.createElement('img');
            img.src = url;
            img.alt = 'Image';
            img.onclick = function() { zoomImage(images.indexOf(url)); };
            imageContainer.appendChild(img);
          });
          dateContainer.appendChild(imageContainer);
          content.appendChild(dateContainer);

          // Weather data section
          const chartDiv = document.createElement('div');
          chartDiv.id = `chart-${date}`;
          dateContainer.appendChild(chartDiv);

          fetch(`/get-weather-data/${previousDate}?location={{ location }}`)
            .then(response => response.json())
            .then(weatherData => {
              if (weatherData.error) {
                console.error("Weather API Error:", weatherData.error);
                return;
              }
              const times = weatherData.map(entry => entry.time.split(" ")[1]);
              const conditions = weatherData.map(entry => entry.condition);
              const weatherIcons = {
                "Sunny": "☀️",
                "Clear": "🌟",
                "Partly cloudy": "⛅",
                "Cloudy": "☁️",
                "Overcast": "🌥",
                "Mist": "🌫",
                "Fog": "🌫",
                "Patchy rain possible": "🌧",
                "Rain": "🌧",
                "Snow": "❄️",
                "Moderate snow": "❄️❄️",
                "Heavy snow": "❄️❄️❄️",
                "Thunderstorm": "⛈"
              };

              function createLegend() {
                const legendContainer = document.getElementById("weather-legend");
                legendContainer.innerHTML = "";
                Object.entries(weatherIcons).forEach(([cond, icon]) => {
                  const legendItem = document.createElement("div");
                  legendItem.classList.add("legend-item");
                  const iconSpan = document.createElement("span");
                  iconSpan.classList.add("legend-icon");
                  iconSpan.textContent = icon;
                  const textSpan = document.createElement("span");
                  textSpan.textContent = cond;
                  legendItem.appendChild(iconSpan);
                  legendItem.appendChild(textSpan);
                  legendContainer.appendChild(legendItem);
                });
              }
              document.addEventListener("DOMContentLoaded", createLegend);
              const conditionsWithIcons = conditions.map(cond => weatherIcons[cond] || cond);
              const traces = [{
                x: times,
                y: conditionsWithIcons,
                mode: 'text',
                type: 'scatter',
                text: conditionsWithIcons,
                textposition: 'middle center',
                textfont: { size: 25 },
                marker: { size: 0 }
              }];
              const layout = {
                title: { text: `Weather Conditions on ${formattedDate}`, font: { color: 'white' } },
                xaxis: { title: 'Time', tickangle: -45, color: 'white', gridcolor: '#444' },
                yaxis: { title: 'Condition', color: 'white', gridcolor: '#444' },
                showlegend: false,
                template: "plotly_dark",
                plot_bgcolor: 'black',
                paper_bgcolor: 'black'
              };
              Plotly.newPlot(chartDiv.id, traces, layout);
            })
            .catch(error => console.error("Error fetching weather data:", error));
        });
      })
      .catch(error => console.error("Error fetching files:", error));

    function zoomImage(index) {
      currentIndex = index;
      document.getElementById('zoom-img').src = images[currentIndex];
      document.getElementById('zoomed-image').style.display = 'flex';
    }
    function closeZoom() { document.getElementById('zoomed-image').style.display = 'none'; }
    function prevImage() { if (currentIndex > 0) { currentIndex--; document.getElementById('zoom-img').src = images[currentIndex]; } }
    function nextImage() { if (currentIndex < images.length - 1) { currentIndex++; document.getElementById('zoom-img').src = images[currentIndex]; } }
    document.addEventListener("keydown", function(event) {
      if (document.getElementById('zoomed-image').style.display === 'flex') {
        if (event.key === "ArrowLeft") prevImage();
        if (event.key === "ArrowRight") nextImage();
        if (event.key === "Escape") closeZoom();
      }
    });
</script>

</body>
</html>
"""

# ---------------------------------------------------------------------------
# Index page using a dropdown menu for Pandora options
# ---------------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Select Pandora Option</title>
      <style>
        body { font-family: Arial, sans-serif; text-align: center; padding-top: 50px; }
        form { display: inline-block; text-align: left; }
        label { display: block; margin-bottom: 5px; }
        select { margin-bottom: 15px; width: 100%; padding: 8px; }
        button { padding: 10px 20px; }
      </style>
    </head>
    <body>
      <h1>Select Pandora Number and Location</h1>
      <form action="/dashboard" method="post">
        <label for="pandora">Pandora Options:</label>
        <select id="pandora" name="pandora" required>
          <option value="">-- Select an option --</option>
          <option value="002|Greenbelt MD">Test NASA 002 (002)</option>
          <option value="032|Greenbelt MD">Test NASA 032 (032)</option>
          <option value="071|Greenbelt MD">Test NASA 070 (071)</option>
          <option value="211|Agam">Agam (211)</option>
          <option value="61|AldineTX">AldineTX (61)</option>
          <option value="129|AliceSprings">AliceSprings (129)</option>
          <option value="65|Altzomoni">Altzomoni (65)</option>
          <option value="207|ArlingtonTX">ArlingtonTX (207)</option>
          <option value="119|Athens-NOA">Athens-NOA (119)</option>
          <option value="158|AtlantaGA-Conyers">AtlantaGA-Conyers (158)</option>
          <option value="173|AtlantaGA-GATech">AtlantaGA-GATech (173)</option>
          <option value="237|AtlantaGA-SouthDeKalb">AtlantaGA-SouthDeKalb (237)</option>
          <option value="158|AtlantaGA">AtlantaGA (158)</option>
          <option value="257|AustinTX">AustinTX (257)</option>
          <option value="210|Bandung">Bandung (210)</option>
          <option value="190|Bangkok">Bangkok (190)</option>
          <option value="78|Banting">Banting (78)</option>
          <option value="38|Bayonne NJ">BayonneNJ (38)</option>
          <option value="171|Beijing-RADI">Beijing-RADI (171)</option>
          <option value="80|BeltsvilleMD">BeltsvilleMD (80)</option>
          <option value="132|Berlin">Berlin (132)</option>
          <option value="139|BlueHillMA">BlueHillMA (139)</option>
          <option value="155|BostonMA">BostonMA (155)</option>
          <option value="204|BoulderCO-NCAR">BoulderCO-NCAR (204)</option>
          <option value="57|BoulderCO">BoulderCO (57)</option>
          <option value="21|Bremen Germany">Bremen (21)</option>
          <option value="134|BristolPA">BristolPA (134)</option>
          <option value="147|BronxNY">BronxNY (147)</option>
          <option value="162|Brussels-Uccle">Brussels-Uccle (162)</option>
          <option value="111|Bucharest">Bucharest (111)</option>
          <option value="114|BuenosAires">BuenosAires (114)</option>
          <option value="206|BuffaloNY">BuffaloNY (206)</option>
          <option value="20|Busan South Korea">Busan (20)</option>
          <option value="118|Cabauw">Cabauw (118)</option>
          <option value="141|Calakmul">Calakmul (141)</option>
          <option value="281|CambridgeBay">CambridgeBay (281)</option>
          <option value="26|Cambridge MA">CambridgeMA (26)</option>
          <option value="260|CameronLA">CameronLA (260)</option>
          <option value="184|CapeElizabethME">CapeElizabethME (184)</option>
          <option value="225|Cebu">Cebu (225)</option>
          <option value="166|ChapelHillNC">ChapelHillNC (166)</option>
          <option value="31|CharlesCityVA">CharlesCityVA (31)</option>
          <option value="153|ChelseaMA">ChelseaMA (153)</option>
          <option value="213|ChiangMai">ChiangMai (213)</option>
          <option value="249|ChicagoIL">ChicagoIL (249)</option>
          <option value="67|Cologne">Cologne (67)</option>
          <option value="124|ComodoroRivadavia">ComodoroRivadavia (124)</option>
          <option value="113|Cordoba">Cordoba (113)</option>
          <option value="179|CornwallCT">CornwallCT (179)</option>
          <option value="258|CorpusChristiTX">CorpusChristiTX (258)</option>
          <option value="229|Daegu">Daegu (229)</option>
          <option value="217|Dalanzadgad">Dalanzadgad (217)</option>
          <option value="120|Davos">Davos (120)</option>
          <option value="39|Dearborn MI">DearbornMI (39)</option>
          <option value="82|DeBilt">DeBilt (82)</option>
          <option value="76|Dhaka">Dhaka (76)</option>
          <option value="103|Downsview">Downsview (103)</option>
          <option value="185|EastProvidenceRI">EastProvidenceRI (185)</option>
          <option value="74|EdwardsCA">EdwardsCA (74)</option>
          <option value="108|Egbert">Egbert (108)</option>
          <option value="75|EssexMD">EssexMD (75)</option>
          <option value="280|Eureka-0PAL">Eureka-0PAL (280)</option>
          <option value="144|Eureka-PEARL">Eureka-PEARL (144)</option>
          <option value="174|FairbanksAK">FairbanksAK (174)</option>
          <option value="60|Fajardo">Fajardo (60)</option>
          <option value="122|FortMcKay">FortMcKay (122)</option>
          <option value="205|FortYatesND">FortYatesND (205)</option>
          <option value="199|Fukuoka">Fukuoka (199)</option>
          <option value="230|Gongju-KNU">Gongju-KNU (230)</option>
          <option value="238|Granada">Granada (238)</option>
          <option value="200|GrandForksND">GrandForksND (200)</option>
          <option value="2|Greenbelt MD">GreenbeltMD (2)</option>
          <option value="32|Greenbelt MD">GreenbeltMD (32)</option>                                  
          <option value="250|Haldwani">Haldwani-ARIES (250)</option>
          <option value="156|Hampton VA">HamptonVA-HU (156)</option>
          <option value="37|Hampton VA">HamptonVA (37)</option>
          <option value="133|Heidelberg">Heidelberg (133)</option>
          <option value="105|Helsinki">Helsinki (105)</option>
          <option value="261|Houston TX-SanJacinto">HoustonTX-SanJacinto (261)</option>
          <option value="25|Houston TX">HoustonTX (25)</option>
          <option value="66|Huntsville AL">HuntsvilleAL (66)</option>
          <option value="219|Ilocos">Ilocos (219)</option>
          <option value="189|Incheon">Incheon-ESC (189)</option>
          <option value="106|Innsbruck">Innsbruck (106)</option>
          <option value="246|IowaCityIA-WHS">IowaCityIA-WHS (246)</option>
          <option value="73|Islamabad-NUST">Islamabad-NUST (73)</option>
          <option value="101|Izana">Izana (101)</option>
          <option value="241|Jeonju">Jeonju (241)</option>
          <option value="30|Juelich Germany">Juelich (30)</option>
          <option value="167|KenoshaWI">KenoshaWI (167)</option>
          <option value="198|Kobe">Kobe (198)</option>
          <option value="239|Kosetice">Kosetice (239)</option>
          <option value="283|LaPaz">LaPaz (283)</option>
          <option value="11|LaPorteTX">LaPorteTX (11)</option>
          <option value="188|LapwaiID">LapwaiID (188)</option>
          <option value="143|LibertyTX">LibertyTX (143)</option>
          <option value="130|Lindenberg">Lindenberg (130)</option>
          <option value="183|LondonderryNH">LondonderryNH (183)</option>
          <option value="107|LynnMA">LynnMA (107)</option>
          <option value="186|MadisonCT">MadisonCT (186)</option>
          <option value="165|ManhattanKS">ManhattanKS (165)</option>
          <option value="135|ManhattanNY-CCNY">ManhattanNY-CCNY (135)</option>
          <option value="56|MaunaLoaHI">MaunaLoaHI (56)</option>
          <option value="142|MexicoCity-UNAM">MexicoCity-UNAM (142)</option>
          <option value="157|MexicoCity-Vallejo">MexicoCity-Vallejo (157)</option>
          <option value="256|MiamiFL-FIU">MiamiFL-FIU (256)</option>
          <option value="34|MountainView CA">MountainViewCA (34)</option>
          <option value="197|Nagoya">Nagoya (197)</option>
          <option value="251|Nainital-ARIES">Nainital-ARIES (251)</option>
          <option value="69|NewBrunswickNJ">NewBrunswickNJ (69)</option>
          <option value="64|NewHavenCT">NewHavenCT (64)</option>
          <option value="236|NewLondonCT">NewLondonCT (236)</option>
          <option value="85|NewOrleansLA-XULA">NewOrleansLA-XULA (85)</option>
          <option value="152|NyAlesund">NyAlesund (152)</option>
          <option value="51|OldFieldNY">OldFieldNY (51)</option>
          <option value="131|Palau">Palau (131)</option>
          <option value="221|Palawan">Palawan (221)</option>
          <option value="166|PhiladelphiaPA">PhiladelphiaPA (166)</option>
          <option value="215|PhnomPenh">PhnomPenh (215)</option>
          <option value="187|PittsburghPA">PittsburghPA (187)</option>
          <option value="212|Pontianak">Pontianak (212)</option>
          <option value="53|Potchefstroom-METSI">Potchefstroom-METSI (53)</option>
          <option value="55|QueensNY">QueensNY (55)</option>
          <option value="224|QuezonCity">QuezonCity (224)</option>
          <option value="52|RichmondCA">RichmondCA (52)</option>
          <option value="138|Rome-IIA">Rome-IIA (138)</option>
          <option value="115|Rome">Rome-ISAC (115)</option>
          <option value="117|Rome-SAP">Rome-SAP (117)</option>
          <option value="84|Rotterdam-Haven">Rotterdam-Haven (84)</option>
          <option value="72|SaltLakeCityUT-Hawthorne">SaltLakeCityUT-Hawthorne (72)</option>
          <option value="154|SaltLakeCityUT">SaltLakeCityUT (154)</option>
          <option value="181|SanJoseCA">SanJoseCA (181)</option>
          <option value="195|Sapporo">Sapporo (195)</option>
          <option value="164|Seosan">Seosan (164)</option>
          <option value="235|Seoul-KU">Seoul-KU (235)</option>
          <option value="149|Seoul-SNU">Seoul-SNU (149)</option>
          <option value="27|Seoul">Seoul (27)</option>
          <option value="77|Singapore-NUS">Singapore-NUS (77)</option>
          <option value="214|Songkhla">Songkhla (214)</option>
          <option value="139|SouthJordanUT">SouthJordanUT (139)</option>
          <option value="109|StGeorge">StGeorge (109)</option>
          <option value="123|StonyPlain">StonyPlain (123)</option>
          <option value="231|Suwon-USW">Suwon-USW (231)</option>
          <option value="147|SWDetroitMI">SWDetroitMI (147)</option>
          <option value="182|Tel-Aviv">Tel-Aviv (182)</option>
          <option value="240|Thessaloniki">Thessaloniki (240)</option>
          <option value="192|Tokyo-Sophia">Tokyo-Sophia (192)</option>
          <option value="194|Tokyo-TMU">Tokyo-TMU (194)</option>
          <option value="243|Toronto-CNTower">Toronto-CNTower (243)</option>
          <option value="145|Toronto-Scarborough">Toronto-Scarborough (145)</option>
          <option value="108|Toronto-West">Toronto-West (108)</option>
          <option value="242|Trollhaugen">Trollhaugen (242)</option>
          <option value="163|Tsukuba-NIES-West">Tsukuba-NIES-West (163)</option>
          <option value="176|Tsukuba-NIES">Tsukuba-NIES (176)</option>
          <option value="193|Tsukuba">Tsukuba (193)</option>
          <option value="254|TubaCityAZ">TubaCityAZ (254)</option>
          <option value="253|TucsonAZ">TucsonAZ (253)</option>
          <option value="248|TurlockCA">TurlockCA (248)</option>
          <option value="259|TylerTX">TylerTX (259)</option>
          <option value="216|Ulaanbaatar">Ulaanbaatar (216)</option>
          <option value="150|Ulsan">Ulsan (150)</option>
          <option value="218|Vientiane">Vientiane (218)</option>
          <option value="255|VirginiaBeachVA-CBBT">VirginiaBeachVA-CBBT (255)</option>
          <option value="207|WacoTX">WacoTX (207)</option>
          <option value="159|Wakkerstroom">Wakkerstroom (159)</option>
          <option value="40|WallopsIslandVA">WallopsIslandVA (40)</option>
          <option value="270|Warsaw-UW">Warsaw-UW (270)</option>
          <option value="140|WashingtonDC">WashingtonDC (140)</option>
          <option value="177|WestportCT">WestportCT (177)</option>
          <option value="247|WhittierCA">WhittierCA (247)</option>
          <option value="208|Windsor-West">Windsor-West (208)</option>
          <option value="68|WrightwoodCA">WrightwoodCA (68)</option>
          <option value="146|Yokosuka">Yokosuka (146)</option>
          <option value="232|Yongin">Yongin (232)</option>
        </select>
        <button type="submit">Submit</button>
      </form>
    </body>
    </html>
    """)

# ---------------------------------------------------------------------------
# Dashboard page that processes the selected Pandora option
# ---------------------------------------------------------------------------
@app.route('/dashboard', methods=['POST'])
def dashboard():
    # Expecting a value like "211|Agam"
    selected = request.form.get('pandora')
    if not selected or "|" not in selected:
        return "Invalid selection", 400
    number_str, location_input = selected.split("|")
    # Ensure the number is 3 digits (pad with zeros if necessary)
    container = "pan" + number_str.zfill(3)
    return render_template_string(HTML_TEMPLATE, container=container, location=location_input)

# ---------------------------------------------------------------------------
# Endpoint for fetching files from Azure Blob Storage using the dynamic container
# ---------------------------------------------------------------------------
@app.route('/get-files', methods=['GET'])
def get_files():
    container = request.args.get('container')
    if not container:
        return jsonify({"error": "Container not provided"}), 400
    try:
        blob_service_client = BlobServiceClient(account_url=ACCOUNT_URL, credential=ACCOUNT_KEY)
        container_client = blob_service_client.get_container_client(container)
        blobs = container_client.list_blobs(name_starts_with=BLOB_PREFIX)
        files_by_date = {}

        for blob in blobs:
            if blob.name.endswith('.jpeg'):
                match = re.search(r"_(\d{8})T", blob.name)
                if match:
                    date_str = match.group(1)
                    date_obj = datetime.strptime(date_str, "%Y%m%d")
                    formatted_date = date_obj.strftime("%Y-%m-%d")
                    sas_token = generate_blob_sas(
                        account_name=ACCOUNT_NAME,
                        container_name=container,
                        blob_name=blob.name,
                        account_key=ACCOUNT_KEY,
                        permission=BlobSasPermissions(read=True),
                        expiry=datetime.utcnow() + timedelta(days=1)
                    )
                    blob_url = f"{ACCOUNT_URL}/{container}/{blob.name}?{sas_token}"
                    files_by_date.setdefault(formatted_date, []).append(blob_url)

        sorted_files_by_date = dict(sorted(files_by_date.items(), key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"), reverse=True))
        return jsonify(sorted_files_by_date)
    except Exception as e:
        print(f"Error fetching files: {e}")
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------------------
# Endpoint for fetching weather data using the dynamic location
# ---------------------------------------------------------------------------
@app.route('/get-weather-data/<date>', methods=['GET'])
def get_weather_data(date):
    location_input = request.args.get('location')
    if not location_input:
        return jsonify({"error": "Location not provided"}), 400
    try:
        url = f"https://api.weatherapi.com/v1/history.json?key={API_KEY}&q={location_input}&dt={date}"
        response = requests.get(url)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch weather data: {response.text}"}), 500
        data = response.json()
        weather_data = []
        for hour in data.get('forecast', {}).get('forecastday', [{}])[0].get('hour', []):
            weather_data.append({
                'time': hour.get('time', 'N/A'),
                'condition': hour.get('condition', {}).get('text', 'N/A')
            })
        return jsonify(weather_data)
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)