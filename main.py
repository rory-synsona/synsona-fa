from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
import os
import asyncio
import requests
from datetime import date
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_perplexity import ChatPerplexity
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain.agents import Tool, initialize_agent, AgentExecutor, OpenAIFunctionsAgent, create_tool_calling_agent
from langchain.agents import AgentExecutor
from langchain.agents.agent_types import AgentType
from langchain_core.exceptions import LangChainException
import json
import time

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

# Define API endpoint first
@app.post("/pie/v1/")
async def pie_v1(request_data: PieRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    
    if (auth_header is None or not auth_header.startswith("Bearer ")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]

    if token == "syn-e5f3a7d6c9b4f2a1c9d9e7b6a3f1b2c4":
        if request_data.bpstep_id:
            print("Headers: ", http_request.headers)
            print("Client: ", http_request.client.host)
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

# Mount static files to /static path (after API endpoint definition)
app.mount("/static", StaticFiles(directory="public", html=True), name="public")

# Tool to scrape a website
def scrape_webpage_content(url: str) -> str:
    request_url = "https://r.jina.ai/" + url
    headers = {
        "Authorization": "Bearer jina_56a782d10f5e4b71b9472f59577a4e0cDwU7yi_F5h2_r8C9I8YB2DyG6jei",
        "X-Return-Format": "markdown",
        "X-With-Links-Summary": "true"
    }

    response = requests.get(request_url, headers=headers)

    if response.status_code == 200:
        return response.text
    else:
        return f"Error: Unable to scrape {request_url}. Status code: {response.status_code}"

# Tool to search the web using a query
def search_internet(query: str) -> str:
    request_url = "https://api.search.brave.com/res/v1/web/search?result_filter=web,news&q=" + query
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": "BSA4Fjk_jYeHhcFQDMUxKtyfgB0JiTf"
    }

    response = requests.get(request_url, headers=headers)

    if response.status_code == 200:
        return response.json()  # Returns JSON response
    else:
        return f"Error: Unable to scrape {request_url}. Status code: {response.status_code}"

def run_bpstep_generic(request_data: PieRequest) -> dict:
    
    # Get EXPECTED variables from input_json in request
    input_json_dict = request_data.input_json
    input_prompt_text = input_json_dict.get("prompt_text")
    input_model_name = input_json_dict.get("model_name")
    input_model_temp = input_json_dict.get("model_temp")
    input_model_top_p = input_json_dict.get("model_top_p")
    input_bubble_test = input_json_dict.get("bubble_test", False)  # Default to False if not provided
    input_tool1 = input_json_dict.get("tool1")
    
    print("run_bpstep_generic: ", input_json_dict)

    # Prepare model kwargs
    model_kwargs = {
        "top_p": input_model_top_p,
        "temperature": input_model_temp, 
    }

    if input_model_name in ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"]:
        print("Using OpenAI model: ", input_model_name)
        chat_model = ChatOpenAI(
            model=input_model_name,  # Specify the model name
            temperature=input_model_temp,
            top_p=input_model_top_p,
        )
    elif input_model_name in ["sonar", "sonar-pro", "sonar-deep-research"]:
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
    elif input_model_name in [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro-exp-03-25"
    ]:
        print("Using Google model: ", input_model_name)     
        chat_model = ChatGoogleGenerativeAI(
            model=input_model_name,
            temperature=input_model_temp,
            top_p=input_model_top_p,
        )
    elif input_model_name in [
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-7-sonnet-latest",
        "claude-3-opus-latest"
    ]:
        print("Using Anthropic model: ", input_model_name)
        chat_model = ChatAnthropic(
            model=input_model_name,
            temperature=input_model_temp,
            top_p=input_model_top_p,
        )
    else:
        print("ERROR: Unknown model name. Please provide a valid model.")
        return {"error": "Unknown model name. Please provide a valid model."}

    # set messages for the llm
    messages = [
        ("system", "Today's date is {date}"),
        ("human", "{input_prompt_text}")
    ]

    # set parameters for running the llm
    invoke_params = {
        "input_prompt_text": input_prompt_text,
        "date": date.today().isoformat()
    }

    prompt_template = ChatPromptTemplate.from_messages(messages)

    max_retries = 20  # Reduced number of retries since we're waiting longer
    
    if input_model_name == "sonar-deep-research":
        retry_delay = 60  # 60 seconds for 5 requests/minute rate limit
    else:
        retry_delay = 10  # Initial delay in seconds for other models
        backoff_factor = 2  # Exponential backoff factor for other models

    for attempt in range(max_retries):
        print("Top of for loop: max_retries=", max_retries, " attempt=", attempt, " retry_delay=", retry_delay)
        try:
            if input_tool1:
                print("running input_tool1: ", input_tool1)
                
                if input_tool1 == "openai_web_search":  
                    print("Using OpenAI web search tool")
                elif input_tool1 == "brave_jina":
                    tools = [
                        Tool(
                            name="scrape_webpage_content",
                            func=scrape_webpage_content,
                            description="Use this tool to scrape content from a webpage. Input should be the URL of the web page that you want to scrape. Output is the content of the page."
                        ),
                        Tool(
                            name="search_internet",
                            func=search_internet,
                            description="Use this tool to search the internet. Input should be the search query. Output is a list of search results (Webpage titles and URLs) based on the query. Usually this is followed by a tool_call for scrape_webpage_content."
                        )
                    ]

                    prompt_1 = ChatPromptTemplate.from_messages(
                        [
                            ("system", "You are a helpful assistant"),
                            ("human", "{input}"),
                            ("placeholder", "{agent_scratchpad}"),
                        ]
                    )

                    agent = create_tool_calling_agent(llm=chat_model, tools=tools, prompt=prompt_1)
                    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
                    response = agent_executor.invoke({"input": input_prompt_text})
                    if isinstance(response, dict) and response.get("response_content", {}).get("error"):
                        error_message = response["response_content"]["error"]
                        print(f"PIE_AGENT_ERROR: {error_message}. Retrying... (Attempt {attempt + 1}/{max_retries})")
                        raise Exception(error_message)
                    else:
                        print("PIE_AGENT_RESPONSE: ", response["output"])
                        attempt = 1 # reset attempt since this succeeded
                        return response["output"]
            else:
                chain = prompt_template | chat_model
                response = chain.invoke(invoke_params)
                if isinstance(response, dict) and response.get("response_content", {}).get("error"):
                    error_message = response["response_content"]["error"]
                    print(f"PIE_COMPLETION_ERROR: {error_message}. Retrying... (Attempt {attempt + 1}/{max_retries})")
                    raise Exception(error_message)
                else:
                    print("PIE_COMPLETION_RESPONSE: ", response)
                    return response
        except Exception as e:
            print("Rory Exception: ", e)
            if attempt < max_retries - 1:
                if input_model_name == "sonar-deep-research":
                    print(f"Rate limit detected for sonar-deep-research. Waiting 65 seconds before retry... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                else:
                    print(f"Rate limit or error detected. Retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= backoff_factor  # Increase delay only for non-sonar-deep-research models
            else:
                print("Max retries reached. Unable to complete the request.")
                return {"error": "Rate limit exceeded or error detected. Please try again later."} 

async def send_post_callback_v1(response_content: str, i_tokens: int, o_tokens: int, o_r_tokens: int, request_data: PieRequest) -> dict:
    # Use test URL if bubble_test is True, otherwise use live URL
    bubble_app_url = os.getenv("SYNSONA_BUBBLE_URL_TEST") if request_data.input_json.get("bubble_test") else os.getenv("SYNSONA_BUBBLE_URL_LIVE")

    print("Attempting to send post request (step=", request_data.step_id, ", app=", bubble_app_url)

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

    timeout = httpx.Timeout(60.0)  # seconds
    max_retries = 30

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(bubble_app_url, json=payload, headers=headers)
                response.raise_for_status()
                print("POST to bubble successful (", request_data.step_id, ") - Payload: ", payload)
                return
        except httpx.ConnectTimeout:
            print(f"ConnectTimeout ({request_data.step_id}): Unable to reach {bubble_app_url}. Retrying... (Attempt {attempt + 1}/{max_retries})")
        except httpx.HTTPStatusError as e:
            print(f"HTTPStatusError: {e.response.status_code} - {e.response.text}")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

    print("Max retries reached. Unable to send POST request.")
    return {"error": "Failed to send POST request after retries."}

async def process_request_async_v1(request_data: PieRequest) -> dict:
    print("Starting process_request_async")

    input_tokens = 0
    output_tokens = 0

    print("bpstep_id is generic: ", request_data.bpstep_id)
    response = await asyncio.to_thread(run_bpstep_generic, request_data)

    # Normalize the output content
    if isinstance(response, dict):
        print("res dict: ", response)
        normalized_response = response.get("content")
        usage = response.get("usage_metadata", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    else:
        print("res str: ", response)

    if hasattr(response, 'content'):  # Check if 'response' has 'content' attribute
        normalized_response = response.content
    else:
        normalized_response = response

    await send_post_callback_v1(normalized_response, input_tokens, output_tokens, -1, request_data)

    return

def process_request(request_data: PieRequest) -> dict:
    print("Starting process_request")
    asyncio.create_task(process_request_async_v1(request_data))
    return {"reciept_confirmed": request_data.step_id}