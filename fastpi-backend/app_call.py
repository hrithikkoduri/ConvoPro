import os
import json
import base64
import asyncio
import logging
import websockets
from pydantic import BaseModel
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from appointment_call import AppointmentWorkflow

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 5050))
appointment_workflow = AppointmentWorkflow()


SYSTEM_MESSAGE = """You are Donna and  AI receptionist for BasePower which is a electricity and battery provider. Your job is to politely engage with the client and 
obtain their name, availability, and service/work required. Ask one question at a time. Do not ask for other contact 
information, and do not check availability, assume we are free. Ensure the conversation remains friendly and professional, 
and guide the user to provide these details naturally. If necessary, ask follow-up questions to gather the required information."""
VOICE = "alloy"

LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

myapp = FastAPI()

# Session management
sessions: Dict[str, dict] = {}

class CustomerDetails(BaseModel):
    customerName: str
    customerAvailability: str
    specialNotes: str

# Add CORS middleware
myapp.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@myapp.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@myapp.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    """ Handle incoming call and return TwiML response to connect to Media Stream """
    
    response = VoiceResponse()
    response.say(
        "Please wait while we connect your call to the AI voice assistant"
    )
    response.pause(length=1)
    response.say("O.K. you can start talking!")

    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")

async def twilio_to_openai(websocket: WebSocket, openai_ws, session):
    """Send audio data from Twilio to OpenAI"""
    try:
        async for message in websocket.iter_text():
            data = json.loads(message)

            if data['event'] == 'media' and not openai_ws.closed:
                audio_append = {
                    "type": "input_audio_buffer.append",
                    "audio": data['media']['payload']
                }
                await openai_ws.send(json.dumps(audio_append))
            
            elif data['event'] == 'start':
                session["stream_sid"] = data['start']['streamSid']
                logger.info(f"Incoming stream has started {session['stream_sid']}")

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected")
        raise
    except Exception as e:
        logger.error(f"Error in twilio_to_openai: {e}")
        raise

async def openai_to_twilio(websocket: WebSocket, openai_ws, session, session_id):
    """Send audio data from OpenAI to Twilio"""
    try:
        async for openai_message in openai_ws:
            response = json.loads(openai_message)

            if response['type'] == 'session.updated':
                logger.info("Session updated successfully: %s", response)
                
            print("------------------")
            print("Response:",response)
            print("------------------")
            if response["type"] == "conversation.item.input_audio_transcription.completed":
                user_message = response["transcript"].strip()
                session["transcript"] += f"User: {user_message}\n"
                logger.info(f"User ({session_id}): {user_message}")
            
            elif response["type"] == "response.done" and response["response"]["status"] == "completed":
                logger.info("Response: %s", response)
                agent_message = next(
                    (content["transcript"] 
                     for content in response["response"]["output"][0]["content"] 
                     if "transcript" in content),
                    "Agent message not found"
                )
                session["transcript"] += f"Agent: {agent_message}\n"
                logger.info(f"Agent ({session_id}): {agent_message}")
            
            elif response["type"] == "response.audio.delta" and response.get("delta"):
                try:
                    audio_payload = base64.b64encode(
                        base64.b64decode(response['delta'])).decode('utf-8')
                    audio_delta = {
                        "event": "media",
                        "streamSid": session["stream_sid"],
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await websocket.send_json(audio_delta)
                except Exception as e:
                    logger.error(f"Error processing audio data: {e}")

    except Exception as e:
        logger.error(f"Error in openai_to_twilio: {e}")
        raise

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "input_audio_transcription": {
                "model": "whisper-1"
            }
        }
    }
    logger.info('Sending session update: %s', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

@myapp.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """ Handle Media Stream WebSocket connection between Twilio and OpenAI """
    await websocket.accept()
    logger.info("Client Connected")

    session_id = f"session_{asyncio.get_event_loop().time()}"
    session = sessions.get(session_id, {"transcript": "", "stream_id": None})
    sessions[session_id] = session
    
    openai_ws = None

    try:
        # Connect to OpenAI WebSocket and send session update
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }) as openai_ws:
            await send_session_update(openai_ws)

            # Create tasks for both directions of communication
            twilio_task = asyncio.create_task(twilio_to_openai(websocket, openai_ws, session))
            openai_task = asyncio.create_task(openai_to_twilio(websocket, openai_ws, session, session_id))

            # Wait for either task to complete (which would happen on disconnect)
            done, pending = await asyncio.wait(
                [twilio_task, openai_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel the other task
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Re-raise any exceptions from the completed tasks
            for task in done:
                try:
                    await task
                except WebSocketDisconnect:
                    raise  # Re-raise to trigger the finally block
                except Exception as e:
                    logger.error(f"Task error: {e}")
                    raise

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if openai_ws and not openai_ws.closed:
            await openai_ws.close()
        
        logger.info("Client Disconnected")
        logger.info("Session Transcript:")
        logger.info(session["transcript"])
        
        # Remove session from sessions dict
        if session_id in sessions:
            del sessions[session_id]

        # Optional: Send transcript to webhook
        # You could add webhook functionality here to send the transcript
        # to your external system
        result = appointment_workflow.process_transcript_and_send_to_webhook(session["transcript"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(myapp, host="0.0.0.0", port=PORT)