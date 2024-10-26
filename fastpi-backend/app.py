from fastapi import FastAPI, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
import logging
from VectorStore import VectorStore
from ai_output import Output
from twilio.rest import Client
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

app = FastAPI()
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
deep_lake = VectorStore()
db = deep_lake.load_db()
output = Output(db)
logger = logging.getLogger(__name__)
approved_numbers = ['15202862703']


def generate_response(incoming_msg):
    """ 
    Generates a response to the incoming message using LangChain.
    Use this for general conversation and queries.
    """
    response = output.chat(incoming_msg)
    logger.info(f"Generated response: {response}")
    return response


def send_twilio_message(to_number, message_body):
    """
    Sends a message using Twilio to the specified number.
    """
    try:
        message = client.messages.create(body=message_body,
                                         from_='whatsapp:' +
                                         TWILIO_PHONE_NUMBER,
                                         to='whatsapp:' + to_number)
        output.update_chat_history(message_body)
        logger.info(f"Sent message to {to_number}: {message_body}")
        return message.sid
    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {str(e)}")
        return None


@app.post("/broadcast")
async def broadcast_message(request: Request):
    try:
        form = await request.form()
        message_body = form.get("Body", "").strip()
        numbers_list = form.get("Numbers",
                                "").split(',')  # Get numbers from form data
        logger.info(f"Received broadcast message: {message_body}")
        logger.info(f"Broadcasting to numbers: {numbers_list}")

        for number in numbers_list:
            # You might want to maintain a list of approved numbers and check against it
            if number.strip() in approved_numbers:
                send_twilio_message(number.strip(), message_body)
            else:
                logger.warning(
                    f"Number {number} is not approved for sandbox use")

        return Response(content="Broadcast messages sent successfully",
                        status_code=200)
    except Exception as e:
        logger.error(f"Error in broadcast_message: {str(e)}")
        return Response(content="An error occurred during broadcasting",
                        status_code=500)


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
        incoming_msg = form.get("Body", "").strip()
        print("Incoming message:", incoming_msg)

        response = generate_response(incoming_msg)
        twilio_response = MessagingResponse()
        twilio_response.message(response)
        print("Response:", response)

        return Response(content=str(twilio_response),
                        media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in whatsapp_webhook: {str(e)}")
        return Response(content="An error occurred", status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
