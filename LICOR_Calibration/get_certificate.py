import requests
import pandas as pd
import os
from pathlib import Path

script_dir = Path(__file__).resolve().parent

# Load the Excel file
file_path = script_dir / 'UofU_LiCOR200R.xlsx'
excel_data = pd.ExcelFile(file_path)

# Print the sheet names
# print(excel_data.sheet_names)

# Load a sheet into a DataFrame by name
df = pd.read_excel(file_path, sheet_name='LiCor Li200R')  # Replace 'Sheet1' with your sheet name

# Display the DataFrame
#print(df)

# Display the data from column F
serial_numbers = df['Serial Number']  # Replace 'F' with the actual column name if it has one
#print(serial_numbers)

# URL for the certificate of calibration
#url = "https://www.licor.com/support/cal/2012-04/instruments/PY105683.pdf"
url_base = "https://www.licor.com/support/cal/2012-04/instruments/"

certificates_dir = script_dir / "certificates"
os.makedirs(certificates_dir, exist_ok=True)

for sn in serial_numbers:
  filename = certificates_dir / (sn+".pdf")
  print("====================================")
  print("Serial number: " + sn)
  if(os.path.isfile(filename)):
    print("Certificate already exists")
  else:
    print("Reqesting certificate")
    
    url = url_base+sn+".pdf"
    
    #Send a GET request to download the certificate
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
      # Save the certificate to a file
      with open(filename, "wb") as file:
        file.write(response.content)
      print("Certificate downloaded successfully. Saved as " + str(filename))
    else:
      print(f"Failed to download the certificate. Status code: {response.status_code}")
