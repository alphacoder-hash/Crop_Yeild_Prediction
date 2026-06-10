from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.conf import settings
from django.core.mail import send_mail
from .forms import FarmInputForm, SignupForm, ContactForm
from .models import FarmInput, Recommendation, Contact
from .ml_model import yield_predictor
import requests
import os


def home(request):
    contact_form = ContactForm()
    return render(request, 'advisory/home.html', {'contact_form': contact_form})


@login_required(login_url='/login/')
def farm_input(request):
    if request.method == 'POST':
        form = FarmInputForm(request.POST)
        if form.is_valid():
            try:
                farm_input_obj = form.save()
                predicted_yield, confidence = yield_predictor.predict_yield(farm_input_obj)
                recommendations = yield_predictor.generate_recommendations(farm_input_obj, predicted_yield)
                if not all(key in recommendations for key in ['action_1', 'action_2', 'action_3', 'reasoning', 'estimated_gain']):
                    raise ValueError("Incomplete recommendation data generated")
                recommendation = Recommendation.objects.create(
                    farm_input=farm_input_obj,
                    predicted_yield=float(predicted_yield),
                    confidence_interval=str(confidence),
                    estimated_gain=float(recommendations['estimated_gain']),
                    action_1=str(recommendations['action_1']),
                    action_2=str(recommendations['action_2']),
                    action_3=str(recommendations['action_3']),
                    reasoning=str(recommendations['reasoning'])
                )
                messages.success(request, "AI recommendation generated successfully!")
                return redirect('recommendation', recommendation_id=recommendation.id)
            except Exception as e:
                messages.error(request, f"Error generating recommendation: {str(e)}. Please try again.")
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = FarmInputForm()
    return render(request, 'advisory/farm_input.html', {'form': form})


@login_required(login_url='/login/')
def recommendation(request, recommendation_id):
    try:
        rec = Recommendation.objects.get(id=recommendation_id)
        farm_input = rec.farm_input
        district_avg = yield_predictor.get_district_average(farm_input.district, farm_input.crop, farm_input.season)
        total_production = rec.predicted_yield * farm_input.field_area
        improvement = 0
        if district_avg > 0:
            improvement = ((rec.predicted_yield - district_avg) / district_avg) * 100
        context = {
            'recommendation': rec,
            'total_production': total_production,
            'yield_comparison': {
                'predicted': rec.predicted_yield,
                'district_avg': district_avg,
                'improvement': improvement
            }
        }
        return render(request, 'advisory/recommendation.html', context)
    except Recommendation.DoesNotExist:
        messages.error(request, "Recommendation not found.")
        return redirect('farm_input')
    except Exception as e:
        messages.error(request, f"Error loading recommendation: {str(e)}")
        return redirect('farm_input')


def about(request):
    return render(request, 'advisory/about.html')


def chatbot(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    user_message = request.POST.get('message', '').strip().lower()
    if not user_message:
        return JsonResponse({'error': 'Message is required'}, status=400)

    if any(w in user_message for w in ['how to use', 'how does', 'what is this', 'website', 'platform', 'help', 'guide', 'start', 'begin', 'register', 'signup', 'login', 'account']):
        response = ("Welcome to Krishi Salahkar! Here's how to use the platform:\n"
                    "1. Sign up / Log in to your account.\n"
                    "2. Go to 'Get Crop Advisory' and fill in your farm details.\n"
                    "3. Get AI-powered yield predictions and personalized recommendations.\n"
                    "4. Check the Weather section for local forecasts.\n"
                    "5. Use the Contact form for any queries.")
    elif 'rice' in user_message or 'paddy' in user_message:
        response = ("🌾 Rice (Paddy) Tips for Odisha:\n"
                    "• Best season: Kharif (June–November).\n"
                    "• Popular varieties: Naveen, Swarna, MTU-1010, Lalat.\n"
                    "• Soil: Alluvial or clay loam with good water retention.\n"
                    "• Apply NPK (60:30:30 kg/ha). Top-dress urea at tillering stage.\n"
                    "• Watch for blast, brown planthopper, and stem borer.\n"
                    "• Maintain 2–5 cm standing water during vegetative stage.")
    elif 'wheat' in user_message:
        response = ("🌾 Wheat Tips:\n"
                    "• Best season: Rabi (November–March).\n"
                    "• Varieties: HD-2967, GW-322, K-307.\n"
                    "• Sow at 100–125 kg seed/ha, 20 cm row spacing.\n"
                    "• Apply NPK (120:60:40 kg/ha). First irrigation at crown root stage (21 days).\n"
                    "• Watch for rust, aphids, and loose smut.")
    elif 'maize' in user_message or 'corn' in user_message:
        response = ("🌽 Maize Tips:\n"
                    "• Grows in Kharif and Rabi seasons.\n"
                    "• Varieties: DHM-117, Vivek-9, HQPM-1.\n"
                    "• Needs well-drained loamy soil.\n"
                    "• Apply NPK (120:60:40 kg/ha). Earthing up at 30 days.\n"
                    "• Watch for fall armyworm and stem borer.")
    elif 'groundnut' in user_message or 'peanut' in user_message:
        response = ("🥜 Groundnut Tips:\n"
                    "• Best season: Kharif (June–July sowing).\n"
                    "• Varieties: TAG-24, GG-20, Kadiri-3.\n"
                    "• Needs sandy loam, well-drained soil.\n"
                    "• Apply gypsum (400 kg/ha) at pegging stage.\n"
                    "• Watch for tikka leaf spot and white grub.")
    elif 'sugarcane' in user_message:
        response = ("🎋 Sugarcane Tips:\n"
                    "• Plant in February–March or October–November.\n"
                    "• Varieties: Co-86032, CoJ-64.\n"
                    "• Apply NPK (250:60:60 kg/ha) in splits.\n"
                    "• Watch for red rot, top borer, and pyrilla.")
    elif 'turmeric' in user_message:
        response = ("🟡 Turmeric Tips:\n"
                    "• Plant in April–May with onset of pre-monsoon showers.\n"
                    "• Varieties: Roma, Suroma, Rajendra Sonia.\n"
                    "• Apply FYM (25 t/ha) + NPK (60:50:120 kg/ha).\n"
                    "• Watch for rhizome rot and leaf blotch.")
    elif any(w in user_message for w in ['mung', 'moong', 'green gram']):
        response = ("🫘 Mung (Green Gram) Tips:\n"
                    "• Grows in Kharif and Zaid seasons.\n"
                    "• Varieties: Pusa Vishal, SML-668, PDM-11.\n"
                    "• Apply NPK (20:40:20 kg/ha). Seed treatment with Rhizobium.\n"
                    "• Watch for yellow mosaic virus and pod borer.")
    elif 'cotton' in user_message:
        response = ("🌿 Cotton Tips:\n"
                    "• Best season: Kharif (May–June sowing).\n"
                    "• Varieties: Bt hybrids like Bunny, RCH-2.\n"
                    "• Apply NPK (120:60:60 kg/ha) in splits.\n"
                    "• Watch for bollworm, whitefly, and leaf curl virus.")
    elif any(w in user_message for w in ['irrigation', 'water', 'drip', 'canal']):
        response = ("💧 Irrigation Guidance:\n"
                    "• Drip irrigation saves 40–50% water — ideal for sugarcane, turmeric, vegetables.\n"
                    "• Canal irrigation suits rice and wheat in flat areas.\n"
                    "• Critical stages: sowing, flowering, and grain filling.\n"
                    "• Avoid waterlogging — ensure proper field drainage.")
    elif any(w in user_message for w in ['fertilizer', 'npk', 'urea', 'manure']):
        response = ("🌱 Fertilizer Tips:\n"
                    "• Always do a soil test before applying fertilizers.\n"
                    "• Use NPK as per crop requirement.\n"
                    "• Apply FYM 2–3 weeks before sowing.\n"
                    "• Split urea application reduces nitrogen loss.\n"
                    "• Zinc (ZnSO4 @ 25 kg/ha) improves yield in deficient soils.")
    elif any(w in user_message for w in ['pest', 'disease', 'insect', 'fungus', 'blight', 'rot']):
        response = ("🐛 Pest & Disease Management:\n"
                    "• Use Integrated Pest Management (IPM).\n"
                    "• Seed treatment with fungicide/insecticide before sowing.\n"
                    "• Install pheromone traps for stem borer and bollworm.\n"
                    "• Neem-based pesticides are eco-friendly and effective.\n"
                    "• Crop rotation reduces soil-borne diseases.")
    elif any(w in user_message for w in ['soil', 'laterite', 'alluvial']):
        response = ("🌍 Soil Management Tips:\n"
                    "• Alluvial soil: Best for rice, wheat, sugarcane — coastal Odisha.\n"
                    "• Lateritic soil: Suitable for groundnut, turmeric — plateau regions.\n"
                    "• Red & Black soil: Good for cotton and pulses.\n"
                    "• Maintain soil pH between 6.0–7.5 for most crops.\n"
                    "• Get a Soil Health Card from your local agriculture office.")
    elif any(w in user_message for w in ['kharif', 'rabi', 'zaid', 'season']):
        response = ("📅 Crop Seasons in Odisha:\n"
                    "• Kharif (June–November): Rice, Maize, Groundnut, Cotton, Mung, Sugarcane.\n"
                    "• Rabi (November–March): Wheat, Mustard, Chickpea, Potato.\n"
                    "• Zaid (March–June): Mung, Watermelon, Cucumber, Vegetables.")
    elif any(w in user_message for w in ['weather', 'rain', 'forecast', 'monsoon']):
        response = ("🌦️ Weather & Farming:\n"
                    "• Check the Weather section on this platform for local forecasts.\n"
                    "• Odisha receives 1200–1500 mm annual rainfall, mostly during Kharif.\n"
                    "• Delay sowing if heavy rain is forecast — prevents seed rot.\n"
                    "• Use weather advisories from IMD Bhubaneswar for planning.")
    elif any(w in user_message for w in ['yield', 'prediction', 'predict', 'production']):
        response = ("📊 Yield Prediction:\n"
                    "• Use the 'Get Crop Advisory' feature for AI-based yield prediction.\n"
                    "• Fill in your district, crop, season, soil type, irrigation, and seed variety.\n"
                    "• The model predicts yield in quintals/hectare with confidence intervals.\n"
                    "• You'll also get 3 personalized action recommendations to improve yield.")
    elif any(w in user_message for w in ['hello', 'hi', 'hey', 'namaste', 'helo']):
        response = ("नमस्ते! 🙏 Welcome to Krishi Salahkar!\n"
                    "I can help you with:\n"
                    "• Crop advice (Rice, Wheat, Maize, Groundnut, Cotton, Sugarcane, Turmeric, Mung)\n"
                    "• Irrigation, fertilizer, pest & disease management\n"
                    "• Soil health and season planning\n"
                    "• How to use this platform\n"
                    "Just type your question!")
    elif any(w in user_message for w in ['thank', 'thanks']):
        response = "You're welcome! 🌾 Happy farming! Feel free to ask anything else."
    else:
        response = ("I can help with farming topics like:\n"
                    "• Crops: rice, wheat, maize, groundnut, cotton, sugarcane, turmeric, mung\n"
                    "• Irrigation, fertilizers, pest & disease management\n"
                    "• Soil types, crop seasons (Kharif/Rabi/Zaid)\n"
                    "• Weather advice and yield prediction\n"
                    "• How to use this platform\n"
                    "Please ask a farming-related question!")

    return JsonResponse({'response': response, 'status': 'success'})


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_instance = form.save()
            try:
                send_mail(
                    subject=f"[Contact] {contact_instance.subject}",
                    message=(f"Name: {contact_instance.name}\n"
                             f"Email: {contact_instance.email}\n\n"
                             f"{contact_instance.message}"),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.CONTACT_EMAIL],
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(request, "Thank you for your message! We'll get back to you soon.")
            return redirect('home')
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = ContactForm()
    return render(request, 'advisory/contact.html', {'form': form})


def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully! Welcome to Krishi Salahkar.")
            return redirect('home')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SignupForm()
    return render(request, 'advisory/signup.html', {'form': form})


def weather_forecast(request):
    # If lat/lon passed directly (from browser geolocation)
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    location = request.GET.get('location', '')

    try:
        if lat and lon:
            # Reverse geocode to get city name
            rev_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
            rev_data = requests.get(rev_url, timeout=8, headers={'User-Agent': 'KrishiSalahkar/1.0'}).json()
            addr = rev_data.get('address', {})
            city_name = (addr.get('city') or addr.get('town') or addr.get('village')
                         or addr.get('county') or 'Your Location')
            country = addr.get('country', '')
            lat, lon = float(lat), float(lon)
        elif location:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
            geo_data = requests.get(geo_url, timeout=10).json()
            if not geo_data.get('results'):
                return render(request, 'advisory/weather.html', {
                    'error': f"City '{location}' not found. Please check the spelling.",
                    'location': location
                })
            result = geo_data['results'][0]
            lat, lon = result['latitude'], result['longitude']
            city_name = result.get('name', location)
            country = result.get('country', '')
        else:
            # No location yet — let JS fetch it
            return render(request, 'advisory/weather.html', {'auto_locate': True})

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,apparent_temperature,visibility"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_max"
            f"&timezone=auto&forecast_days=5"
        )
        weather_data = requests.get(weather_url, timeout=10).json()
        current = weather_data.get('current', {})
        daily = weather_data.get('daily', {})

        def wmo_description(code):
            wmo = {
                0: ('Clear Sky', '☀️'), 1: ('Mainly Clear', '🌤️'), 2: ('Partly Cloudy', '⛅'),
                3: ('Overcast', '☁️'), 45: ('Foggy', '🌫️'), 48: ('Icy Fog', '🌫️'),
                51: ('Light Drizzle', '🌦️'), 53: ('Drizzle', '🌦️'), 55: ('Heavy Drizzle', '🌧️'),
                61: ('Slight Rain', '🌧️'), 63: ('Rain', '🌧️'), 65: ('Heavy Rain', '🌧️'),
                71: ('Slight Snow', '🌨️'), 73: ('Snow', '❄️'), 75: ('Heavy Snow', '❄️'),
                80: ('Rain Showers', '🌦️'), 81: ('Showers', '🌧️'), 82: ('Heavy Showers', '⛈️'),
                95: ('Thunderstorm', '⛈️'), 96: ('Thunderstorm w/ Hail', '⛈️'), 99: ('Heavy Thunderstorm', '⛈️'),
            }
            return wmo.get(code, ('Unknown', '🌡️'))

        curr_desc, curr_icon = wmo_description(current.get('weather_code', 0))
        current_weather = {
            'temp': current.get('temperature_2m', 'N/A'),
            'feels_like': current.get('apparent_temperature', 'N/A'),
            'humidity': current.get('relative_humidity_2m', 'N/A'),
            'wind_speed': current.get('wind_speed_10m', 'N/A'),
            'visibility': current.get('visibility', 'N/A'),
            'description': curr_desc,
            'icon': curr_icon,
        }

        daily_forecasts = []
        for i, date in enumerate(daily.get('time', [])):
            code = daily.get('weather_code', [0])[i] if i < len(daily.get('weather_code', [])) else 0
            desc, icon = wmo_description(code)
            daily_forecasts.append({
                'date': date,
                'temp_max': daily.get('temperature_2m_max', [None])[i],
                'temp_min': daily.get('temperature_2m_min', [None])[i],
                'description': desc,
                'icon': icon,
                'precipitation': daily.get('precipitation_sum', [0])[i],
                'wind_speed': daily.get('wind_speed_10m_max', [0])[i],
                'humidity': daily.get('relative_humidity_2m_max', [0])[i],
            })

        return render(request, 'advisory/weather.html', {
            'current_weather': current_weather,
            'daily_forecasts': daily_forecasts,
            'location': f"{city_name}, {country}",
        })

    except Exception as e:
        return render(request, 'advisory/weather.html', {
            'error': f"Error fetching weather data: {str(e)}",
            'location': location
        })
