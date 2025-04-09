from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import asyncio
import requests
import openai
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

# Tool to call OpenAI with web_search_preview
# def call_web_search(query: str) -> str:
#     """Call OpenAI with web_search_preview tool enabled."""
#     response = openai.ChatCompletion.create(
#         model="gpt-4o",
#         messages=[{"role": "user", "content": query}],
#         tools=[{"type": "web_search_preview"}]
#     )
#     return response.choices[0].message["content"]


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
    
    # Get EXPECTED variables from input_json in request
    input_json_dict = request_data.input_json
    input_prompt_text = input_json_dict.get("prompt_text")
    input_model_name = input_json_dict.get("model_name")
    input_model_temp = input_json_dict.get("model_temp")
    input_model_top_p = input_json_dict.get("model_top_p")

    input_tool1 = input_json_dict.get("tool1")

    # input_target_url = input_json_dict.get("target_url")
    # input_target_company = input_json_dict.get("target_company")

    print("run_bpstep_Triggers: ", input_json_dict)

    # Prepare model kwargs
    model_kwargs = {
        "top_p": input_model_top_p,
        "temperature": input_model_temp, 
    }

    if input_model_name in ["gpt-4o-mini", "gpt-4o"]:
        print("Using OpenAI model: ", input_model_name)
        chat_model = ChatOpenAI(
            model=input_model_name,  # Specify the model name
            temperature=input_model_temp,
            top_p=input_model_top_p,
            # model_kwargs=model_kwargs,  # Pass model kwargs
        )
    elif input_model_name in ["sonar", "sonar-pro", "sonar-deep-research"]:
        print("Using Sonar model: ", input_model_name)
        chat_model = ChatPerplexity(
            model=input_model_name,
            temperature=input_model_temp,
            top_p=input_model_top_p,
            # model_kwargs=model_kwargs,  # Pass model kwargs
        )
    elif input_model_name in ["o3-mini", "o3"]:
        print("Using OpenAI reasoning model: ", input_model_name)
        chat_model = ChatOpenAI(
            model=input_model_name,
            # temperature=input_model_temp,
            # top_p=input_model_top_p,
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
            # model_kwargs=model_kwargs,  # Pass model kwargs
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
            # model_kwargs=model_kwargs,  # Pass model kwargs
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

    # invoke_params = {
    #     "input_prompt_text": input_prompt_text,
    #     "date": date.today().isoformat(),
    #     "input_target_url": input_target_url,
    #     "input_target_company": input_target_company
    # }

    # Conditionally add invoke params based on input_json
    # if input_target_url:
    #    invoke_params["input_target_url"] = input_target_url

    if input_tool1:
        print("running input_tool1: ", input_tool1)
        
        # 🧠 Step 3: Create the agent with tools
        if input_tool1 == "openai_web_search":  
            print("Using OpenAI web search tool")
            
            # prompt_1 = ChatPromptTemplate.from_messages(
            #     [
            #         ("system", "You are a helpful assistant"),
            #         ("human", "{input}"),
            #         # Placeholders fill up a **list** of messages
            #         ("placeholder", "{agent_scratchpad}"),
            #     ]
            # )

            # agent = create_tool_calling_agent(llm=chat_model, tools=[{"type": "web_search_preview"}], prompt=prompt_1)
            # agent_executor = AgentExecutor(agent=agent, tools=[{"type": "web_search_preview"}], verbose=True)
            # response = agent_executor.invoke({"input": input_prompt_text})
            # return response["output"]

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
                    # Placeholders fill up a **list** of messages
                    ("placeholder", "{agent_scratchpad}"),
                ]
            )

            agent = create_tool_calling_agent(llm=chat_model, tools=tools, prompt=prompt_1)
            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
            response = agent_executor.invoke({"input": input_prompt_text})
            print("OUT111: ", response["output"])
            return response["output"]
    else:
        chain = prompt_template | chat_model
        response = chain.invoke(invoke_params)
        print("RES111: ", response)
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

    # Use the mappings to determine the action based on bpstep_id
    # bpstep = BPSTEP_MAPPINGS.get(request_data.bpstep_id)

    # if bpstep == "Company triggers":
    #     print("bpstep_id is 'Company triggers' 1742963840776x872202725975654400")

    #     response = await asyncio.to_thread(run_bpstep_Triggers, request_data, TRIGGERS_TGT_CISO_1)

    #     # Extract values from usage_metadata
    #     input_tokens = response.usage_metadata['input_tokens']
    #     output_tokens = response.usage_metadata['output_tokens']
    #     # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

    #     await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)
    
    # elif bpstep == "Industry triggers":
    #     print("bpstep_id is 'Industry triggers' 1743642197570x161409188642422800")

    #     response = await asyncio.to_thread(run_bpstep_Triggers, request_data, TRIGGERS_IND_CISO_1)

    #     # Extract values from usage_metadata
    #     input_tokens = response.usage_metadata['input_tokens']
    #     output_tokens = response.usage_metadata['output_tokens']
    #     # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

    #     await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    # elif bpstep == "Angles persona 1":
    #     print("bpstep_id is Angles persona 1 - 1743007240371x889852377243582500")
    #     response = await asyncio.to_thread(run_bpstep_Angles1, request_data)

    #     # Extract values from usage_metadata
    #     input_tokens = response.usage_metadata['input_tokens']
    #     output_tokens = response.usage_metadata['output_tokens']
    #     # output_reasoning_tokens = response.usage_metadata['output_reasoning_tokens']

    #     await send_post_callback_v1(response.content, input_tokens, output_tokens, -1, request_data)

    # elif request_data.bpstep_id:
        
    # else:
    #     print("bpstep_id was empty")

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
            print("Client: ", http_request.client.host)
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")