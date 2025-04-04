from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import asyncio
from datetime import date
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatPerplexity
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
import json

# Import the mappings from mappings.py
from mappings import BPSTEP_MAPPINGS

# Import messages from external file
from messages import ANGLES1_MESSAGES, TRIGGERS_TGT_CISO_1, TRIGGERS_IND_CISO_1

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
    input_json: dict

def run_bpstep_Angles1(request_data: PieRequest) -> dict:
    # get variables from input_json in request
    input_json_dict = request_data.input_json
    input_triggers = input_json_dict.get("triggers")
    input_target_company = input_json_dict.get("target_company")

    print("run_bpstep_Angles1: ", input_json_dict)
    print("input_triggers: ", input_triggers)   
    print("input_target_company: ", input_target_company)

    messages = ANGLES1_MESSAGES
    chat = init_chat_model("o3-mini", model_provider="openai")
    # chat = init_chat_model("gpt-4o-mini", model_provider="openai")
    prompt_template = ChatPromptTemplate.from_messages(messages)  
    chain = prompt_template | chat
    response = chain.invoke({"input_target_company": input_target_company, "input_triggers": input_triggers})

    return response

def run_bpstep_Triggers(request_data: PieRequest, messages) -> dict:
    # get variables from input_json in request
    input_json_dict = request_data.input_json
    input_target_url = input_json_dict.get("target_url")
    
    print("run_bpstep_Triggers: ", input_json_dict, " => ", input_target_url)

    chat_sonar_dr = ChatPerplexity(model="sonar-deep-research")
    # chat = ChatPerplexity(model="sonar")
    # messages = TRIGGERS_TGT_CISO_1
    prompt_template = ChatPromptTemplate.from_messages(messages)
    chain = prompt_template | chat_sonar_dr
    response = chain.invoke(
        {"input_target_url": input_target_url},
        config={
            "web_search_options": {
                "search_context_size": "high"
            }
        }
    )

    return response

def run_bpstep_generic(request_data: PieRequest) -> dict:
    # get variables from input_json in request
    input_json_dict = request_data.input_json
    input_prompt_text = input_json_dict.get("prompt_text")
    input_model_name = input_json_dict.get("model_name")
    input_model_temp = input_json_dict.get("model_temp")
    input_model_top_p = input_json_dict.get("model_top_p")

    print("run_bpstep_Triggers: ", input_json_dict, " => ", input_prompt_text)

    if input_model_name in ["gpt-4o-mini", "gpt-4o"]:
        print("Using OpenAI model: ", input_model_name)
        chat_model = ChatOpenAI(
            model=input_model_name,  # Specify the model name
            temperature=input_model_temp,      # Adjust temperature for creativity
            top_p=input_model_top_p,  # Adjust top_p for sampling
        )
    elif input_model_name in ["sonar", "sonar-deep-research"]:
        print("Using Sonar model: ", input_model_name)
        chat_model = ChatPerplexity(
            model=input_model_name,
            temperature=input_model_temp,
            top_p=input_model_top_p,
        )
    elif input_model_name in ["o3-mini", "o3"]:
        print("Using OpenAI reasoning model: ", input_model_name)
        chat_model = ChatOpenAI(
            model=input_model_name,
            reasoning_effort="medium"
        )
    elif input_model_name in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro-exp-03-25"]:
        print("Using Google model: ", input_model_name)     
        chat_model = ChatGoogleGenerativeAI(
            model=input_model_name
        )
    else:
        print("Unknown model name. Please provide a valid model.")

    messages = [
        ("system", "Today's date is {date}"),
        ("human", "{input_prompt_text}")
    ]

    prompt_template = ChatPromptTemplate.from_messages(messages)
    chain = prompt_template | chat_model
    response = chain.invoke(
        {"input_prompt_text": input_prompt_text,
         "date": date.today().isoformat()}  # Use the current date in ISO format
    )

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
    }
    headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(bubble_app_url, json=payload, headers=headers)
        response.raise_for_status()
        print("Payload: ", payload)
    return

async def process_request_async_v1(request_data: PieRequest) -> dict:
    print("Starting process_request_async")

    # Use the mappings to determine the action based on bpstep_id
    bpstep = BPSTEP_MAPPINGS.get(request_data.bpstep_id)

    if bpstep == "Company triggers":
        print("bpstep_id is 'Company triggers' 1742963840776x872202725975654400")

        response = await asyncio.to_thread(run_bpstep_Triggers, request_data, TRIGGERS_TGT_CISO_1)

        # Extract values from usage_metadata
        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)
    
    elif bpstep == "Industry triggers":
        print("bpstep_id is 'Industry triggers' 1743642197570x161409188642422800")

        response = await asyncio.to_thread(run_bpstep_Triggers, request_data, TRIGGERS_IND_CISO_1)

        # Extract values from usage_metadata
        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "Angles persona 1":
        print("bpstep_id is Angles persona 1 - 1743007240371x889852377243582500")
        response = await asyncio.to_thread(run_bpstep_Angles1, request_data)

        # Extract values from usage_metadata
        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "Angles persona 2":
        print("bpstep_id is 'Angles persona 2' - 1743007304138x215986182283591680")
        response = await asyncio.to_thread(run_bpstep_Angles1, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "Angles persona 3":
        print("bpstep_id is 'Angles persona 3' - 1743007578100x896562523443036200")
        response = await asyncio.to_thread(run_bpstep_Angles1, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "SDR email 1":
        print("bpstep_id is 'SDR email 1' - 1743007958890x533155609689718800")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "SDR email 2":
        print("bpstep_id is 'SDR email 2' - 1743008107420x694234347110137900")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "SDR email 3":
        print("bpstep_id is 'SDR email 3' - 1743008147961x485549258569416700")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "LinkedIn message 1":
        print("bpstep_id is 'LinkedIn message 1' - 1743706071501x986170635387142100")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "LinkedIn voice message script":
        print("bpstep_id is 'LinkedIn voice message script' - 1743706125451x482733737766289400")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    elif bpstep == "Phone call script":
        print("bpstep_id is 'Phone call script' - 1743706323661x613148516472062000")
        response = await asyncio.to_thread(run_bpstep_generic, request_data)

        input_tokens = response.usage_metadata['input_tokens']
        output_tokens = response.usage_metadata['output_tokens']
        await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    # Add more elif statements as needed for other mappings in BPSTEP_MAPPINGS

    else:
        print("bpstep_id not found in mappings")

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
        if request_data.bpstep_id:
            print("Headers: ", http_request.headers)
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")