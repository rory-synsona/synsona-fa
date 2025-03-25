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
    target_url: str
    target_id: str
    customer_id: str
    bpwf_id: str
    wf_id: str
    helper_string: str

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

def run_sonar_v1(request_data: EchoRequest) -> str:
    print("run_sonar_v1: ", request_data.target_url)

    #messages = [
    #    ("system", "Determine the official NAME of the company with official website as follows. Only reply with the name."),
    #    ("human", "{target_url}")
    #]
    messages = [
        ("system",
         """ROLE: You are a research assistant for 'Phriendly Phishing' (https://www.phriendlyphishing.com). Phriendly Phishing specializes in security awareness and phishing simulation training. The company offers tailored, automated training solutions that empower organizations to combat cyber threats, including phishing and ransomware. Their value proposition lies in delivering engaging, customizable learning experiences for each department that foster long-lasting behavioral change among employees, thereby reducing the risk of financial and reputational damage from cyber attacks. Phriendly Phishing's content is recognized for being localized and more relevant to Australian and New Zealand audiences, contributing to an increase in completion rates compared to other offerings.
         
        OBJECTIVE: The user will assign you a target account. You are to thoroughly research the company to find potential triggers for engagement related to topics that resonate with Phriendly Phishing such as: 'cyber security', 'phishing attacks', 'cyber attacks', 'ransomware' or changes in leadership like the 'Chief Information Security Officer (CISO)'.

        SOURCES: Your research about the target account must be published within the last 12 months and include these sources:
        1. News about the target account
        2. News about the target account's main competitors
        3. News about the target account's industry
        4. News about companies in Australia or New Zealand
        5. (If they are publicly traded) Review their annual report
        6. (If they are publicly traded) Review their latest earnings report
        
        OUTPUT TEMPLATE: For each trigger, use the following template:
        Name: Brief name of the trigger
        Source: URL of the source where the trigger was found
        Date: Publish date of the article
        Summary: Brief summary of the trigger with high brevity for a c-level executive, focusing on figures, metrics, monitory values, and percentages
        Relevance: Explain why this trigger is relevant to Phriendly Phishing
        
        Your response must only include the triggers and exclude introduction and concluing summary."""),
        ("human", "Target account: {target_url}")
    ]
    prompt_template = ChatPromptTemplate.from_messages(messages)
    chat = ChatPerplexity(model="sonar-deep-research")
    chain = prompt_template | chat
    response = chain.invoke({"target_url": request_data.target_url})
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

async def send_post_callback_v1(llm_response_content: str, request_data: EchoRequest) -> dict:
    bubble_app_url = os.getenv("SYNSONA_BUBBLE_URL_TEST")
    print("Sending post request (", request_data.wf_id,") to Synsona: ", llm_response_content)
    payload = {
        "content": llm_response_content,
        "target_id": request_data.target_id,
        "bpwf_id": request_data.bpwf_id,
        "wf_id": request_data.wf_id,
    }
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(bubble_app_url, json=payload, headers=headers)
        response.raise_for_status()
    return 0

async def process_request_async(domain: str, tid: str, cid: str) -> dict:
    print("Starting process_request_async")
    # call new function to start LLM
    llm_response = await asyncio.to_thread(run_sonar, domain, tid, cid)
    # send post request as callback
    await send_post_for_callback(llm_response, tid)
    return 0

async def process_request_async_v1(request_data: EchoRequest) -> dict:
    print("Starting process_request_async")
    # call new function to start LLM
    llm_response = await asyncio.to_thread(run_sonar_v1, request_data)
    # send post request as callback
    await send_post_callback_v1(llm_response, request_data)
    return

def process_request_sync(domain: str, tid: str, cid: str) -> dict:
    # call new function to start LLM
    llm_response = run_openai(domain, tid, cid)
    return {"confirm": tid, "message": llm_response}

def process_request(request_data: EchoRequest) -> dict:
    print("Starting process_request")
    # call new function to start LLM

    # bpwf_id = 1 is for sonar-deep-research for triggers
    if (request_data.bpwf_id == "1"):
        asyncio.create_task(process_request_async_v1(request_data))
        return {"confirmed": request_data.wf_id}
    else:
        return {"error": "Invalid bpwf_id"}

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

@app.post("/pie/v1/")
async def pie_v1(request_data: EchoRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    if auth_header is None or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    if token == "asdf":
        if request_data.bpwf_id is not None:
            response = process_request(request_data)
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