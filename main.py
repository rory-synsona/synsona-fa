from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

'''
@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}

@app.get("/echo/")
async def echo(value: str = Query(..., description="The value to be echoed")):
    return {"confirmation61": value}
'''

class EchoRequest(BaseModel):
    value: str

@app.post("/echo/")
async def echo(request: EchoRequest):
    return {"confirmation": request.value}