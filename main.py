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
    input_triggers = input_json_dict.get("triggers")
    input_target_company = input_json_dict.get("target_company")

    print("run_bpstep_Angles1: ", input_json_dict)
    print("input_triggers: ", input_triggers)   
    print("input_target_company: ", input_target_company)

    # messages = [("system", "Objective: Provide a summary of all of the TRIGGERS in 100 words or less"), ("human", "TRIGGERS for {input_target_company}: {input_triggers}")]

    messages = [("system",
         """ROLE: You are a Sales Development Representative for 'Phriendly Phishing'. Phriendly Phishing is a B2B company that specializes in employee security awareness, phishing simulation training and phishing detection and remediation tools. Primarily sells to companies within the Australian and New Zealand markets.

        Phriendly Phishing Value proposition for {input_target_company}:
        - Engaging Training: Offers security awareness and phishing simulation training designed to drive long-lasting behavioral change among their employees (Decrease in click-through rates on phishing emails, Decreased phishing risk within an organization, Increase of reported emails by employees of a company)
        - Tailored Learning: Provides customized learning experiences tailored to the unique needs of each department within their organization (High 85percent+ completion rates of security awareness training within an organisation)
        - Localized Content: Features content specifically localized for Australian and New Zealand audiences, resulting in higher employee training completion rates compared to generic alternatives.
        - Phish focus: Empowers organizations with rapid threat detection for all of their employee inboxes, one-click remediation, and phishing simulations, enhancing email security to minimize risks efficiently and effectively.
        - Managed service: Dedicated Managed Service Specialists deliver tailored cyber security solutions, overseeing planning, implementation, training, communications, campaign delivery, analytics, and check-ins to enhance employee awareness, engagement, and defense against evolving cyber threats.

        TARGET PERSONA at {input_target_company}: Chief Information Security Officer (CISO) at {input_target_company}
        1. Pain points:
            - Increasing volume and sophistication of cyber threats
            - Human error is a major cyber risk
            - Regulatory compliance requirements (GDPR, HIPAA, SOC 2, ISO etc)
            - Board pressure to reduce cyber risk while managing risk
        2. Motivations:
            - Reduce human risk as a cybersecurity vulnerability
            - Ensure compliance with industry regulations
            - Strengthen security culture across the organisation
            - Demonstrate proactive security measures to leadership and auditors
            - Could lose their job/reputation in the event of a major cyber breach
            - Minimise business disruption from cyber incidents
        
        OBJECTIVE:
        The user will provide you a list of TRIGGERS for {input_target_company}. For each TRIGGER, generate an ANGLE. If you don't believe the TRIGGER can be used to generate an effective ANGLE explain your reasoning and continue with the next trigger.

        Your response must be formatted as a JSON list of ANGLES SORTED by decending relevance and likelihood to succeed with 1 being the lowest and 5 being the highest.
       
        OUTPUT TEMPLATE:  Use this ANGLES JSON template and complete for all TRIGGERS provided.

        [
            {{
                "ANGLE for CISO": "A successful ANGLE resonates with the CISO at {input_target_company} by connecting the TRIGGER to their motivations or pain points and makes a clear connection to Phriendly Phishing's value propostion by explaining how it can help solve a problem. Be concise, direct, clear, and avoid AI sounding words or terms.",
                "Score of ANGLE": "Rate the ANGLE from 1-5 based on relevance and likelihood to succeed. 1 being the lowest and 5 being the highest.",
                "Trigger": "Summary as provided exactly in TRIGGER",
                "URL": "Exact URL of the source for the TRIGGER",
                "Risk to company": "Explain the cyber security risk indicated by the TRIGGER and what it means for {input_target_company}'s operational metrics, financials, reputation, and compliance",
                "Relevance to CISO": "Explain why this angle is relevant the CISO at {input_target_company}. What are they likely doing or thinking about in response to this TRIGGER?"
            }},
            {{
            ...
            }}
        ]

        Your response must only include the JSON: Exclude introduction and concluding summary."""),
        ("human", "TRIGGERS for {input_target_company}: {input_triggers}")
    ]
    prompt_template = ChatPromptTemplate.from_messages(messages)
    # chat = init_chat_model("gpt-4o-mini", model_provider="openai")
    chat = init_chat_model("o3-mini", model_provider="openai")
    chain = prompt_template | chat
    response = chain.invoke({"input_target_company": input_target_company, "input_triggers": input_triggers})
    return response

def run_bpstep_Triggers(request_data: PieRequest) -> dict:
    input_json_dict = request_data.get_input_json_dict()
    input_target_url = input_json_dict.get("target_url")
    print("run_bpstep_Triggers: ", input_json_dict, " => ", input_target_url)

    # messages = [("system", "You are a friendly assistant. What is the target URL?"), ("human", "Target url = {input_target_url}")]

    messages = [("system",
        """ROLE: You are a research assistant for 'Phriendly Phishing' (https://www.phriendlyphishing.com). Phriendly Phishing is a B2B company that specializes in employee security awareness, phishing simulation training and phishing detection and remediation tools. Primarily sells to companies within the Australian and New Zealand markets.

        Phriendly Phishing Value proposition for {input_target_url}:
        - Engaging Training: Offers security awareness and phishing simulation training designed to drive long-lasting behavioral change among their employees (Decrease in click-through rates on phishing emails, Decreased phishing risk within an organization, Increase of reported emails by employees of a company)
        - Tailored Learning: Provides customized learning experiences tailored to the unique needs of each department within their organization (High 85percent+ completion rates of security awareness training within an organisation)
        - Localized Content: Features content specifically localized for Australian and New Zealand audiences, resulting in higher employee training completion rates compared to generic alternatives.
        - Phish focus: Empowers organizations with rapid threat detection for all of their employee inboxes, one-click remediation, and phishing simulations, enhancing email security to minimize risks efficiently and effectively.
        - Managed service: Dedicated Managed Service Specialists deliver tailored cyber security solutions, overseeing planning, implementation, training, communications, campaign delivery, analytics, and check-ins to enhance employee awareness, engagement, and defense against evolving cyber threats.

        OBJECTIVE: The user will assign you a TARGET account. You are to thoroughly research the company to find relevant triggers that will lead to opportunities for engagement and generate a JSON list of triggers.
            
        RELEVANT TOPICS: Your research should focus on topics that resonate with Phriendly Phishing's value proposition. These include, but are not limited to:
        1. cyber breaches
        2. it security investments
        3. phishing attacks
        4. cyber attacks
        5. ransomware
        6. Changes in the TARGET account's security leadership (Chief Information Security Officer or CISO)
        7. Changes to relevant regulations to the TARGET like APRA, ISO Certifications, Australian/New Zealand Government guidelines

        RESEARCH SOURCES: Your research about the TARGET account MUST include these sources:
        1. News about TARGET account (less than 12 months old)
        2. News about TARGET account's top competitors (less than 12 months old)
        3. News about TARGET account's sub-industry (less than 12 months old)
        4. News about companies in Australia or New Zealand (less than 12 months old)
        5. Most recent Directors' Report
        6. Most recent Annual Financial Report
        7. Most recent Half-Year Financial Report
            
        OUTPUT TEMPLATE: Use this template for each trigger you find:
        
        Ttitle of TRIGGER: Concise title of the trigger
        Date: Publish date of trigger
        URL: Exact URL of the source of this trigger
        Summary: Detailed summary of the trigger with high brevity, intended for a c-level executive, focusing on details (who/what/when/where/why/how), figures, metrics, monitory values, and percentages
        Relevance: Explain why this trigger is relevant to Phriendly Phishing's value propostion
            
        Your response must only include the triggers in plain text. No markdown or JSON. Exclude introduction and concluding text."""),
        ("human", "TARGET account to research: {input_target_url}")
    ]
    prompt_template = ChatPromptTemplate.from_messages(messages)
    chat = ChatPerplexity(model="sonar-deep-research")
    # chat = ChatPerplexity(model="sonar")
    chain = prompt_template | chat
    response = chain.invoke(
        {"input_target_url": input_target_url},
        config={
            "web_search_options": {
                "search_context_size": "high"
            }
        }
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