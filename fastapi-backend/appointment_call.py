from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime
import json
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
print("---------------")
print(f"WEBHOOK_URL: {WEBHOOK_URL}")
print("---------------")

class CustomerDetails(BaseModel):
    customerName: str
    customerAvailability_date: str
    customerAvailability_time: str
    conversationSummary: str
    conversationTranscript: str


class AppointmentWorkflow:
    def __init__(self):
        self.transcript = ""
        logger.info("Initializing AppointmentWorkflow")
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.day_name = datetime.today().strftime("%A")
        self.today_date = datetime.today().date()

    
    def process_transcript_and_send_to_webhook(self, transcript):
        if not isinstance(transcript, str):
            raise TypeError(f"Transcript must be a string, got {type(transcript)}")
            
        logger.info("Processing new transcript")
        print("\nProcessing new appointment request...")
        self.transcript = transcript

        system = """
        Extract customer details from the provided conversation transcript: 
        - name, 
        - availability date 
        - availability time
        - any any reason/requirement/description for the appointment and summarize it in conversation summary  
        - the entire conversation transcript.
         
        Also based on today's date and day of the week provided, figure out the exact date and time for availability that user has mentioned in the transcript.
        Note: The today's date is only for reference to figure out customer availability date, if the customer has not provided the date in the transcript then CustomerAvailability_date should be Unavailable.
        Similarly, if the customer has not provided the time in the transcript then CustomerAvailability_time should be Unavailable.
        """
    
        customer_details_prompt = ChatPromptTemplate.from_messages([
            ("system", system),
            ("human", "This is the call transcript: \n{transcript} \n Today's date is {date} and day is {day}"),
        ])

        

        structured_llm = self.llm.with_structured_output(CustomerDetails)

        try:
            print("\nExtracting customer details...")
            customer_details_input_prompt = customer_details_prompt.invoke({
                "transcript": self.transcript,
                "date": self.today_date,
                "day": self.day_name
            })

            print("Customer details input prompt:", customer_details_input_prompt)

            customer_details = structured_llm.invoke(customer_details_input_prompt) 
            
            print("\nExtracted Details:")
            print(f"Name: {customer_details.customerName}")
            print(f"Date: {customer_details.customerAvailability_date}")
            print(f"Time: {customer_details.customerAvailability_time}")
            print(f"Conversation Summary: {customer_details.conversationSummary}")
            print(f"Conversation Transcript: {customer_details.conversationTranscript}")

            #appointment_decision  = self.check_appointment(self.transcript)
            #if appointment_decision == "no":
                #return "User didnt book an appointment or provided details to schedule an appointment"
            
            #else:

            # Convert pydantic model to dict, then to JSON string
            customer_dict = customer_details.model_dump()
            print(f"\nCustomer dict type: {type(customer_dict)}")
            
            json_string = json.dumps(customer_dict)
            print(f"JSON string type: {type(json_string)}")
            
            # Convert JSON string back to dict for the payload
            payload = json.loads(json_string)
            print(f"Payload type: {type(payload)}")

            print("\nSending to webhook...")
            print(f"Payload: {payload}")

            if not WEBHOOK_URL:
                print("\nWarning: WEBHOOK_URL environment variable not set")
                return "Test mode: Webhook URL not configured"
            
            try:
                response = requests.post(
                    WEBHOOK_URL,
                    json=payload,
                )
                
                if response.headers.get("Content-Type") == "application/json":
                    response_data = response.json()
                    print("\nWebhook Response:")
                    print(response_data)
                    logger.info("Data successfully sent to webhook")
                else:
                    print("\nWebhook Response (non-JSON):")
                    print(response.text)
                    logger.info("Data sent to webhook (non-JSON response)")

                print("\nAppointment scheduled successfully!")
                return "Transcript processed and data sent to webhook"

            except requests.exceptions.RequestException as e:
                error_msg = f"Error sending data to webhook: {str(e)}"
                logger.error(error_msg)
                print(f"\nError: {error_msg}")
                return None

        except Exception as e:
            error_msg = f"Error processing appointment: {str(e)}"
            logger.error(error_msg)
            print(f"\nError: {error_msg}")
            return None

#for testing
def main():
    print("\n=== Starting Appointment Processing ===\n")
    
    transcript = """
    User: Hello.
    User: What can you do for me?
    Agent: We offer a range of automotive services, from routine maintenance like oil changes and tire rotations to more complex repairs on brakes, engine diagnostics, and transmission work. What kind of service are you looking for today?
    User: I'm looking for oil change and engine transmissions
    Agent: Great! We can definitely help you with an oil change and take a look at your engine transmission. May I have your name so we can get started with scheduling your appointment?
    User: Yeah.
    User: My name is Hrithik.
    Agent: Thank you, Hrithik. When would you be available to bring your car in for the service? We can work around your schedule.
    User: Monday at 2pm.
    Agent: Monday at 2 PM works perfectly. We'll see you then for your oil change and to check the engine transmission. If you have any other questions or need to reschedule, feel free to give us a call.
    User: 
    Agent: You're welcome! Looking forward to seeing you on Monday. Have a great day!
    """

    
    print(f"\nFinal Result: {result}")
    print("\n=== Processing Complete ===\n")

if __name__ == "__main__":
    main()