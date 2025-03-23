from fastapi import FastAPI, Query, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class EchoRequest(BaseModel):
    domain: str
    tid: str
    cid: str

def run_llm(domain: str, tid: str, cid: str) -> dict:
    return 0

def send_post_for_callback(response: str, tid: str) -> dict:
    # url = "https://app.synsona.com/version-test/api/1.1/wf/callback_response"
    url = "https://app.synsona.com/api/1.1/wf/callback_response"
    payload = {
        "response": "response_string_okay",
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
    callback_response = send_post_for_callback(llm_response, tid)

    return {"confirm": tid}

@app.post("/echo/")
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
