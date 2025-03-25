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
import json

# Load environment variables
load_dotenv()

# Start server
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins TO DO: change to specific origin
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class PieRequest(BaseModel):
    customer_id: str
    target_id: str
    bpwf_id: str
    bpstep_id: str
    wf_id: str
    step_id: str
    input_json: str

    def get_input_json_dict(self) -> dict:
        return json.loads(self.input_json)

def run_openai(domain: str, tid: str, cid: str) -> dict:
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    messages = [
        SystemMessage("Translate the following from English into Italian"),
        HumanMessage("hi!"),
    ]
    response = model.invoke(messages)
    return response

def run_bpwf_1(request_data: PieRequest) -> dict:
    input_json_dict = request_data.get_input_json_dict()
    target_url = input_json_dict.get("target_url")
    print("run_bpwf_1: ", input_json_dict, " => ", target_url)

    messages = [("system", "You are a friendly assistant. What is the target URL?"), ("human", "Target url = {target_url}")]

    # messages = [
    #     ("system",
    #      """ROLE: You are a research assistant for 'Phriendly Phishing' (https://www.phriendlyphishing.com). Phriendly Phishing specializes in security awareness and phishing simulation training. The company offers tailored, automated training solutions that empower organizations to combat cyber threats, including phishing and ransomware. Their value proposition lies in delivering engaging, customizable learning experiences for each department that foster long-lasting behavioral change among employees, thereby reducing the risk of financial and reputational damage from cyber attacks. Phriendly Phishing's content is recognized for being localized and more relevant to Australian and New Zealand audiences, contributing to an increase in completion rates compared to other offerings.
         
    #     OBJECTIVE: The user will assign you a target account. You are to thoroughly research the company to find potential triggers for engagement related to topics that resonate with Phriendly Phishing
        
    #     RELEVANT TOPICS for Phriendly Phishing:
    #     1. cyber breaches
    #     2. cyber security
    #     3. phishing attacks
    #     4. cyber attacks
    #     5. ransomware
    #     6. changes in security leadership (Chief Information Security Officer or CISO)'

    #     RESEARCH SOURCES: Your search about the target account MUST include the following sources
    #     1. Recent news about the target account
    #     2. Recent news about the target account's main competitors
    #     3. Recent news about the target account's industry
    #     4. Recent news about companies in Australia or New Zealand
    #     5. Recent change to regulations like APRA, ISO Certifications, Australian/New Zealand Government guidelines around cyber breaches
    #     5. Review their latest Directors' Report
    #     6. Review their latest Annual Financial Report
    #     7. Review their latest Half-Year Financial Report
        
    #     OUTPUT TEMPLATE: Use this template for each trigger you find
    #     Title: Concise title of the trigger
    #     Date: Publish date
    #     Summary: Concise summary of the trigger with high brevity for a c-level executive, focusing on details (who/what/when/where/why/how), figures, metrics, monitory values, and percentages
    #     Relevance: Explain why this trigger is relevant to Phriendly Phishing
    #     Reference: Exact URL of the source of the trigger
        
    #     Your response must only include the triggers and exclude introduction and concluding summary."""),
    #     ("human", "Target account to research: {target_url}")
    # ]
    prompt_template = ChatPromptTemplate.from_messages(messages)
    # chat = ChatPerplexity(model="sonar-deep-research")
    chat = ChatPerplexity(model="sonar")
    chain = prompt_template | chat
    response = chain.invoke({"target_url": target_url})
    return response

async def send_post_callback_v1(response_content: str, i_tokens: int, o_tokens: int, o_r_tokens: int, request_data: PieRequest) -> dict:
    print("Sending post request (step=", request_data.step_id,") to Synsona Bubble App")
    bubble_app_url = os.getenv("SYNSONA_BUBBLE_URL_TEST")
    payload = {
        "response_content": response_content,
        "customer_id": request_data.customer_id,
        "target_id": request_data.target_id,
        "bpwf_id": request_data.bpwf_id,
        "bpstep_id": request_data.bpstep_id,
        "wf_id": request_data.wf_id,
        "step_id": request_data.step_id,
        "i_tokens": i_tokens,
        "o_tokens": o_tokens,
        "o_r_tokens": o_r_tokens,
        "input_json": request_data.input_json  # Ensure input_json is sent as a string
    }
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(bubble_app_url, json=payload, headers=headers)
        response.raise_for_status()
    return 0

async def process_request_async_v1(request_data: PieRequest) -> dict:
    print("Starting process_request_async")

    if request_data.bpwf_id == "1":
        print("bpwf_id is 1 - Triggers")

        response = await asyncio.to_thread(run_bpwf_1, request_data)

        # Extract values from usage_metadata
        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    if request_data.bpwf_id == "2":
        print("bpwf_id is 2!")

    return

def process_request(request_data: PieRequest) -> dict:
    print("Starting process_request")
    asyncio.create_task(process_request_async_v1(request_data))
    return {"reciept_confirmed": request_data.step_id}

@app.post("/pie/v1/")
async def pie_v1(request_data: PieRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    
    if (auth_header is None or not auth_header.startswith("Bearer ")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]

    if token == "syn-e5f3a7d6c9b4f2a1c9d9e7b6a3f1b2c4":
        if request_data.bpwf_id:
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")