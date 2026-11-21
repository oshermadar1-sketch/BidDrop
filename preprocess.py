import pandas as pd
import numpy as np

# 1. Load the raw Zomato dataset
df = pd.read_csv('Zomato Dataset.csv')

# 2. Handle Missing Values
# Impute missing Age and Ratings with the median
df['Delivery_person_Age'] = df['Delivery_person_Age'].fillna(df['Delivery_person_Age'].median())
df['Delivery_person_Ratings'] = df['Delivery_person_Ratings'].fillna(df['Delivery_person_Ratings'].median())
# Impute missing Weather and Traffic conditions with the mode
df['Weather_conditions'] = df['Weather_conditions'].fillna(df['Weather_conditions'].mode()[0])
df['Road_traffic_density'] = df['Road_traffic_density'].fillna(df['Road_traffic_density'].mode()[0])

# 3. Calculate Haversine Distance (in kilometers)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth's radius in kilometers
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

df['Distance_km'] = haversine(df['Restaurant_latitude'], df['Restaurant_longitude'], 
                              df['Delivery_location_latitude'], df['Delivery_location_longitude'])

# 3b. Road distance of the same route, from OpenStreetMap routing (scripts/road_distances.py).
# Kept next to the straight-line distance so the model can be trained on either one.
_road = pd.read_csv('Zomato_Road_Distances.csv')
_key = ['Restaurant_latitude', 'Restaurant_longitude',
        'Delivery_location_latitude', 'Delivery_location_longitude']
_join = df[_key].astype(float).abs().round(5)
_join.columns = ['_rlat', '_rlon', '_dlat', '_dlon']
_road.columns = ['_rlat', '_rlon', '_dlat', '_dlon', 'Road_Distance_km', 'Road_Duration_min', 'Road_Source']
df = (pd.concat([df, _join], axis=1)
        .merge(_road, on=['_rlat', '_rlon', '_dlat', '_dlon'], how='left')
        .drop(columns=['_rlat', '_rlon', '_dlat', '_dlon']))
# Routes the server could not answer (or rows with missing coordinates): scale the
# straight line by the typical road/air ratio of the routes it did answer.
_ratio = (df.loc[df['Road_Source'] == 'osrm', 'Road_Distance_km']
          / df.loc[df['Road_Source'] == 'osrm', 'Distance_km']).median()
_missing = df['Road_Distance_km'].isna()
df.loc[_missing, 'Road_Distance_km'] = (df.loc[_missing, 'Distance_km'] * _ratio).round(3)
df.loc[_missing, 'Road_Duration_min'] = (60 * df.loc[_missing, 'Road_Distance_km'] / 30.0).round(1)
df.loc[_missing, 'Road_Source'] = 'air'
print(f"Road distances: ratio road/air = {_ratio:.2f}, {int((~_missing).sum())} routed, {int(_missing.sum())} scaled from air")

# 4. Process Time Features
# Drop rows missing crucial order or pickup times
df = df.dropna(subset=['Time_Orderd', 'Time_Order_picked']).copy()
df['Time_Orderd'] = df['Time_Orderd'].astype(str).str.strip()
df['Time_Order_picked'] = df['Time_Order_picked'].astype(str).str.strip()

# Convert time strings to datetime for calculation
t_order = pd.to_datetime(df['Time_Orderd'], format='%H:%M', errors='coerce')
t_pickup = pd.to_datetime(df['Time_Order_picked'], format='%H:%M', errors='coerce')

# Calculate restaurant delay and handle midnight crossing (adding 1440 mins)
delay_min = (t_pickup - t_order).dt.total_seconds() / 60
df['Restaurant_delay_min'] = delay_min.apply(lambda x: x + 1440 if pd.notnull(x) and x < 0 else x)

# Calculate net delivery time for the courier
df['Net_Delivery_Time_min'] = df['Time_taken (min)'] - df['Restaurant_delay_min']

# Format Order_Date to datetime before we drop other date/time columns
df['Order_Date'] = pd.to_datetime(df['Order_Date'], format='%d/%m/%Y', errors='coerce')

# 5. Filter Outliers (Domain Knowledge + Statistical)
# Age 16-65 (Including 16 for electric scooters in our market), Ratings 1-5, Distance 0.1-50km
df = df[(df['Delivery_person_Age'] >= 16) & (df['Delivery_person_Age'] <= 65)]
df = df[(df['Delivery_person_Ratings'] >= 1.0) & (df['Delivery_person_Ratings'] <= 5.0)]
df = df[(df['Distance_km'] >= 0.1) & (df['Distance_km'] <= 50.0)]
# Valid net delivery times and max total time of 3 hours
df = df[df['Net_Delivery_Time_min'] > 0]
df = df[df['Time_taken (min)'] <= 180]

# IQR filtering to remove extreme delivery times
Q1 = df['Time_taken (min)'].quantile(0.25)
Q3 = df['Time_taken (min)'].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR
df = df[(df['Time_taken (min)'] >= lower_bound) & (df['Time_taken (min)'] <= upper_bound)]

# 6. Drop Irrelevant Columns
# Remove IDs (noise), raw GPS coords, and raw time strings
columns_to_drop = [
    'ID', 
    'Delivery_person_ID', 
    'Restaurant_latitude', 
    'Restaurant_longitude', 
    'Delivery_location_latitude', 
    'Delivery_location_longitude', 
    'Time_Orderd', 
    'Time_Order_picked'
]
df = df.drop(columns=columns_to_drop)

# 7. Save Final Preprocessed Dataset
df.to_csv('Zomato_Final_Preprocessed.csv', index=False)
print("Data preprocessing complete! Final shape:", df.shape)