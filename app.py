# app.py
import os
import time
from pathlib import Path
from typing import Dict
import requests
import boto3
from gtts import gTTS
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv

load_dotenv()

# ========== CONFIG ==========
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY")  # <-- set in your env
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
AUDIO_DIR = Path("audio")
AUDIO_DIR.mkdir(exist_ok=True)
sessions: Dict[str, Dict] = {}  # in-memory session
# ============================

app = FastAPI()
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# --------------------
# Helpers
# --------------------
def get_weather_for_place(city_or_district: str):
    """Get current weather from OpenWeatherMap for a city/district."""
    if not OPENWEATHER_KEY:
        print("DEBUG: Missing OPENWEATHER_KEY")
        return {"desc": "clear sky", "temp": "unknown"}
    try:
        q = f"{city_or_district},IN"
        url = f"http://api.openweathermap.org/data/2.5/weather?q={requests.utils.requote_uri(q)}&appid={OPENWEATHER_KEY}&units=metric"
        r = requests.get(url, timeout=10).json()
        if r.get("cod") == 200:
            desc = r["weather"][0]["description"]
            temp = r["main"]["temp"]
            return {"desc": desc, "temp": temp}
        print("DEBUG: OpenWeather error:", r)
        return {"desc": "clear sky", "temp": "unknown"}
    except Exception as e:
        print("DEBUG: Exception in get_weather_for_place:", e)
        return {"desc": "clear sky", "temp": "unknown"}


def get_tomato_price_demo(city: str):
    """Demo fallback for tomato price. Replace with real API."""
    mapping = {
        "Ahmedabad": 28,
        "Surat": 35,
        "Mumbai": 45,
        "Delhi": 30,
        "Bengaluru": 40,
        "Chennai": 38,
        "Hyderabad": 34,
        "Kolkata": 32,
    }
    for key in mapping:
        if key.lower() in city.lower():
            return mapping[key]
    return 32


def synthesize_aws_polly(text: str, out_path: Path, voice_id: str = "Aditi"):
    """Synthesize via AWS Polly."""
    polly = boto3.client("polly", region_name=AWS_REGION)
    try:
        resp = polly.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=voice_id, Engine="neural"
        )
    except Exception:
        resp = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice_id)

    stream = resp.get("AudioStream")
    if stream:
        with open(out_path, "wb") as f:
            f.write(stream.read())
        return True
    return False


def synthesize_gtts(text: str, out_path: Path, lang_code: str = "gu"):
    """Use gTTS for Gujarati (or other languages supported by gTTS)."""
    try:
        tts = gTTS(text=text, lang=lang_code)
        tts.save(str(out_path))
        return True
    except Exception:
        return False


def build_message(lang: str, city: str, weather: dict, price: int):
    """Return localized message text for given language code."""
    desc = weather.get("desc", "clear")
    temp = weather.get("temp", "unknown")

    if lang == "en":
        return f"Current weather in {city}: {desc}, temperature {temp} degrees Celsius. Today's tomato price is {price} rupees per kilogram."
    if lang == "hi":
        return f"{city} में मौजूदा मौसम {desc} है, तापमान {temp} डिग्री सेल्सियस। आज टमाटर का भाव {price} रुपये प्रति किलो है।"
    if lang == "gu":
        return f"{city} માં હાલનું હવામાન {desc} છે, તાપમાન {temp} ડિગ્રિ સેલ્સિયસ. આજે ટામેટાની કિંમત {price} રૂપિયા પ્રતિ કિલોગ્રામ છે."

    return f"Current weather in {city}: {desc}, temperature {temp} degrees Celsius. Tomato price: {price} rupees per kilogram."


def map_pincode_to_city(pincode: str):
    """Map Indian pincode to city + state (basic ranges + known cities)."""
    if not pincode or not pincode.isdigit():
        return "Unknown City", "Unknown State"

    pin = int(pincode)

    # Direct city mapping (important known pincodes)
    city_map = {
        "110001": ("New Delhi", "Delhi"),
        "400001": ("Mumbai", "Maharashtra"),
        "560001": ("Bengaluru", "Karnataka"),
        "600001": ("Chennai", "Tamil Nadu"),
        "700001": ("Kolkata", "West Bengal"),
        "500001": ("Hyderabad", "Telangana"),
        "380001": ("Ahmedabad", "Gujarat"),
    }
    if str(pin) in city_map:
        return city_map[str(pin)]

    # State range mapping fallback
    ranges = [
        (110000, 110099, "Delhi"),
        (400000, 444999, "Maharashtra"),
        (560000, 591999, "Karnataka"),
        (600000, 643999, "Tamil Nadu"),
        (670000, 695999, "Kerala"),
        (700000, 749999, "West Bengal"),
        (500000, 534999, "Andhra Pradesh"),
        (505000, 535999, "Telangana"),
        (380000, 396999, "Gujarat"),
        (180000, 194999, "Jammu & Kashmir"),
        (750000, 769999, "Odisha"),
        (800000, 849999, "Bihar"),
        (820000, 839999, "Jharkhand"),
        (140000, 160999, "Punjab"),
        (160000, 179999, "Haryana"),
        (201000, 285999, "Uttar Pradesh"),
        (301000, 345999, "Rajasthan"),
        (360000, 389999, "Gujarat"),
        (793000, 799999, "Meghalaya"),
        (781000, 788999, "Assam"),
    ]

    for start, end, state in ranges:
        if start <= pin <= end:
            return f"Pincode {pincode}", state

    return "Unknown City", "Unknown State"


# --------------------
# IVR Endpoints
# --------------------
@app.post("/ivr")
async def ivr_entry(request: Request):
    resp = VoiceResponse()
    gather = Gather(num_digits=1, action="/language", method="POST")
    gather.say("Press 1 for English. Press 2 for Hindi. Press 3 for Gujarati.", language="en-IN")
    resp.append(gather)
    resp.redirect("/ivr")
    return Response(content=str(resp), media_type="application/xml")


@app.post("/language")
async def handle_language(request: Request, Digits: str = Form(...)):
    form = await request.form()
    call_sid = form.get("CallSid")

    lang = "en"
    if Digits == "1":
        lang = "en"
    elif Digits == "2":
        lang = "hi"
    elif Digits == "3":
        lang = "gu"

    sessions[call_sid] = {"lang": lang, "pincode_digits": [], "step": 1}

    # Go to PIN code flow
    resp = VoiceResponse()
    gather = Gather(action="/collect_digit", num_digits=1, method="POST", timeout=5)
    gather.say("Please enter the first digit of your six digit pincode.")
    resp.append(gather)
    return Response(content=str(resp), media_type="application/xml")


@app.post("/collect_digit")
async def collect_digit(request: Request, Digits: str = Form(...)):
    form = await request.form()
    call_sid = form.get("CallSid")
    session = sessions.get(call_sid, {"lang": "en", "pincode_digits": [], "step": 1})

    step = session["step"]
    digits = session["pincode_digits"]
    digits.append(Digits)

    session["pincode_digits"] = digits
    session["step"] = step + 1
    sessions[call_sid] = session

    resp = VoiceResponse()
    if step < 6:
        gather = Gather(action="/collect_digit", num_digits=1, method="POST", timeout=5)
        gather.say(f"Please enter digit number {step+1} of your pincode.")
        resp.append(gather)
    else:
        full_pincode = "".join(digits)
        city, state = map_pincode_to_city(full_pincode)
        # use city if known, else fall back to state
        location_name = city if "Pincode" not in city and "Unknown" not in city else state

        weather = get_weather_for_place(location_name)
        price = get_tomato_price_demo(location_name)
        message_text = build_message(session["lang"], f"{city}, {state}", weather, price)

        filename = f"{call_sid}_{int(time.time())}_{session['lang']}.mp3"
        out_path = AUDIO_DIR / filename

        ok = False
        if session["lang"] in ("en", "hi"):
            voice_map = {"en": "Aditi", "hi": "Aditi"}
            try:
                ok = synthesize_aws_polly(message_text, out_path, voice_id=voice_map.get(session["lang"], "Aditi"))
            except Exception:
                ok = False
        elif session["lang"] == "gu":
            ok = synthesize_gtts(message_text, out_path, lang_code="gu")

        if ok:
            host = request.headers.get("host")
            scheme = request.url.scheme
            audio_url = f"{scheme}://{host}/audio/{filename}"
            resp.play(audio_url)
        else:
            resp.say(message_text, language="en-IN")

        resp.hangup()
        sessions.pop(call_sid, None)

    return Response(content=str(resp), media_type="application/xml")
