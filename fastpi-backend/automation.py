from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from datetime import date
import json
import httpx
import logging
import os

# Define Webhook URL
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://hook.us2.make.com/iciq6etn4n2ddmhnssuf416ce9ep469b")

class CustomerDetails(BaseModel):
    customerName: str
    customerAvailability_date: str
    customerAvailability_time: str
    specialNotes: str

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class AutoServiceChat:
    def __init__(self):
        self.transcript = ""

    async def process_and_send_to_webhook(self, transcript):
        self.transcript = transcript

        system = """Extract customer details from the provided call transcript: name, availability date and time, and any special notes from the transcript.
        Also based on today's date, provide the exact date and time for availability."""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "This is the call transcript: \n{transcript} \n Today's date is {d1}"),
            ]
        )

        
        structured_llm = llm.with_structured_output(CustomerDetails)
        today = date.today()
        # dd/mm/YY
        today_date = today.strftime("%d/%m/%Y")

        input_prompt = prompt.invoke({"transcript": transcript, "d1": today_date})



        customer_details = structured_llm.invoke(input_prompt)

        print(customer_details)

        json_input = json.dumps(customer_details.dict(), indent=2)
        print(json_input)

        if (customer_details.customerName != "User"):
            await self.send_to_webhook(customer_details.dict())

    async def send_to_webhook(self, payload: dict):
        """Send extracted data to webhook."""
        print(f"Sending data to webhook: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    WEBHOOK_URL,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                print("Data successfully sent to webhook")
            except Exception as e:
                print(f"Error sending data to webhook: {e}")
