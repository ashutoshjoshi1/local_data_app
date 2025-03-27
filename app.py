from flask import Flask, jsonify, render_template_string, request, Response, redirect, url_for
import os, re, requests
from datetime import datetime, timedelta
from google.cloud import storage

app = Flask(__name__)
API_KEY = "5ae04d623af44c5fa48154438251102"

# -------------------------------
# Google Cloud Storage Setup
# -------------------------------
GCP_CREDENTIALS_PATH = "ornate-course-442519-s9-29052f520c7f.json"
BUCKET_NAME = "all-charts"
storage_client = storage.Client.from_service_account_json(GCP_CREDENTIALS_PATH)
bucket = storage_client.bucket(BUCKET_NAME)

# -------------------------------
# Helper function to get device status from status.txt
# -------------------------------
def get_status(pandora):
    """Fetch the status.txt from the bucket under Pan{pandora}/status.txt and extract the date.
    Expected content example:
      Pandora2s1_GreenbeltMD_20250327_L0_part50.txt
    If the file is not present or cannot be parsed, returns ('grey', 'Not Sure').
    Otherwise, based on the extracted date:
      - Green: if the date is today or yesterday.
      - Yellow: if the date is within the last 7 days.
      - Red: if the date is older than 7 days.
    """
    blob_name = f"Pan{pandora}/status.txt"
    blob = bucket.blob(blob_name)
    try:
        status_line = blob.download_as_text().strip()
    except Exception as e:
        print(f"Error reading status.txt: {e}")
        return ("grey", "Not Sure")
    
    # Extract date using pattern: _YYYYMMDD_
    match = re.search(r"_(\d{8})_", status_line)
    if match:
        date_str = match.group(1)
        try:
            file_date = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception as e:
            print(f"Error parsing date from status.txt: {e}")
            return ("grey", "Not Sure")
    else:
        return ("grey", "Not Sure")
    
    today = datetime.today().date()
    diff = (today - file_date).days
    if diff <= 1:
        return ("green", "The device is working fine. All files are generated perfectly.")
    elif diff <= 7:
        return ("yellow", "Check the device in teamviewer. There might be some error.")
    else:
        return ("red", "Please check the device ASAP. It is not generating L0 files. Maybe the application is stopped.")

# -------------------------------
# HTML Template for the view route
# -------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pandora {{ pandora_number }} - {{ folder.capitalize() }}</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; background: #121212; color: white; }
    .date-container { margin: 20px auto; padding: 10px; border: 1px solid #444; border-radius: 8px;
                      box-shadow: 0 4px 6px rgba(0,0,0,0.2); max-width: 90%; }
    .image-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                       gap: 20px; padding: 10px; }
    img { width: 100%; border-radius: 8px; cursor: pointer; transition: transform 0.3s ease; }
    img:hover { transform: scale(1.05); }
    .legend-item { display: flex; align-items: center; font-size: 16px; margin-bottom: 5px;
                   justify-content: center; }
    .legend-icon { font-size: 20px; margin-right: 5px; }
    /* Zoomed Image Container */
    #zoomed-image {
      display: none;
      position: fixed;
      top: 0; left: 0;
      width: 100vw; height: 100vh;
      background: rgba(0,0,0,0.8);
      justify-content: center;
      align-items: center;
    }
  </style>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
  <h1>
    {{ folder.capitalize() }} for Pandora {{ pandora_number }}
    <span style="color: {{ status_color }};">({{ status_message }})</span>
  </h1>
  <div id="content"></div>
  <!-- Zoomed Image Container -->
  <div id="zoomed-image">
    <button onclick="closeZoom()" style="position: absolute; top: 20px; right: 20px; background: rgba(255,255,255,0.6); border: none; font-size: 24px; cursor: pointer;">&times;</button>
    <div style="position: relative; max-width: 90%; max-height: 90%;">
      <img id="zoom-img" src="" alt="Zoomed Image" style="max-width: 100%; max-height: 100%; display: block; margin: auto;">
      <button onclick="prevImage()" style="position: absolute; top: 50%; left: 10px; transform: translateY(-50%); background: rgba(255,255,255,0.6); border: none; font-size: 30px; cursor: pointer;">⬅</button>
      <button onclick="nextImage()" style="position: absolute; top: 50%; right: 10px; transform: translateY(-50%); background: rgba(255,255,255,0.6); border: none; font-size: 30px; cursor: pointer;">➡</button>
    </div>
  </div>
  <script>
    let allImages = [];
    // Fetch files, then for each date (container) add images and its weather chart
    fetch('/get-files/{{ pandora_number }}/{{ folder }}')
      .then(res => res.json())
      .then(data => {
        const content = document.getElementById('content');
        // Sort and select latest 10 dates
        const sortedDates = Object.keys(data.files)
                              .sort((a, b) => new Date(b) - new Date(a))
                              .slice(0, 10);
        sortedDates.forEach(date => {
          const formattedDate = new Date(date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
          // Create container for the date
          const dateContainer = document.createElement('div');
          dateContainer.className = 'date-container';
          dateContainer.innerHTML = `<h2>Date: ${formattedDate}</h2>`;
          // Create and append the image container
          const imageContainer = document.createElement('div');
          imageContainer.className = 'image-container';
          data.files[date].forEach(img => {
            const image = document.createElement('img');
            image.src = img;
            let index = allImages.length;
            allImages.push(img);
            image.onclick = function() { zoomImage(index); };
            imageContainer.appendChild(image);
          });
          dateContainer.appendChild(imageContainer);
          // Create chart div and append to the same container
          const chartDiv = document.createElement('div');
          chartDiv.id = `chart-${date}`;
          dateContainer.appendChild(chartDiv);
          content.appendChild(dateContainer);
          
          // Fetch weather data for this date and render chart in chartDiv.
          // Weather data is fetched for one day before the image date.
          fetch(`/get-weather-data/${date}?location={{ location }}`)
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
                "Clear": "🌤️",
                "Partly cloudy": "⛅",
                "Cloudy": "☁️",
                "Overcast": "🌥️",
                "Mist": "🌫️",
                "Fog": "🌫️",
                "Patchy rain possible": "🌦️",
                "Rain": "🌧️",
                "Light rain shower": "🌧️",
                "Patchy light rain": "🌧️",
                "Light rain": "☔",
                "Moderate rain": "🌧️🌧️",
                "Moderate or heavy rain shower": "⛈️💦",
                "Heavy rain at times": "🌧️🌧️🌧️",
                "Snow": "❄️",
                "Moderate snow": "🌨️",
                "Heavy snow": "❄️",
                "Thunderstorm": "⛈️"
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
              if (!document.getElementById("weather-legend") || !document.getElementById("weather-legend").hasChildNodes()) {
                const weatherLegend = document.createElement("div");
                weatherLegend.id = "weather-legend";
                document.body.appendChild(weatherLegend);
                createLegend();
              }
              const conditionsWithIcons = conditions.map(cond => {
                let trimmed = cond.trim();
                return weatherIcons[trimmed] || trimmed;
              });
              const traces = [{
                x: times,
                y: conditionsWithIcons,
                mode: 'text',
                type: 'scatter',
                text: conditionsWithIcons,
                textposition: 'middle center',
                textfont: { size: 25, family: "Apple Color Emoji,Segoe UI Emoji,NotoColorEmoji" },
                marker: { size: 0 }
              }];
              const layout = {
                title: { text: `Weather Conditions on ${formattedDate}`, font: { color: 'white' } },
                xaxis: { title: 'Time', tickangle: -45, color: 'white', gridcolor: '#444' },
                yaxis: { title: 'Condition', type: 'category', color: 'white', gridcolor: '#444' },
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
      
    let currentIndex = 0;
    function zoomImage(index) {
      currentIndex = index;
      document.getElementById('zoom-img').src = allImages[currentIndex];
      document.getElementById('zoomed-image').style.display = 'flex';
    }
    function closeZoom() {
      document.getElementById('zoomed-image').style.display = 'none';
    }
    function prevImage() {
      if (currentIndex > 0) {
        currentIndex--;
        document.getElementById('zoom-img').src = allImages[currentIndex];
      }
    }
    function nextImage() {
      if (currentIndex < allImages.length - 1) {
        currentIndex++;
        document.getElementById('zoom-img').src = allImages[currentIndex];
      }
    }
    document.addEventListener("keydown", function(event) {
      const zoomedImage = document.getElementById('zoomed-image');
      if (zoomedImage && zoomedImage.style.display === 'flex') {
        if (event.key === "ArrowLeft") {
          prevImage();
        } else if (event.key === "ArrowRight") {
          nextImage();
        } else if (event.key === "Escape") {
          closeZoom();
        }
      }
    });
  </script>
</body>
</html>
"""

# -------------------------------
# Helper function to list files from GCP bucket
# -------------------------------
def get_files_from_gcp(pandora, folder):
    """
    Lists image files from the GCP bucket under Pan{pandora}/{folder}/.
    It groups the images by date extracted from the filename (using pattern _YYYYMMDDT).
    """
    prefix = f"Pan{pandora}/{folder}/"
    blobs = bucket.list_blobs(prefix=prefix)
    files_by_date = {}
    for blob in blobs:
        filename = os.path.basename(blob.name)
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            match = re.search(r"_(\d{8})T", filename)
            if match:
                date_str = match.group(1)
                try:
                    date_obj = datetime.strptime(date_str, "%Y%m%d")
                    date_formatted = date_obj.strftime("%Y-%m-%d")
                    file_url = f"/files/{pandora}/{folder}/{filename}"
                    files_by_date.setdefault(date_formatted, []).append(file_url)
                except Exception as e:
                    print(f"Error parsing date from filename {filename}: {e}")
    return files_by_date

# -------------------------------
# Endpoint to get files grouped by date from GCP bucket
# -------------------------------
@app.route('/get-files/<pandora>/<folder>')
def get_files(pandora, folder):
    files_by_date = get_files_from_gcp(pandora, folder)
    return jsonify({"files": files_by_date})

# -------------------------------
# Endpoint to serve a file from the GCP bucket
# -------------------------------
@app.route('/files/<pandora>/<folder>/<filename>')
def serve_file(pandora, folder, filename):
    """
    Serves an image file from the GCP bucket.
    Blob name is constructed as Pan{pandora}/{folder}/{filename}.
    """
    blob_name = f"Pan{pandora}/{folder}/{filename}"
    blob = bucket.blob(blob_name)
    try:
        image_data = blob.download_as_bytes()
    except Exception as e:
        return f"Error: {e}", 404
    return Response(image_data, mimetype=blob.content_type or 'application/octet-stream')

# -------------------------------
# Endpoint to fetch weather data using WeatherAPI
# -------------------------------
@app.route('/get-weather-data/<date>', methods=['GET'])
def get_weather_data(date):
    location_input = request.args.get('location')
    if not location_input:
        return jsonify({"error": "Location not provided"}), 400
    try:
        # Subtract one day from the provided date
        original_date = datetime.strptime(date, "%Y-%m-%d")
        previous_date = original_date - timedelta(days=1)
        previous_date_str = previous_date.strftime("%Y-%m-%d")
        
        url = f"https://api.weatherapi.com/v1/history.json?key={API_KEY}&q={location_input}&dt={previous_date_str}"
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

# -------------------------------
# Home route (with form) and view route
# -------------------------------
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        # Expecting the drop-down selection to be in the form "pandora" with value "XXX|Location"
        pandora_full = request.form.get('pandora')
        if not pandora_full:
            return "No pandora selected.", 400
        parts = pandora_full.split('|')
        if len(parts) != 2:
            return "Invalid pandora selection.", 400
        pandora = parts[0]
        location = parts[1]
        return render_template_string(HTML_TEMPLATE,
                                      pandora_number=pandora,
                                      folder=request.form.get('folder'),
                                      location=location,
                                      **dict(zip(["status_color", "status_message"], get_status(pandora))))
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SciGlob NOps app</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; height: 100%; }
    body { background-color: #000; overflow: hidden; font-family: sans-serif; }
    .container { position: relative; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; flex-direction: column; }
    .background-light { position: absolute; width: 400px; height: 400px; opacity: 0.3; filter: blur(120px); }
    .light1 { background: #A855F7; animation: moveLight 8s infinite alternate ease-in-out; left: 0; top: 0; }
    .light2 { background: #F472B6; animation: moveLight2 10s infinite alternate ease-in-out; right: 0; bottom: 0; }
    @keyframes moveLight { 0%, 100% { transform: translate(-50%, -50%); } 50% { transform: translate(50%, 50%); } }
    @keyframes moveLight2 { 0%, 100% { transform: translate(50%, 50%); } 50% { transform: translate(-50%, -50%); } }
    .input-field { position: relative; width: 320px; padding: 12px 16px; font-size: 16px; color: #fff;
                   background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2);
                   border-radius: 8px; backdrop-filter: blur(10px); outline: none; transition: transform 0.3s ease-out;
                   margin-bottom: 10px; }
    .submit-button { padding: 10px 20px; font-size: 16px; color: #fff; background: rgba(255, 255, 255, 0.2);
                     border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 8px; backdrop-filter: blur(10px);
                     cursor: pointer; transition: background 0.3s ease-out; }
    .submit-button:hover { background: rgba(255, 255, 255, 0.3); }
    .focused { transform: translateY(-12px); }
    .animate-rise { animation: rise 0.5s ease-out forwards; }
    @keyframes rise { 0% { transform: translateY(0); } 40% { transform: translateY(-16px); } 100% { transform: translateY(-12px); } }
    ::placeholder { color: #ccc; }
    label { color: white; }
  </style>
</head>
<body>
  <div class="container">
    <div class="background-light light1"></div>
    <div class="background-light light2"></div>
    <div style="text-align: center; margin-bottom: 380px;">
      <img src="static/asset/sciglob.png" style="max-width: 1200px; height: auto;">
    </div>
   <form action="/" method="post" style="font-size: 28px;"> 
    <label for="pandora">Select Pandora:</label><br>
    <select name="pandora" id="pandora" style="font-size: 28px;">
      <option value="002|Greenbelt MD">002 - Greenbelt MD</option>
      <option value="032|Greenbelt MD">032 - Greenbelt MD</option>
      <option value="071|Greenbelt MD">071 - Greenbelt MD</option>
      <option value="057|Greenbelt MD">057 - Greenbelt MD</option>
      <option value="059|Greenbelt MD">059 - Greenbelt MD</option>
      <option value="079|Greenbelt MD">079 - Greenbelt MD</option>
      <option value="085|New Orleans">085 - New Orleans</option>
      <option value="157|Greenbelt MD">157 - Greenbelt MD</option>
      <option value="025|Houston TX">025 - Houston TX</option>
      <option value="040|Wallops island">040 - Wallops island</option>
      <option value="061|Aldine TX">061 - Aldine TX</option>
      <option value="081|Stockton IL">081 - Stockton IL</option>
      <option value="083|Bondville IL">083 - Bondville IL</option>
      <option value="087|Lapwai ID">087 - Lapwai ID</option>
      <option value="088|San Antonio TX">088 - UT San Antonio TX</option>
      <option value="143|Liberty TX">143 - Liberty TX</option>
      <option value="158|Atlanta GA">158 - Atlanta GA Conyers</option>
      <option value="173|Atlanta GA">173 - Atlanta GATech</option>
      <option value="204|Boulder CO">204 - Boulder CO NCAR</option>
      <option value="237|Atlant GA">237 - Atlant GA SouthDeKalb</option>
    </select>
    <br><br>
    <button type="submit" name="folder" value="diagnostic" style="font-size: 28px;">View Diagnostics</button>
    <button type="submit" name="folder" value="figures" style="font-size: 28px;">View Figures</button>
   </form>
  </div>
  <script>
    const input = document.getElementById("glassInput");
    if (input) {
      input.addEventListener("focus", function () { input.classList.add("animate-rise"); });
      input.addEventListener("animationend", function (e) { if (e.animationName === "rise") { input.classList.remove("animate-rise"); input.classList.add("focused"); } });
      input.addEventListener("blur", function () { input.classList.remove("focused"); });
    }
  </script>
</body>
</html>
    """

# -------------------------------
# Optional: Allow GET on /view to redirect to home
# -------------------------------
@app.route('/view', methods=['GET'])
def view_get():
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
