from fastapi import FastAPI
from pydantic import BaseModel
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@app.get("/")
async def root():
    return {"message": "Hello functions"}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    result = await Runner.run(agent, input=req.message)
    return ChatResponse(reply=result.final_output)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "my_bot:app",   # module_name:app
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
