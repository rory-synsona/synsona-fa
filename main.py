from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from docs_api import DocsRequest, generate_docs
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
    expected_token = os.getenv('SYNSONA_TOKEN')

    if token == expected_token:
        if request_data.bpstep_id:
            print("Headers: ", http_request.headers)
            print("Client: ", http_request.client.host if http_request.client else "No client info")
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

# Mount static files to /static path (after API endpoint definition)
app.mount("/static", StaticFiles(directory="public", html=True), name="public")

@app.post("/generate_docs")
async def generate_docs_endpoint(request_data: DocsRequest, http_request: Request):
    auth_header = http_request.headers.get("Authorization")
    
    if (auth_header is None or not auth_header.startswith("Bearer ")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.split(" ")[1]
    expected_token = os.getenv('SYNSONA_TOKEN')

    if token == expected_token:
        return await generate_docs(request_data, http_request)
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")

# Tool to scrape a website
def scrape_webpage_content(url: str) -> str:
    request_url = "https://r.jina.ai/" + url
    headers = {
        "Authorization": f"Bearer {os.getenv('JINA_API_KEY')}",
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
    input_bubble_test = input_json_dict.get("bubble_test", False)
    input_tool1 = input_json_dict.get("tool1")
    input_model_response_format = input_json_dict.get("model_response_format")
    
    print("run_bpstep_generic: ", input_json_dict)
    
    if not input_model_name or not isinstance(input_model_name, str):
        return {"error": "Model name must be a valid string"}

    # Prepare model kwargs
    model_kwargs = {
        "top_p": float(input_model_top_p) if input_model_top_p is not None else 1.0,
        "temperature": float(input_model_temp) if input_model_temp is not None else 0.7,
        "response_format": input_model_response_format if input_model_response_format else None
    }

    try:
        if input_model_name in ["gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"]:
            print("Using OpenAI model: ", input_model_name)
            chat_model = ChatOpenAI(
                model=input_model_name,
                temperature=model_kwargs["temperature"],
                top_p=model_kwargs["top_p"],
                model_kwargs={"response_format": model_kwargs["response_format"]} if model_kwargs["response_format"] else {}
            )
        elif input_model_name in ["sonar", "sonar-pro", "sonar-deep-research", "sonar-reasoning"]:
            from datetime import datetime, timedelta
            today = datetime.now()
            six_months_ago = (today - timedelta(days=180)).strftime('%B 1, %Y')
            print("Using Sonar model: ", input_model_name)
            chat_model = ChatPerplexity(
                model=input_model_name,
                temperature=model_kwargs["temperature"],
                timeout=60,
                model_kwargs={
                    "web_search_options": {
                        "search_context_size": "medium",
                        "search_after_date_filter": six_months_ago
                    }
                }
            )
        elif input_model_name in ["o4-mini", "o3", "o3-deep-research", "o4-mini-deep-research"]:
            print("Using OpenAI reasoning model: ", input_model_name)
            chat_model = ChatOpenAI(
                model=input_model_name,
                reasoning_effort="medium",
                use_responses_api=True
            )
        elif input_model_name in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-pro"]:
            print("Using Google model: ", input_model_name)
            chat_model = ChatGoogleGenerativeAI(
                model=input_model_name,
                temperature=model_kwargs["temperature"],
                top_p=model_kwargs["top_p"]
            )
        elif input_model_name in [
            "claude-3-5-haiku-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-7-sonnet-latest",
            "claude-sonnet-4-0",
            "claude-opus-4-0"
        ]:
            print("Using Anthropic model: ", input_model_name)
            chat_model = ChatAnthropic(
                model_name=input_model_name,
                temperature=model_kwargs["temperature"],
                timeout=60,
                stop=None
            )
        else:
            return {"error": "Unknown model name. Please provide a valid model."}
    except Exception as e:
        return {"error": f"Error initializing model: {str(e)}"}

    messages = [
        ("system", "Today's date is {date}"),
        ("human", "{input_prompt_text}")
    ]
    invoke_params = {
        "input_prompt_text": input_prompt_text,
        "date": date.today().isoformat()
    }
    prompt_template = ChatPromptTemplate.from_messages(messages)
    max_retries = 20
    retry_delay = 60 if input_model_name == "sonar-deep-research" else 10
    backoff_factor = 2

    for attempt in range(max_retries):
        print(f"Attempt {attempt + 1}/{max_retries}, delay: {retry_delay}s")
        try:
            if input_tool1:
                print("running input_tool1: ", input_tool1)
                if input_tool1 == "openai_web_search":
                    print("Using OpenAI web search tool")
                    return {"error": "OpenAI web search not implemented"}
                elif input_tool1 == "brave_jina":
                    tools = [
                        Tool(
                            name="scrape_webpage_content",
                            func=scrape_webpage_content,
                            description="Use this tool to scrape content from a webpage."
                        ),
                        Tool(
                            name="search_internet",
                            func=search_internet,
                            description="Use this tool to search the internet."
                        )
                    ]
                    prompt_1 = ChatPromptTemplate.from_messages([
                        ("system", "You are a helpful assistant"),
                        ("human", "{input}"),
                        ("placeholder", "{agent_scratchpad}")
                    ])
                    agent = create_tool_calling_agent(llm=chat_model, tools=tools, prompt=prompt_1)
                    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
                    response = agent_executor.invoke({"input": input_prompt_text})
                    return {"content": str(response.get("output", ""))}
            else:
                chain = prompt_template | chat_model
                response = chain.invoke(invoke_params)
                print("PIE_COMPLETION_RESPONSE raw: ", response)
                print("Response type:", type(response))
                print("Response attributes:", dir(response))
                
                # Extract response details based on type
                if isinstance(response, dict):
                    result = {
                        "content": str(response.get("text", response.get("content", ""))),
                        "citations": response.get("citations", []),
                        "search_results": response.get("search_results", [])
                    }
                    # Pass through usage_metadata and response_metadata if present
                    if "usage_metadata" in response:
                        result["usage_metadata"] = response["usage_metadata"]
                    if "response_metadata" in response:
                        result["response_metadata"] = response["response_metadata"]
                    print("Extracted dict result:", result)
                    return result
                elif hasattr(response, 'additional_kwargs'):  # Handle ChatPerplexity response
                    content = str(response.content)
                    citations = response.additional_kwargs.get('citations', [])
                    search_results = response.additional_kwargs.get('search_results', [])
                    result = {
                        "content": content,
                        "citations": citations,
                        "search_results": search_results
                    }
                    # Pass through usage_metadata and response_metadata if present
                    if hasattr(response, 'usage_metadata'):
                        result["usage_metadata"] = getattr(response, 'usage_metadata', {})
                    if hasattr(response, 'response_metadata'):
                        result["response_metadata"] = getattr(response, 'response_metadata', {})
                    print("Extracted Perplexity result:", result)
                    return result
                else:
                    print("Fallback: converting response to string")
                    return {"content": str(response)}
        except Exception as e:
            print(f"Error: {str(e)}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                if input_model_name != "sonar-deep-research":
                    retry_delay *= backoff_factor
            else:
                return {"error": f"Failed after {max_retries} attempts: {str(e)}"}

    return {"error": "Unexpected error occurred"}
async def send_post_callback_v1(response_content: str, i_tokens: int, o_tokens: int, o_r_tokens: int, request_data: PieRequest, citation_tokens=None, num_search_queries=None) -> dict:
    # Use test URL if bubble_test is True, otherwise use live URL
    bubble_app_url = os.getenv("SYNSONA_BUBBLE_URL_TEST") if request_data.input_json.get("bubble_test") else os.getenv("SYNSONA_BUBBLE_URL_LIVE")

    if not bubble_app_url:
        return {"error": "Missing Bubble URL configuration"}

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
    if citation_tokens is not None:
        payload["citation_tokens"] = citation_tokens
    if num_search_queries is not None:
        payload["num_search_queries"] = num_search_queries
    headers = {"Content-Type": "application/json"}

    timeout = httpx.Timeout(60.0)  # seconds
    max_retries = 30

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(bubble_app_url, json=payload, headers=headers)
                response.raise_for_status()
                print("POST to bubble successful (", request_data.step_id, ") - Payload: ", payload)
                return {"status": "success", "step_id": request_data.step_id}
        except httpx.ConnectTimeout:
            print(f"ConnectTimeout ({request_data.step_id}): Unable to reach {bubble_app_url}. Retrying... (Attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                return {"error": f"Connection timeout after {max_retries} attempts"}
        except httpx.HTTPStatusError as e:
            print(f"HTTPStatusError: {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP error {e.response.status_code}"}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {"error": str(e)}

    return {"error": "Failed to send POST request after retries."}

async def process_request_async_v1(request_data: PieRequest) -> dict:
    print("Starting process_request_async")

    input_tokens = 0
    output_tokens = 0

    print("bpstep_id is generic: ", request_data.bpstep_id)
    response = await asyncio.to_thread(run_bpstep_generic, request_data)
    print("Raw response from model:", response)
    
    # Normalize the output content
    if isinstance(response, dict):
        print("Response is dict with keys:", response.keys())
        content = response.get("content", "")
        
        # Handle citations if they exist
        citations = response.get("citations", [])
        if citations:
            print("Found citations:", citations)
            content = f"{content}\n<citations>{chr(10)}{chr(10).join(citations)}</citations>"
            
        # Handle search results if they exist
        search_results = response.get("search_results", [])
        if search_results:
            print("Found search_results:", search_results)
            results_str = json.dumps(search_results, indent=2)
            content = f"{content}\n<search_results>{chr(10)}{results_str}</search_results>"
        
        print("Final normalized content:", content)    
        normalized_response = str(content)
        # --- Token extraction logic ---
        usage = response.get("usage_metadata", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        o_r_tokens = -1
        citation_tokens = None
        num_search_queries = None
        # Also check for response_metadata['token_usage']
        response_metadata = response.get("response_metadata", {})
        token_usage = response_metadata.get("token_usage", {})
        if token_usage:
            input_tokens = token_usage.get("prompt_tokens", input_tokens)
            output_tokens = token_usage.get("completion_tokens", output_tokens)
            o_r_tokens = token_usage.get("completion_tokens_details", {}).get("reasoning_tokens", -1)
        # --- NEW: Check for top-level 'usage' field ---
        usage_top = response.get("usage", {})
        if usage_top:
            input_tokens = usage_top.get("prompt_tokens", input_tokens)
            output_tokens = usage_top.get("completion_tokens", output_tokens)
            o_r_tokens = usage_top.get("reasoning_tokens", o_r_tokens)
            citation_tokens = usage_top.get("citation_tokens")
            num_search_queries = usage_top.get("num_search_queries")
    elif hasattr(response, 'content'):
        print("Response is object with content attribute")
        content = response.content
        
        # Check if the response object has citations
        citations = getattr(response, 'citations', [])
        if citations:
            print("Found citations from object:", citations)
            content = f"{content}\n<citations>{chr(10)}{chr(10).join(citations)}</citations>"
            
        # Check if the response object has search results
        search_results = getattr(response, 'search_results', [])
        if search_results:
            print("Found search_results from object:", search_results)
            results_str = json.dumps(search_results, indent=2)
            content = f"{content}\n<search_results>{chr(10)}{results_str}</search_results>"
            
        print("Final normalized content from object:", content)
        normalized_response = str(content)
        # --- Token extraction logic for object ---
        usage = getattr(response, 'usage_metadata', {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        o_r_tokens = -1
        citation_tokens = None
        num_search_queries = None
        response_metadata = getattr(response, 'response_metadata', {})
        token_usage = response_metadata.get("token_usage", {})
        if token_usage:
            input_tokens = token_usage.get("prompt_tokens", input_tokens)
            output_tokens = token_usage.get("completion_tokens", output_tokens)
            o_r_tokens = token_usage.get("completion_tokens_details", {}).get("reasoning_tokens", -1)
        # --- NEW: Check for top-level 'usage' field ---
        usage_top = getattr(response, 'usage', {})
        if usage_top:
            input_tokens = usage_top.get("prompt_tokens", input_tokens)
            output_tokens = usage_top.get("completion_tokens", output_tokens)
            o_r_tokens = usage_top.get("reasoning_tokens", o_r_tokens)
            citation_tokens = usage_top.get("citation_tokens")
            num_search_queries = usage_top.get("num_search_queries")
    else:
        print("Response is neither dict nor has content attribute")
        normalized_response = str(response)
        input_tokens = 0
        output_tokens = 0
        o_r_tokens = -1
        citation_tokens = None
        num_search_queries = None

    print("Final response being sent to callback:", normalized_response)
    await send_post_callback_v1(normalized_response, input_tokens, output_tokens, o_r_tokens, request_data, citation_tokens, num_search_queries)

    return {"status": "success", "step_id": request_data.step_id}

def process_request(request_data: PieRequest) -> dict:
    print("Starting process_request")
    asyncio.create_task(process_request_async_v1(request_data))
    return {"reciept_confirmed": request_data.step_id}