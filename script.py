import pandas as pd
import numpy as np

# Load original sourcing data
df = pd.read_csv("NJTransit_FIFA2026_Synthetic_Data(1).xlsx - Sourcing Data.csv")

# Get unique vendors from the dataset
vendors = df['Location Name'].unique()

# Set a seed for reproducibility so the numbers stay the same every time it is run
np.random.seed(42)

social_data = []

# Loop through each vendor and assign scores based on logical profiles
for vendor in vendors:
    
    # Logic Profile 1: Local / Regional Suppliers
    # Higher community impact, solid labor rights, standard transparency
    if "Local" in vendor or "NJ" in vendor:
        community_score = np.random.randint(80, 98) 
        labor_score = np.random.randint(75, 95)
        safety_trir = round(np.random.uniform(0.5, 2.5), 2) 
        transparency = np.random.randint(70, 90)
        
    # Logic Profile 2: Global / International Suppliers
    # Lower local community impact, very high labor/transparency standards (EU/Corporate compliance)
    elif "Global" in vendor:
        community_score = np.random.randint(50, 70) 
        labor_score = np.random.randint(85, 98) 
        safety_trir = round(np.random.uniform(0.2, 1.5), 2)
        transparency = np.random.randint(80, 95)
        
    # Logic Profile 3: Standard Hubs / Depots / Default
    # Baseline control group scores, slightly higher safety incident rate (TRIR) due to high volume
    else:
        community_score = np.random.randint(60, 85)
        labor_score = np.random.randint(70, 90)
        safety_trir = round(np.random.uniform(1.0, 3.0), 2)
        transparency = np.random.randint(60, 85)
        
    # Append the generated scores to our list
    social_data.append({
        'Location Name': vendor,
        'Social_LaborRights_Score (1-100)': labor_score,
        'Social_Safety_TRIR (Lower=Better)': safety_trir,
        'Social_CommunityDiversity_Score (1-100)': community_score,
        'Social_Transparency_Index (1-100)': transparency
    })

# Convert the generated scores into a DataFrame
social_df = pd.DataFrame(social_data)

# Merge the new social data back into the original dataset based on 'Location Name'
df_enriched = df.merge(social_df, on='Location Name', how='left')

# Save to a new CSV file for AnyLogistix
output_file = 'NJTransit_Sourcing_with_Social_Pillar.csv'
df_enriched.to_csv(output_file, index=False)

print(f"Successfully generated social metrics and saved to: {output_file}")