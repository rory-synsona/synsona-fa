from fastapi import FastAPI, Query, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()
pplx_api_key = os.getenv("PPLX_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins TO DO: change to specific origin
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class EchoRequest(BaseModel):
    domain: str
    tid: str
    cid: str

def run_llm(domain: str, tid: str, cid: str) -> dict:
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    messages = [
        SystemMessage("Translate the following from English into Italian"),
        HumanMessage("hi!"),
    ]

    response = model.invoke(messages)
    return response

def send_post_for_callback(llm_response: str, tid: str) -> dict:
    url = os.getenv("SYNSONA_URL")
    payload = {
        "response": llm_response,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0
    }
    headers = {"Content-Type": "application/json"}
    
    response = httpx.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return 0

def process_request(domain: str, tid: str, cid: str) -> dict:
    # call new function to start LLM
    llm_response = run_llm(domain, tid, cid)

    # send post request as callback
    callback_response = send_post_for_callback(llm_response.content, tid)

    return {"confirm": tid, "llm_response": llm_response.content}

@app.post("/pie/")
async def echo(request: EchoRequest, req: Request):
    auth_header = req.headers.get("Authorization")
    if (auth_header is None or not auth_header.startswith("Bearer ")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    if token == "asdf":
        result = process_request(request.domain, request.tid, request.cid)
        return result
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

'''
@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}
'''

'''
@app.get("/echo/")
async def echo(value: str = Query(..., description="The value to be echoed")):
    return {"confirmation61": value}
'''
