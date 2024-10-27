import httpx
import asyncio

WEBHOOK_URL = "https://hook.us2.make.com/59r6xsei62mv9f1jtpnj0lv39epw72aq"

payload = {
    "customerName": "Mohan Vikas",
    "customerAvailability_date": "2024-10-30",
    "customerAvailability_time": "12:00 PM",
    "specialNotes": "For therapy and massage"
}

async def send_to_webhook(payload: dict):
    """Send data to webhook asynchronously."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            print("Data successfully sent to webhook:", response.text)
        except httpx.HTTPStatusError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as e:
            print(f"Error sending data to webhook: {e}")

# Run the async function
asyncio.run(send_to_webhook(payload))

