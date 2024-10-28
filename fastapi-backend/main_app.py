# main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager
from app_call import myapp as call_app
from app_text import app as text_app, lifespan as text_lifespan

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize text app dependencies
    async with text_lifespan(text_app):
        yield

# Create the main application
main_app = FastAPI(lifespan=lifespan)

# Add CORS middleware
main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the call and text applications with their respective prefixes
main_app.mount("/call", call_app)
main_app.mount("/text", text_app)

# Root endpoint
@main_app.get("/")
async def root():
    return {
        "message": "Unified AI Communication Server",
        "endpoints": {
            "call": "/call",
            "text": "/text"
        }
    }

if __name__ == "__main__":
    # Run the server on port 8000
    uvicorn.run(main_app, host="0.0.0.0", port=8000)