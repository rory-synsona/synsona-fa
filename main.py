from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import asyncio
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatPerplexity
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

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
    mode: str

def run_openai(domain: str, tid: str, cid: str) -> dict:
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    messages = [
        SystemMessage("Translate the following from English into Italian"),
        HumanMessage("hi!"),
    ]
    response = model.invoke(messages)
    return response

def run_sonar(domain: str, tid: str, cid: str) -> str:
    prompt = ChatPromptTemplate.from_messages([("system", "Translate the following from English into Italian"), ("human", "{myprompt}")])
    chat = ChatPerplexity(model="sonar")
    chain = prompt | chat
    response = chain.invoke({"myprompt": "What is the time in Sydney, Australia?"})
    return response.content

async def send_post_for_callback(llm_response_content: str, tid: str) -> dict:
    url = os.getenv("SYNSONA_URL")
    print("Sending post request to Synsona: ", llm_response_content)
    payload = {
        "content": llm_response_content,
    }
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    return 0

async def process_request_async(domain: str, tid: str, cid: str) -> dict:
    print("Starting process_request_async")
    # call new function to start LLM
    llm_response = await asyncio.to_thread(run_sonar, domain, tid, cid)
    # send post request as callback
    await send_post_for_callback(llm_response, tid)
    return 0

def process_request_sync(domain: str, tid: str, cid: str) -> dict:
    # call new function to start LLM
    llm_response = run_openai(domain, tid, cid)
    return {"confirm": tid, "message": llm_response}

@app.post("/pie/")
async def pie(request_data: EchoRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header is None or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    if token == "asdf":
        # Run the process_request function in the background
        if request_data.mode == "async":
            asyncio.create_task(process_request_async(request_data.domain, request_data.tid, request_data.cid))
            return {"confirmed": request_data.tid}
        elif request_data.mode == "sync":
            response = process_request_sync(request_data.domain, request_data.tid, request_data.cid)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

'''
@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}
'''