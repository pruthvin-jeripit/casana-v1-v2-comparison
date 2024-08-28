import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
import pandas as pd
import re
import json
from io import StringIO

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Load credentials from Streamlit secrets
google_credentials_dict = st.secrets["google_credentials"]
google_credentials = json.dumps(google_credentials_dict)
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_credentials), scope)
client = gspread.authorize(creds)
sheet = client.open("Casana-V1-V2-Phy").sheet1

# Load the CSV file (which should also be stored in Streamlit secrets)
csv_data = st.secrets["my_csv_data"]["csv_content"]
visit1_df = pd.read_csv(StringIO(csv_data))

# Streamlit UI and other logic remains the same...
st.title("Measurement Comparison/Re-measure App")
option = st.radio("Select Option:", ["Comparison", "Re-measure"])

# Record ID Input with Validation
rec_id = st.text_input("Enter REDCap ID:").strip()
valid_rec_id = re.match(r'^CBP-\d{4}(-B)?$', rec_id)
if rec_id and not valid_rec_id:
    st.warning("REDCap ID must follow the pattern 'CBP-' followed by 4 integers, optionally followed by '-B' (e.g., 'CBP-0023' or 'CBP-0251-B').")
    st.stop()

# Remove '-B' for comparison, but store with '-B' in Google Sheets
record_id = rec_id.replace("-B", "") if "-B" in rec_id else rec_id

# User Inputs
if option == "Comparison":
    coordinator = st.selectbox("Coordinator", ["Select a coordinator", "Alyssa", "Cyriah", "Eddie", "Gianna", "Sam"])
    if coordinator == "Select a coordinator":
        st.warning("Please select a coordinator.")
        st.stop()
else:
    remeasured_by = st.selectbox("Re-measured by", ["Select a person", "Dr. T", "Mitch"])
    if remeasured_by == "Select a person":
        st.warning("Please select who re-measured.")
        st.stop()

# Measurements
sternal_notch = st.text_input("Sternal notch (cm)").strip()
height = st.text_input("Height (in)").strip()
weight = st.text_input("Weight (lbs)").strip()
waist_circ = st.text_input("Waist Circumference (cm)").strip()
arm_circ = st.text_input("Arm Circumference (cm)").strip()

# Convert inputs to floats if provided and valid
try:
    sternal_notch = float(sternal_notch) if sternal_notch else None
    height = float(height) if height else None
    weight = float(weight) if weight else None
    waist_circ = float(waist_circ) if waist_circ else None
    arm_circ = float(arm_circ) if arm_circ else None
except ValueError:
    st.error("Please enter valid float values for measurements.")
    st.stop()

# Ensure both height and weight are entered if either is provided
if (height and not weight) or (weight and not height):
    st.error("Please enter both height and weight to calculate BMI.")
    st.stop()

# Calculate BMI if height and weight are provided
bmi = None
if height and weight:
    bmi = (weight / (height ** 2)) * 703  # BMI calculation with height in inches and weight in lbs

# Mapping of measure names to their corresponding variables
measure_to_variable = {
    'Sternal Notch': sternal_notch,
    'Height': height,
    'Weight': weight,
    'Waist Circumference': waist_circ,
    'Arm Circumference': arm_circ
}

# On submission
if st.button("Submit"):
    if option == "Comparison":
        # Retrieve corresponding Visit 1 data
        visit1_data = visit1_df[visit1_df['record_id'] == record_id]

        if visit1_data.empty:
            st.error("No matching Record ID found in Visit 1 data.")
        else:
            # Mapping of measure names to Visit 1 column names
            measure_to_column = {
                'Sternal Notch': 'phy_sternal', 
                'Height': 'phy_height_inch',
                'Weight': 'phy_weight_lb',
                'Waist Circumference': 'phy_waist_circ',
                'Arm Circumference': 'phy_arm'
            }

            # Calculate differences and classify
            categories = {}
            results = []
            for measure, visit_2_measure in measure_to_variable.items():
                if visit_2_measure is not None:
                    visit_1_measure = visit1_data[measure_to_column[measure]].values[0]
                    
                    if measure == "Weight":
                        diff = abs((visit_2_measure - visit_1_measure) / visit_1_measure) * 100  # % difference for weight
                    else:
                        diff = abs(visit_2_measure - visit_1_measure)
                    
                    if measure == 'Sternal Notch' and diff > 2:
                        categories[measure] = 'Red'
                    elif measure == 'Sternal Notch' and 1.5 <= diff <= 2:
                        categories[measure] = 'Yellow'
                    elif measure == 'Height' and diff > 2:
                        categories[measure] = 'Red'
                    elif measure == 'Height' and 1 <= diff <= 2:
                        categories[measure] = 'Yellow'
                    elif measure == 'Weight' and diff > 4:
                        categories[measure] = 'Red'
                    elif measure == 'Weight' and 3 <= diff <= 4:
                        categories[measure] = 'Yellow'
                    elif measure == 'Waist Circumference' and diff > 6.5:
                        categories[measure] = 'Red'
                    elif measure == 'Waist Circumference' and 4 <= diff <= 6.5:
                        categories[measure] = 'Yellow'
                    elif measure == 'Arm Circumference':
                        # Categorize Visit 1 and Visit 2 measures
                        if visit_1_measure <= 24:
                            visit_1_category = 'Small'
                        elif 24 < visit_1_measure <= 33:
                            visit_1_category = 'Medium'
                        else:
                            visit_1_category = 'Large'

                        if visit_2_measure <= 24:
                            visit_2_category = 'Small'
                        elif 24 < visit_2_measure <= 33:
                            visit_2_category = 'Medium'
                        else:
                            visit_2_category = 'Large'

                        # Compare categories
                        if visit_1_category != visit_2_category:
                            categories[measure] = 'Red'
                    
                    # Append the results for displaying
                    results.append([measure, categories.get(measure, 'Green'), visit_1_measure, visit_2_measure])

            # Convert the categories dictionary into a string that can be stored in a cell
            categories_str = ", ".join([f"{k}: {v}" for k, v in categories.items()])

            # Store in Google Sheets
            data = [rec_id, option, coordinator, sternal_notch, height, weight, bmi, waist_circ, arm_circ, categories_str]
            sheet.append_row(data)

            # Display the results table in the app
            st.write("### Measurements Comparison Results")
            results_df = pd.DataFrame(results, columns=["Measure", "Category", "Visit 1 Measure", "Visit 2 Measure"])
            st.table(results_df)

            # Load email credentials from Streamlit secrets
            sender_email = st.secrets["email_credentials"]["email"]
            sender_password = st.secrets["email_credentials"]["password"]

            # Send email if Red or Yellow
            if any(cat in ['Red', 'Yellow'] for cat in categories.values()):
                # Create a table for the flagged measurements
                flagged_measurements_table = "<table border='1' cellpadding='5' cellspacing='0'><tr><th>Serial #</th><th>Measure</th><th>Category</th><th>Visit 1 Measure</th><th>Visit 2 Measure</th></tr>"
                
                serial_num = 1
                for measure, category in categories.items():
                    visit_1_measure = visit1_data[measure_to_column[measure]].values[0]
                    visit_2_measure = measure_to_variable[measure]
                    flagged_measurements_table += f"<tr><td>{serial_num}</td><td>{measure}</td><td>{category}</td><td>{visit_1_measure}</td><td>{visit_2_measure}</td></tr>"
                    serial_num += 1
                
                flagged_measurements_table += "</table>"

                # Email content with HTML formatting
                email_content = f"""
                <html>
                    <body>
                        <h2>Record ID: {rec_id}</h2>
                        <p><strong>Coordinator:</strong> {coordinator}</p>
                        <p><strong>Measurements to be remeasured:</strong></p>
                        {flagged_measurements_table}
                    </body>
                </html>
                """

                # Create MIMEText object with HTML content
                msg = MIMEText(email_content, 'html')
                msg['Subject'] = f"Alert for Record ID: {rec_id}"
                msg['From'] = sender_email
                msg['To'] = 'villagesresearch@gmail.com'

                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)

                st.success("Data submitted successfully!")

    elif option == "Re-measure":
        # Store in Google Sheets without comparison
        data = [rec_id, option, remeasured_by, sternal_notch, height, weight, bmi, waist_circ, arm_circ]
        sheet.append_row(data)
        st.success("Re-measure data submitted successfully!")
