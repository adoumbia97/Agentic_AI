from fastapi import FastAPI
from pydantic import BaseModel
from simple_agents import Agent, Runner
from food_security import food_security_analyst

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[food_security_analyst],
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
