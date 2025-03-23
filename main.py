from fastapi import FastAPI, Query
from pydantic import BaseModel

app = FastAPI()

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