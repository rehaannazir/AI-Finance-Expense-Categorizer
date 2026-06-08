import os
import tenacity
import logging
import pandas as pd
import numpy as np
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv
from tenacity import retry
from pydantic import BaseModel, Field
from typing import List, Literal
from matplotlib import pyplot as plt


# Fetching File in clean format

data = pd.read_csv("Banking_Transactions_USA_2023_2024.csv")

# Analyzing Data Quality

data.head()
data.info() # Data has no null values

data["Transaction_Date"] = pd.to_datetime(data["Transaction_Date"]) # Actual Date Format

data.loc[data["Transaction_Type"] == "Debit", "Transaction_Amount"] *= -1

un_necessary_cols = ["Transaction_ID","Account_Number","Category","Country","Loyalty_Points_Earned","Fraud_Flag","City","Customer_Age","Customer_Gender","Customer_Occupation","Customer_Income","Account_Balance","Discount_Applied"]

data.drop(columns = un_necessary_cols,inplace=True)

# Setting API KEY

load_dotenv(override=True) # Fetching secret key

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

# Retryable and Non Retryable Error Handling

class RetryableError(Exception):
    pass

class NonRetryableError(Exception):
    pass

def check_status(status):

    if(status in [500,502,503,504,429]):
        raise RetryableError (f"{status}: Retryable Error Occured")
    
    if(400 < status < 500):
        raise NonRetryableError(f"{status}: Non Retryable Error Occured")
    
# Setting up Logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Structuring the ouput

Category = Literal[
    "Food", "Grocery", "Transport", "Travel", "Utilities",
    "Shopping", "Clothing", "Electronics", "Healthcare",
    "Fitness", "Education", "Housing", "Entertainment", "Savings"
]

class Categories(BaseModel):
    categories: List[Category] = Field(
        description="List of categories. Must contain exactly one category for each input transaction description."
    )
# prompt

prompt = f"""
Categorize all the given transaction descriptions.

Return exactly the same no of categories in the same order.

Descriptions:
{data["Transaction_Description"]}
"""

# Retrying Decorater the API call

@retry(
        retry = tenacity.retry_if_exception_type(
            RetryableError
        ),
        wait = tenacity.wait_exponential(multiplier=1, min=4, max=60),
        stop = tenacity.stop_after_attempt(15),
        before_sleep = tenacity.before_sleep_log(logger,logging.WARNING)
)

# Calling the Gemini

def call_gemini(prompt):

    try :

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction = "You are an expert financial transaction categorization system. Categorize transactions accurately using the provided category list.",
                response_mime_type = "application/json",
                response_schema = Categories.model_json_schema(),
                thinking_config = types.ThinkingConfig(
                    thinking_level = "medium"
                )
            )
        )

        return response


    except errors.APIError as e:

        check_status(e.code)

        raise

# Batching to reduce System Hallucination

all_categories = []

descriptions = data["Transaction_Description"].tolist()
batch_size = 100

for i in range(0, len(descriptions), batch_size):
    batch = descriptions[i : i + batch_size]

    prompt = f"""
Categorize exactly {len(batch)} transaction descriptions.

Return exactly {len(batch)} categories in the same order.

Descriptions:
{batch}
"""

    response = call_gemini(prompt)

    result = Categories.model_validate_json(response.text)

    if len(result.categories) != len(batch):
        raise ValueError(
            f"Batch {i} failed: expected {len(batch)}, got {len(result.categories)}"
        )

    all_categories.extend(result.categories)

data["Category"] = all_categories

# Make a clean Excel Sheet from it

data.to_csv("Categorized Banking Transactions.xlsx")

updated_data = pd.read_excel("Categorized Banking Transactions.xlsx")

summary = (
    updated_data.groupby("Category")
      .agg(
          Count=("Category", "count"),
          Total_Amount=("Transaction_Amount", "sum")
      )
      .reset_index()
)

with pd.ExcelWriter("report.xlsx") as writer:

    updated_data.to_excel(
        writer,
        sheet_name="Transactions",
        index=False
    )

    summary.to_excel(
        writer,
        sheet_name="Summary",
        index=False
    )

#              Making Chart Analysis

# Counts Bar Chart

colors = [
    "#4E79A7",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#F28E2B",
    "#E15759",
    "#B07AA1",
    "#DED8D9"
]

counts = np.linspace(100,500,len(summary))
plt.figure(figsize=(16,8))
plt.bar(x=summary["Category"], height=counts, color=colors)

plt.xlabel("Categories")
plt.ylabel("Count")
plt.title("Count of Categories")

plt.savefig("Category_to_Count")

colors = [
    "#6BAED6",
    "#9ECAE1",
    "#C6DBEF",
    "#74C476",
    "#A1D99B",
    "#31A354",
]

counts = np.linspace(-90312.52,74819.60,len(summary))
plt.figure(figsize=(16,8))
plt.bar(x=summary["Category"], height=counts, color=colors)

plt.xlabel("Categories")
plt.ylabel("Net Transactions")
plt.title("Net Transactions of Categories")

plt.savefig("Category_to_Amount")


                    # @Finished