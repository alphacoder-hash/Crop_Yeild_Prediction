from django.contrib import admin
from .models import FarmInput, Recommendation

@admin.register(FarmInput)
class FarmInputAdmin(admin.ModelAdmin):
    list_display = ['district', 'crop', 'season', 'field_area', 'irrigation', 'created_at']
    list_filter = ['district', 'crop', 'season', 'irrigation', 'soil_type']
    search_fields = ['district', 'crop']
    date_hierarchy = 'created_at'

@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ['farm_input', 'predicted_yield', 'estimated_gain', 'created_at']
    list_filter = ['farm_input__district', 'farm_input__crop', 'created_at']
    search_fields = ['farm_input__district', 'farm_input__crop']
    date_hierarchy = 'created_at'