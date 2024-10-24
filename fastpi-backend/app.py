from fastapi import FastAPI, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
import logging
from VectorStore import VectorStore
from ai_output import Output
from twilio.rest import Client
import os
import uvicorn
from dotenv import load_dotenv
from langchain.agents import tool, initialize_agent, AgentType, Tool
from langchain_openai import OpenAI

load_dotenv()
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
CALENDLY_LINK = os.getenv('CALENDLY_LINK', 'https://calendly.com/your-link')

app = FastAPI()
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
deep_lake = VectorStore()
db = deep_lake.load_db()
output = Output(db)
logger = logging.getLogger(__name__)
approved_numbers = ['15202862703']

llm = OpenAI(model="gpt-3.5-turbo-instruct", temperature=0)

@tool
def generate_response(incoming_msg:str) -> str:
    """ 
    Generates a response to the incoming message using LangChain.
    Use this for general conversation and queries.
    """
    response = output.chat(incoming_msg)
    logger.info(f"Generated response: {response}")
    return response

@tool
def send_calendly_link(incoming_msg: str = "") -> str:
    """
    Sends the Calendly booking link.
    Use this when user wants to schedule a meeting or appointment.
    """
    response = output.schedule_meeting()

    return response


def send_twilio_message(to_number, message_body):
    """
    Sends a message using Twilio to the specified number.
    """
    try:
        message = client.messages.create(
            body=message_body,
            from_='whatsapp:' + TWILIO_PHONE_NUMBER,
            to='whatsapp:' + to_number
        )
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
        numbers_list = form.get("Numbers", "").split(',')  # Get numbers from form data
        logger.info(f"Received broadcast message: {message_body}")
        logger.info(f"Broadcasting to numbers: {numbers_list}")

        for number in numbers_list:
            # You might want to maintain a list of approved numbers and check against it
            if number.strip() in approved_numbers:
                send_twilio_message(number.strip(), message_body)
            else:
                logger.warning(f"Number {number} is not approved for sandbox use")

        return Response(content="Broadcast messages sent successfully", status_code=200)
    except Exception as e:
        logger.error(f"Error in broadcast_message: {str(e)}")
        return Response(content="An error occurred during broadcasting", status_code=500)

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
        incoming_msg = form.get("Body", "").strip()
        logger.info(f"Received message: {incoming_msg}")

        tools = [
            Tool(
                name="Generate Response",
                description="Generate a standard response for general queries and conversation",
                func = generate_response
            ),
            Tool(
                name="Schedule Meeting",
                description="Send Calendly link when user wants to schedule a meeting or appointment",
                func = send_calendly_link
            ),
        ]
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True,
        )

        agent_response = agent.run(incoming_msg)
           
        twilio_response = MessagingResponse()
        twilio_response.message(agent_response)
        logger.info(f"Generated response: {agent_response}")

        return Response(content=str(twilio_response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in whatsapp_webhook: {str(e)}")
        return Response(content="An error occurred", status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)