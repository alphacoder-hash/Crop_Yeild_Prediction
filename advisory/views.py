from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.conf import settings
from .forms import FarmInputForm, SignupForm, ContactForm
from .models import FarmInput, Recommendation, Contact
from .ml_model import yield_predictor
import traceback
import requests
# import openai
import os

def home(request):
    """Home page view"""
    return render(request, 'advisory/home.html')

@login_required(login_url='/login/')
def farm_input(request):
    """Farm input form view"""
    if request.method == 'POST':
        form = FarmInputForm(request.POST)
        if form.is_valid():
            try:
                farm_input_obj = form.save()
                
                # Generate ML prediction
                predicted_yield, confidence = yield_predictor.predict_yield(farm_input_obj)
                recommendations = yield_predictor.generate_recommendations(farm_input_obj, predicted_yield)
                
                # Ensure all required fields are present
                if not all(key in recommendations for key in ['action_1', 'action_2', 'action_3', 'reasoning', 'estimated_gain']):
                    raise ValueError("Incomplete recommendation data generated")
                
                # Save recommendation
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
                print(f"Error in farm_input view: {e}")  # For debugging
        else:
            messages.error(request, "Please correct the errors in the form.")
                
    else:
        form = FarmInputForm()
    
    return render(request, 'advisory/farm_input.html', {'form': form})

@login_required(login_url='/login/')
def recommendation(request, recommendation_id):
    """Display recommendation results"""
    try:
        recommendation = Recommendation.objects.get(id=recommendation_id)
        
        # Get district average for comparison
        farm_input = recommendation.farm_input
        district_avg = yield_predictor.get_district_average(farm_input.district, farm_input.crop, farm_input.season)
        
        # Calculate total production
        total_production = recommendation.predicted_yield * farm_input.field_area
        
        # Calculate improvement percentage
        improvement = 0
        if district_avg > 0:
            improvement = ((recommendation.predicted_yield - district_avg) / district_avg) * 100
        
        context = {
            'recommendation': recommendation,
            'total_production': total_production,
            'yield_comparison': {
                'predicted': recommendation.predicted_yield,
                'district_avg': district_avg,
                'improvement': improvement
            }
        }
        
        return render(request, 'advisory/recommendation.html', context)
    except Recommendation.DoesNotExist:
        messages.error(request, "Recommendation not found. Please try generating a new recommendation.")
        return redirect('farm_input')
    except Exception as e:
        messages.error(request, f"Error loading recommendation: {str(e)}")
        return redirect('farm_input')

def about(request):
    """About page view"""
    return render(request, 'advisory/about.html')

# from django.conf import settings
# from twilio.rest import Client
# import logging

def contact(request):
    """Contact form view"""
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_instance = form.save()
            # Send SMS notification via Twilio - Temporarily disabled
            # try:
            #     client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            #     message_body = (
            #         f"New contact form submission:\n"
            #         f"Name: {contact_instance.name}\n"
            #         f"Email: {contact_instance.email}\n"
            #         f"Subject: {contact_instance.subject}\n"
            #         f"Message: {contact_instance.message}"
            #     )
            #     client.messages.create(
            #         body=message_body,
            #         from_=settings.TWILIO_PHONE_NUMBER,
            #         to=settings.DEVELOPER_MOBILE_NUMBER
            #     )
            # except Exception as e:
            #     logging.error(f"Failed to send SMS notification: {e}")
            messages.success(request, "Thank you for your message! We'll get back to you soon.")
            return redirect('home')
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = ContactForm()
    return render(request, 'advisory/contact.html', {'form': form})

def signup(request):
    """User signup view"""
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
    """Weather forecast view"""
    location = request.GET.get('location', 'Bhubaneswar')  # Default to Bhubaneswar
    api_key = settings.WEATHER_API_KEY
    base_url = settings.WEATHER_API_BASE_URL

    if api_key == 'your-weather-api-key-here':
        messages.error(request, "Weather API key not configured. Please set WEATHER_API_KEY in settings.")
        return render(request, 'advisory/weather.html', {'error': 'API key not configured'})

    try:
        # Fetch current weather
        current_url = f"{base_url}/weather?q={location}&appid={api_key}&units=metric"
        current_response = requests.get(current_url)
        current_data = current_response.json()

        # Fetch 5-day forecast
        forecast_url = f"{base_url}/forecast?q={location}&appid={api_key}&units=metric"
        forecast_response = requests.get(forecast_url)
        forecast_data = forecast_response.json()

        if current_response.status_code != 200 or forecast_response.status_code != 200:
            error_msg = f"API Error - Current: {current_response.status_code} ({current_response.text}), Forecast: {forecast_response.status_code} ({forecast_response.text})"
            messages.error(request, error_msg)
            return render(request, 'advisory/weather.html', {'error': error_msg})

        # Process forecast data (group by day)
        daily_forecasts = {}
        for item in forecast_data['list']:
            date = item['dt_txt'].split(' ')[0]
            if date not in daily_forecasts:
                daily_forecasts[date] = {
                    'temp_min': item['main']['temp_min'],
                    'temp_max': item['main']['temp_max'],
                    'humidity': item['main']['humidity'],
                    'description': item['weather'][0]['description'],
                    'icon': item['weather'][0]['icon'],
                    'wind_speed': item['wind']['speed'],
                    'date': date
                }
            else:
                daily_forecasts[date]['temp_min'] = min(daily_forecasts[date]['temp_min'], item['main']['temp_min'])
                daily_forecasts[date]['temp_max'] = max(daily_forecasts[date]['temp_max'], item['main']['temp_max'])

        context = {
            'current_weather': current_data,
            'daily_forecasts': list(daily_forecasts.values())[:5],  # Next 5 days
            'location': location
        }
        return render(request, 'advisory/weather.html', context)

    except Exception as e:
        messages.error(request, f"Error fetching weather data: {str(e)}")
        return render(request, 'advisory/weather.html', {'error': str(e)})

# def chatbot(request):
#     """Chatbot API endpoint"""
#     if request.method == 'POST':
#         try:
#             user_message = request.POST.get('message', '').strip()

#             if not user_message:
#                 return JsonResponse({'error': 'Message is required'}, status=400)

#             # Set OpenAI API key
#             openai.api_key = os.getenv('OPENAI_API_KEY')

#             # Create farming-specific context
#             system_prompt = """You are Krishi Salahkar, an AI agricultural assistant specializing in farming advice for Odisha, India.
#             You help farmers with:
#             - Crop selection and planning
#             - Soil management and fertilization
#             - Pest and disease control
#             - Irrigation techniques
#             - Weather-based farming decisions
#             - Sustainable farming practices
#             - Odisha-specific agricultural knowledge

#             Always provide practical, actionable advice based on scientific farming principles.
#             Keep responses concise but informative.
#             If you don't know something specific to Odisha, acknowledge this and provide general best practices."""

#             # Create chat completion using new OpenAI API
#             client = openai.OpenAI(api_key=openai.api_key)
#             response = client.chat.completions.create(
#                 model="gpt-3.5-turbo",
#                 messages=[
#                     {"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_message}
#                 ],
#                 max_tokens=500,
#                 temperature=0.7
#             )

#             bot_response = response.choices[0].message.content.strip()
#             print(f"Bot response: {bot_response}")  # Debug log

#             return JsonResponse({
#                 'response': bot_response,
#                 'status': 'success'
#             })

#         except Exception as e:
#             print(f"Chatbot error: {str(e)}")
#             import traceback
#             traceback.print_exc()  # Print full traceback

#             # Fallback responses for common farming questions
#             fallback_responses = {
#                 'rice': 'For rice cultivation in Odisha, use varieties like Naveen or Swarna. Plant during Kharif season (June-July) with proper irrigation and apply NPK fertilizers.',
#                 'wheat': 'Wheat grows well in Odisha during Rabi season. Use varieties like HD-2967. Ensure proper irrigation and apply fertilizers at recommended doses.',
#             }

#             user_lower = user_message.lower()
#             fallback_response = fallback_responses['default']

#             for key, response in fallback_responses.items():
#                 if key in user_lower and key != 'default':
#                     fallback_response = response
#                     break

#             return JsonResponse({
#                 'response': fallback_response,
#                 'status': 'success'
#             })

#     return JsonResponse({'error': 'Method not allowed'}, status=405)
