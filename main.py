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

# Import the mappings from mappings.py
from mappings import BPSTEP_MAPPINGS

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

def run_bpstep_Angles1(request_data: PieRequest) -> dict:
    input_json_dict = request_data.get_input_json_dict()
    input_triggers = input_json_dict.get("input_triggers")
    input_target_name = input_json_dict.get("input_target_name")

    print("run_bpstep_Angles1: ", input_json_dict)
    print("input_triggers: ", input_triggers)   
    print("input_target_name: ", input_target_name)

    messages = [("system", "Objective: Provide a summary of all of the TRIGGERS in 100 words or less"), ("human", "TRIGGERS for {input_target_name}: {input_triggers}")]

    # messages = [
    #     ("system",
    #      """ROLE: You are a Sales Development Representative for 'Phriendly Phishing'. Phriendly Phishing specializes in security awareness and phishing simulation training, focusing on the Australian and New Zealand markets.

    #      Phriendly Phishing Value proposition:
    #      - Engaging Training: Offers security awareness and phishing simulation training designed to drive long-lasting behavioral change among employees.
    #      - Tailored Learning: Provides customized learning experiences tailored to the unique needs of each department within your organization.
    #      - Localized Content: Features content specifically localized for Australian and New Zealand audiences, resulting in higher completion rates compared to generic alternatives.
    #      - Secure Data Storage: Ensures all data is stored securely within Australia, eliminating risks associated with overseas storage.

    #     TARGET PERSONA at {input_target_name}: Chief Information Security Officer (CISO) at {input_target_name}
    #     1. Pain points:
    #         - Increasing volume and sophistication of cyber threats
    #         - Human error is a major cyber risk
    #         - Regulatory compliance requirements (GDPR, HIPAA, SOC 2, ISO etc)
    #         - Board pressure to reduce cyber risk while managing risk
    #     2. Motivations:
    #         - Reduce human risk as a cybersecurity vulnerability
    #         - Ensure compliance with industry regulations
    #         - Strengthen security culture across the organisation
    #         - Demonstrate proactive security measures to leadership and auditors
    #         - Could lose their job/reputation in the event of a major cyber breach
    #         - Minimise business disruption from cyber incidents
        
    #     OBJECTIVE:
    #     The user will provide you a list of TRIGGERS for {input_target_name}. You will generate an ANGLE that resonates with the TARGET PERSONA by connecting the TRIGGER to their persona's motivations and pain points in a way that offers value or a solution, and aligns with Phriendly Phishing's value proposition.
       
    #     OUTPUT TEMPLATE: Your response must be formatted as a JSON list, with ANGLES ordered by decending relevance and likelihood to succeed. Use this ANGLES JSON template and complete for all TRIGGERS provided.

    #     [
    #         {{
    #             "Angle for CISO": "Connect the TRIGGER to Phriendly Phishing's value proposition and how it addresses the CISO's pain points and motivations. Be concise, direct, clear, and avoid AI sounding words or terms.",
    #             "Relevance to CISO": "Explain why this angle is relevant the CISO at {input_target_name}. What are they likely doing or thinking about in response to this TRIGGER?",
    #             "Trigger": "Summary as provided exactly in TRIGGER",
    #             "Risk": "Expand on the cyber security risk involved in the TRIGGER and what it means for {input_target_name}'s operational metrics, financials, reputation, and compliance",
    #             "Reference": "TITLE and exact URL of the source for the TRIGGER"
    #         }},
    #         {{
    #         ...
    #         }}
    #     ]

    #     Your response must only include the JSON: Exclude introduction and concluding summary."""),
    #     ("human", "TRIGGERS for {input_target_name}: {input_triggers}")
    # ]
    prompt_template = ChatPromptTemplate.from_messages(messages)
    chat = init_chat_model("gpt-4o-mini", model_provider="openai")
    chain = prompt_template | chat
    response = chain.invoke({"input_target_name": input_target_name, "input_triggers": input_triggers})
    return response

def run_bpstep_Triggers(request_data: PieRequest) -> dict:
    input_json_dict = request_data.get_input_json_dict()
    target_url = input_json_dict.get("target_url")
    print("run_bpstep_Triggers: ", input_json_dict, " => ", target_url)

    messages = [("system", "You are a friendly assistant. What is the target URL?"), ("human", "Target url = {target_url}")]

    # messages = [("system",
    # """ROLE: You are a research assistant for 'Phriendly Phishing' (https://www.phriendlyphishing.com). Phriendly Phishing specializes in security awareness and phishing simulation training. The company offers tailored, automated training solutions that empower organizations to combat cyber threats, including phishing and ransomware. Their value proposition lies in delivering engaging, customizable learning experiences for each department that foster long-lasting behavioral change among employees, thereby reducing the risk of financial and reputational damage from cyber attacks. Phriendly Phishing's content is recognized for being localized and more relevant to Australian and New Zealand audiences, contributing to an increase in completion rates compared to other offerings.
         
    # OBJECTIVE:
    # The user will assign you a target account. You are to thoroughly research the company to find relevant triggers that will lead to opportunities for engagement and generate a JSON list of triggers.
        
    # RELEVANT TOPICS for Phriendly Phishing: Your research should focus on topics that resonate with Phriendly Phishing's value proposition. These include, but are not limited to:
    # 1. cyber breaches
    # 2. it security investments
    # 3. phishing attacks
    # 4. cyber attacks
    # 5. ransomware
    # 6. changes in security leadership (Chief Information Security Officer or CISO)

    # RESEARCH SOURCES: Your search about the target account MUST include the following sources
    # 1. News about the target account
    # 2. News about the target account's top competitors
    # 3. News about the target account's sub-industry 
    # 4. News about companies in Australia or New Zealand
    # 5. News about changes to regulations like APRA, ISO Certifications, Australian/New Zealand Government guidelines around cyber breaches
    # 6. News about new regulations or guidelines around cyber security
    # 7. Review their latest Directors' Report
    # 8. Review their latest Annual Financial Report
    # 9. Review their latest Half-Year Financial Report
        
    # OUTPUT TEMPLATE: Use this template for each trigger you find:
    
    # Trigger #1: Concise title of the trigger
    # Date: Publish date
    # Summary: Detailed summary of the trigger with high brevity, intended for a c-level executive, focusing on details (who/what/when/where/why/how), figures, metrics, monitory values, and percentages
    # Relevance: Explain why this trigger is relevant to Phriendly Phishing
    # Reference: Exact URL of the source of the trigger
        
    # Your response must only include the triggers. Exclude introduction and concluding summary."""),
    # ("human", "Target account to research: {target_url}")]
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

    if bpstep == "Triggers":
        print("bpstep_id is Triggers - 1742963840776x872202725975654400")

        response = await asyncio.to_thread(run_bpstep_Triggers, request_data)

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
            response = process_request(request_data)
            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    else:
        raise HTTPException(status_code=401, detail="Unauthorized")