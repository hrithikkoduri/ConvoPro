from fastapi import FastAPI, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
from storage import VectorStore
from ai_output import Output
import os
import uvicorn
import asyncio
from typing import Dict
from datetime import datetime
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from appointment_call import AppointmentWorkflow

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
appointment_workflow = AppointmentWorkflow()

class SessionManager:
    def __init__(self):
        self.current_session: Dict[str, any] = None
        self.timeout = 60  # seconds
        self.timeout_task: asyncio.Task = None
        self.transcript = []
        self.last_response = None

    async def cleanup(self):
        """Cleanup current session and task"""
        logger.info("Starting cleanup of session...")
        if self.timeout_task:
            try:
                self.timeout_task.cancel()
                await self.timeout_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error cancelling timeout task: {e}")
        
        self.current_session = None
        self.transcript = []
        self.last_response = None
        logger.info("Cleanup completed")

    async def create_session(self) -> bool:
        """Create a new session"""
        is_new_session = self.current_session is None or not self.current_session.get('is_active', False)


        if self.timeout_task:
            self.timeout_task.cancel()
        
        self.current_session = {
            'start_time': datetime.now(),
            'is_active': True,
            'message_count': 0
        }
        
        logger.info(f"Session {'created' if is_new_session else 'renewed'}")
        return is_new_session

    async def end_session(self) -> str:
        """End the current session"""
        if self.current_session:
            session_duration = datetime.now() - self.current_session['start_time']
            messages_exchanged = self.current_session['message_count']
            
            if self.timeout_task:
                self.timeout_task.cancel()
            
            self.current_session['is_active'] = False
            
            summary = (
                "🔚 Session ended\n"
                f"Duration: {int(session_duration.total_seconds())} seconds\n"
                f"Messages exchanged: {messages_exchanged}"
            )
            
            logger.info(f"Ended session. {summary}")
            
            if self.transcript:
                transcript_text = "\n".join(self.transcript)
                print("Transcript:", transcript_text)
                result = appointment_workflow.process_transcript_and_send_to_webhook(transcript_text)
                print("Result:", result)
                transcript_text = ""
                self.transcript = []
                
            
            self.current_session = None
            return summary
        return "No active session to end"
        
    def add_to_transcript(self, sender: str, message: str):
        """Add message to transcript"""
        self.transcript.append(f"{sender}: {message}")

    async def start_timeout(self, send_message_callback):
        """Start timeout countdown for session"""
        if self.current_session:
            if self.timeout_task:
                self.timeout_task.cancel()
            
            self.timeout_task = asyncio.create_task(
                self._timeout_handler(send_message_callback)
            )

    async def _timeout_handler(self, send_message_callback):
        """Handle session timeout"""
        await asyncio.sleep(self.timeout)
        summary = await self.end_session()
        timeout_message = (
            "⏰ Session timed out due to inactivity.\n"
            f"{summary}\n\n"
            "Send a new message to start a fresh session!"
        )
        # Send the timeout message using the callback
        await send_message_callback(timeout_message)

    def increment_message_count(self):
        """Increment the message count for current session"""
        if self.current_session:
            self.current_session['message_count'] += 1

    def get_session_info(self) -> str:
        """Get current session information"""
        if self.current_session:
            duration = datetime.now() - self.current_session['start_time']
            return (
                f"Current session duration: {int(duration.total_seconds())} seconds\n"
                f"Messages in this session: {self.current_session['message_count']}"
            )
        return "No active session"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up application...")
    deep_lake = VectorStore()
    app.state.db = deep_lake.load_db()
    app.state.output = Output(app.state.db)
    app.state.session_manager = SessionManager()
    
    yield
    
    # Shutdown
    logger.info("Application shutdown initiated...")
    if hasattr(app.state, 'session_manager'):
        await app.state.session_manager.cleanup()
    logger.info("Application shutdown complete")

app = FastAPI(lifespan=lifespan)

def generate_response(output: Output, incoming_msg: str) -> str:
    """Generates a response to the incoming message using LangChain."""
    response = output.chat(incoming_msg)
    logger.info(f"Generated response: {response}")
    return response

async def send_whatsapp_message(message: str):
    """Helper function to format and send WhatsApp messages"""
    twilio_response = MessagingResponse()
    twilio_response.message(message)
    # This is where you would typically send the message via Twilio's API
    # For now, we'll just log it
    logger.info(f"Sending WhatsApp message: {message}")
    return str(twilio_response)

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        form = await request.form()
        incoming_msg = form.get("Body", "").strip()
        session_manager = request.app.state.session_manager
        
        # Start or refresh session
        is_new_session = await session_manager.create_session()
        
        # Increment message count and add to transcript
        session_manager.increment_message_count()
        session_manager.add_to_transcript("User", incoming_msg)
        
        # Generate AI response
        ai_response = generate_response(request.app.state.output, incoming_msg)
        session_manager.add_to_transcript("Agent", ai_response)
        
        # Prepare complete response
        full_response = (
            f"{'🆕 New session started!\n' if is_new_session else ''}"
            f"{ai_response}\n\n"
            "⏳ Session will timeout after 60 seconds of inactivity"
        )
        
        # Store the last response
        session_manager.last_response = full_response
        
        # Start timeout countdown with callback to send message
        await session_manager.start_timeout(send_whatsapp_message)
        
        # Create Twilio response
        twilio_response = MessagingResponse()
        twilio_response.message(full_response)
        
        return Response(content=str(twilio_response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in whatsapp_webhook: {str(e)}")
        return Response(content="An error occurred", status_code=500)

if __name__ == "__main__":
    uvicorn.run(app_text, host="0.0.0.0", port=8000)