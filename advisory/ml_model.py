import random
import os
from django.conf import settings
import statistics
import pickle
import math

import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

class YieldPredictor:
    def __init__(self):
        self.data = None
        self.is_loaded = False
        self.model = None
        self.rainfall_means = None
        self.load_model()
        if self.model is None:
            self.train_model()
        
    def load_data(self):
        """Load and preprocess the combined_tables data"""
        if self.is_loaded and self.data:
            return self.data
            
        try:
            data_path = os.path.join(settings.BASE_DIR, 'combined_tables.txt')
            data = []
            with open(data_path, 'r') as f:
                lines = f.readlines()
                headers = lines[0].strip().split('\t')
                for line in lines[1:]:
                    values = line.strip().split('\t')
                    if len(values) == len(headers):
                        row = dict(zip(headers, values))
                        # Convert numeric fields
                        try:
                            row['yield'] = float(row['yield'])
                            row['field_area'] = float(row['field_area'])
                            row['rainfall'] = float(row['rainfall'])
                            row['year'] = int(row['year'])
                        except:
                            continue
                        data.append(row)
            self.data = data
            self.is_loaded = True
            return data
        except Exception as e:
            print(f"Error loading data: {e}")
            return []

    def load_model(self):
        """Load the trained model from pickle file"""
        model_path = os.path.join(settings.BASE_DIR, 'advisory/models/farm_model.pkl')
        try:
            artifact = joblib.load(model_path)
            if isinstance(artifact, dict) and artifact.get('artifact_version') == 1:
                self.model = artifact.get('model')
                self.rainfall_means = artifact.get('rainfall_means')
            else:
                self.model = artifact
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
            self.rainfall_means = None

    def _rainfall_mean_key(self, district, crop, season):
        return f"{district}|{crop}|{season}"

    def _build_rainfall_means(self, data):
        by_key = {}
        for row in data:
            key = self._rainfall_mean_key(row['district'], row['crop'], row['season'])
            by_key.setdefault(key, []).append(float(row['rainfall']))
        means = {key: float(statistics.mean(vals)) for key, vals in by_key.items() if vals}
        if means:
            means['_global'] = float(statistics.mean(means.values()))
        else:
            means['_global'] = 0.0
        return means

    def train_model(self, n_estimators=250, random_state=42):
        data = self.load_data()
        if not data:
            self.model = None
            return None

        self.rainfall_means = self._build_rainfall_means(data)

        X = []
        y = []
        for row in data:
            base_features = self._encode_features(
                crop=row['crop'],
                district=row['district'],
                season=row['season'],
                irrigation=row['irrigation'],
                seed_variety=row['seed_variety'],
                soil_type=row['soil_type'],
                soil_health_card=0,
                pest_presence=0,
                year=int(row['year']),
                rainfall=float(row['rainfall']),
            )
            base_yield = float(row['yield'])

            for soil_health_card in (0, 1):
                for pest_presence in (0, 1):
                    features = list(base_features)
                    features[6] = soil_health_card
                    features[7] = pest_presence

                    adjusted_yield = base_yield
                    if soil_health_card:
                        adjusted_yield *= 1.05
                    if pest_presence:
                        adjusted_yield *= 0.92

                    X.append(features)
                    y.append(adjusted_yield)

        model = RandomForestRegressor(
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
        model.fit(X, y)

        model_path = os.path.join(settings.BASE_DIR, 'advisory/models/farm_model.pkl')
        joblib.dump(
            {
                'artifact_version': 1,
                'model': model,
                'rainfall_means': self.rainfall_means,
            },
            model_path,
        )
        self.model = model
        return model

    def _encode_features(
        self,
        *,
        crop,
        district,
        season,
        irrigation,
        seed_variety,
        soil_type,
        soil_health_card,
        pest_presence,
        year,
        rainfall,
    ):
        crop_map = {'rice': 1, 'maize': 2, 'wheat': 3, 'groundnut': 4, 'mung': 5, 'cotton': 6, 'sugarcane': 7, 'turmeric': 8}
        district_map = {
            'angul': 1, 'balangir': 2, 'balasore': 3, 'bargarh': 4, 'bhadrak': 5, 'boudh': 6,
            'cuttack': 7, 'deogarh': 8, 'dhenkanal': 9, 'gajapati': 10, 'ganjam': 11, 'jagatsinghpur': 12,
            'jajpur': 13, 'jharsuguda': 14, 'kalahandi': 15, 'kandhamal': 16, 'kendrapara': 17, 'keonjhar': 18,
            'khordha': 19, 'koraput': 20, 'malkangiri': 21, 'mayurbhanj': 22, 'nabarangpur': 23, 'nayagarh': 24,
            'nuapada': 25, 'puri': 26, 'rayagada': 27, 'sambalpur': 28, 'sonepur': 29, 'sundargarh': 30
        }
        season_map = {'kharif': 1, 'rabi': 2, 'zaid': 3}
        irrigation_map = {'none': 0, 'drip': 1, 'tubewell': 2, 'canal': 3, 'lift': 4}
        seed_map = {'local': 0, 'hyv': 1, 'hybrid': 2}
        soil_map = {'alluvial': 1, 'red_black': 2, 'lateritic': 3, 'saline': 4}

        return [
            crop_map.get(crop, 0),
            district_map.get(district, 0),
            season_map.get(season, 0),
            irrigation_map.get(irrigation, 0),
            seed_map.get(seed_variety, 0),
            soil_map.get(soil_type, 0),
            1 if soil_health_card else 0,
            1 if pest_presence else 0,
            int(year),
            float(rainfall),
        ]

    def _estimate_rainfall(self, farm_input):
        if not self.rainfall_means:
            data = self.load_data()
            self.rainfall_means = self._build_rainfall_means(data) if data else {'_global': 0.0}

        key = self._rainfall_mean_key(farm_input.district, farm_input.crop, farm_input.season)
        return float(self.rainfall_means.get(key, self.rainfall_means.get('_global', 0.0)))

    def prepare_features(self, farm_input):
        """Prepare numerical features for the model"""
        year = getattr(getattr(farm_input, 'sowing_date', None), 'year', None) or 2020
        rainfall = self._estimate_rainfall(farm_input)
        return self._encode_features(
            crop=farm_input.crop,
            district=farm_input.district,
            season=farm_input.season,
            irrigation=farm_input.irrigation,
            seed_variety=farm_input.seed_variety,
            soil_type=farm_input.soil_type,
            soil_health_card=bool(farm_input.soil_health_card),
            pest_presence=bool(farm_input.pest_presence),
            year=year,
            rainfall=rainfall,
        )

    def predict_yield(self, farm_input):
        """Predict yield based on farm input using the trained model or rule-based fallback"""
        if self.model:
            try:
                features = self.prepare_features(farm_input)
                prediction = float(self.model.predict([features])[0])
                # Ensure positive prediction
                prediction = max(prediction, 100.0)
                confidence = None

                if hasattr(self.model, 'estimators_') and self.model.estimators_:
                    tree_preds = np.array([float(est.predict([features])[0]) for est in self.model.estimators_], dtype=float)
                    lower = float(np.percentile(tree_preds, 2.5))
                    upper = float(np.percentile(tree_preds, 97.5))
                    half_width = max((upper - lower) / 2.0, prediction * 0.05)
                    confidence = f"±{half_width:.0f}"

                if confidence is None:
                    confidence = f"±{(prediction * 0.12):.0f}"
                return prediction, confidence
            except Exception as e:
                print(f"Model prediction failed: {e}, falling back to rule-based")

        # Fallback to rule-based prediction
        data = self.load_data()

        # Base yields for different crops (kg/ha)
        base_yields = {
            'rice': 3200, 'maize': 4200, 'wheat': 3500, 'groundnut': 2200,
            'mung': 1100, 'cotton': 1600, 'sugarcane': 75000, 'turmeric': 5200
        }

        base_yield = base_yields.get(farm_input.crop, 2500)

        # Apply adjustments based on farming practices
        multiplier = 1.0

        # Irrigation adjustment
        if farm_input.irrigation == 'drip':
            multiplier *= 1.25
        elif farm_input.irrigation in ['tubewell', 'canal']:
            multiplier *= 1.15
        elif farm_input.irrigation == 'lift':
            multiplier *= 1.08
        elif farm_input.irrigation == 'none':
            multiplier *= 0.85

        # Seed variety adjustment
        if farm_input.seed_variety == 'hybrid':
            multiplier *= 1.20
        elif farm_input.seed_variety == 'hyv':
            multiplier *= 1.10
        elif farm_input.seed_variety == 'local':
            multiplier *= 0.95

        # Soil type adjustment
        if farm_input.soil_type == 'alluvial':
            multiplier *= 1.05
        elif farm_input.soil_type == 'red_black':
            multiplier *= 1.02
        elif farm_input.soil_type == 'lateritic':
            multiplier *= 0.98
        elif farm_input.soil_type == 'saline':
            multiplier *= 0.85

        # Season adjustment
        if farm_input.season == 'kharif':
            multiplier *= 1.05  # Monsoon advantage
        elif farm_input.season == 'rabi':
            multiplier *= 1.10  # Better conditions
        elif farm_input.season == 'zaid':
            multiplier *= 0.95  # Summer challenges

        # Soil health card bonus
        if farm_input.soil_health_card:
            multiplier *= 1.05

        # Pest presence penalty
        if farm_input.pest_presence:
            multiplier *= 0.92

        # Calculate final prediction
        prediction = base_yield * multiplier

        # Add some randomness for realism
        variation = random.uniform(0.95, 1.05)
        prediction *= variation

        # Calculate confidence interval
        confidence_range = prediction * 0.12
        confidence = f"±{confidence_range:.0f}"

        return max(prediction, 100), confidence
    
    def generate_recommendations(self, farm_input, predicted_yield):
        """Generate actionable recommendations"""
        # Calculate potential gain based on best practices
        potential_gain = self._calculate_potential_gain(farm_input)
        
        recommendations = {
            'action_1': self._get_priority_action_1(farm_input),
            'action_2': self._get_priority_action_2(farm_input),
            'action_3': self._get_priority_action_3(farm_input),
            'reasoning': f"AI analysis of {farm_input.get_crop_display()} in {farm_input.get_district_display()} during {farm_input.get_season_display()} season using {farm_input.get_irrigation_display()} irrigation on {farm_input.get_soil_type_display()} soil.",
            'estimated_gain': potential_gain
        }
        
        return recommendations
    
    def _calculate_potential_gain(self, farm_input):
        """Calculate potential yield gain from improved practices"""
        gain = 0
        
        # Irrigation improvement potential
        if farm_input.irrigation == 'none':
            gain += 20
        elif farm_input.irrigation in ['lift', 'canal']:
            gain += 8
        elif farm_input.irrigation == 'tubewell':
            gain += 5
        
        # Seed variety improvement
        if farm_input.seed_variety == 'local':
            gain += 15
        elif farm_input.seed_variety == 'hyv':
            gain += 8
        
        # Soil health improvement
        if not farm_input.soil_health_card:
            gain += 10
        
        # Pest management
        if farm_input.pest_presence:
            gain += 12
        
        # Cap the gain between 5-25%
        return min(max(gain, 5), 25)
    
    def _get_priority_action_1(self, farm_input):
        """Get highest priority immediate action"""
        if farm_input.irrigation == 'none' and farm_input.crop in ['rice', 'sugarcane']:
            return "URGENT: Install irrigation system immediately - these crops need consistent water supply for survival and yield"
        elif farm_input.pest_presence:
            return "IMMEDIATE: Apply integrated pest management - spray neem oil and set up pheromone traps within 2 days"
        elif not farm_input.soil_health_card:
            return "HIGH PRIORITY: Get soil health card from nearest agriculture office to optimize fertilizer application"
        elif farm_input.irrigation == 'none':
            return "CRITICAL: Install drip irrigation system to increase water efficiency and boost yield by 20-25%"
        else:
            return "OPTIMIZE: Monitor soil moisture daily and apply irrigation at critical crop growth stages"
    
    def _get_priority_action_2(self, farm_input):
        """Get second priority action"""
        if farm_input.soil_health_card:
            crop_fertilizer = {
                'rice': "Apply 120:60:40 NPK kg/ha in 3 splits - 50% basal, 25% tillering, 25% panicle stage",
                'maize': "Apply 150:75:40 NPK kg/ha - 1/3 at sowing, 1/3 at knee-high, 1/3 at tasseling",
                'wheat': "Apply 120:60:40 NPK kg/ha in 3 splits based on soil test recommendations",
                'groundnut': "Apply 20:60:40 NPK kg/ha - groundnut fixes nitrogen naturally",
                'cotton': "Apply 150:75:75 NPK kg/ha in splits with micronutrients",
                'sugarcane': "Apply 300:150:150 NPK kg/ha in 4 splits throughout growing season"
            }
            return crop_fertilizer.get(farm_input.crop, "Apply balanced NPK fertilizer as per soil test in 2-3 splits")
        else:
            return "Apply balanced NPK fertilizer (consult agriculture officer) and get soil testing done immediately"
    
    def _get_priority_action_3(self, farm_input):
        """Get third priority action"""
        if farm_input.seed_variety == 'local':
            return f"UPGRADE: Switch to hybrid or HYV {farm_input.crop} varieties for 15-20% higher yield next season"
        elif farm_input.season == 'kharif':
            return "WEATHER PREP: Monitor weather forecasts and provide drainage during heavy rains to prevent waterlogging"
        elif farm_input.season == 'rabi':
            return "TIMING: Ensure timely sowing and harvest to avoid heat stress and maximize market prices"
        else:
            return "FIELD MANAGEMENT: Maintain proper plant spacing, weed control, and regular field monitoring for diseases"

    def get_district_average(self, district, crop, season):
        """Get average yield for district, crop, season combination"""
        data = self.load_data()
        if data:
            yields = [
                float(row['yield'])
                for row in data
                if row['district'] == district and row['crop'] == crop and row['season'] == season
            ]
            if yields:
                return float(statistics.mean(yields))

        district_crop_avg = {
            'rice': 2800, 'maize': 3500, 'wheat': 3000, 'groundnut': 1900,
            'mung': 950, 'cotton': 1400, 'sugarcane': 68000, 'turmeric': 4500
        }
        base_avg = float(district_crop_avg.get(crop, 2200))
        if season == 'kharif':
            base_avg *= 0.95
        elif season == 'rabi':
            base_avg *= 1.05
        elif season == 'zaid':
            base_avg *= 0.90
        return base_avg

# Global instance
yield_predictor = YieldPredictor()
