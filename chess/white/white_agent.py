# ──────────────────────────────────────────────
# 1. white_agent_sse.py
# ──────────────────────────────────────────────
"""White Chess Agent (SSE transport). Start with:
    uvicorn white_agent_sse:mcp --port 5001 --reload
"""
import os
import chess
from mcp.server.fastmcp import FastMCP
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from otel.otel import configure_telemetry
from dotenv import load_dotenv
load_dotenv()


SERVICE_VERSION = "1.0.1"

instruments = configure_telemetry("White", SERVICE_VERSION)
meter = instruments["meter"]
tracer = instruments["tracer"]
log = instruments["logger"]

MAX_NUMBER_OF_RETRIES = 5

AZURE_OPENAI_MODEL = "gpt-4.1" # ["gpt-4o", "gpt-4o-mini", "o4-mini", "gpt-4.1-mini", "gpt-4.1", "o3-mini"]
AZURE_OPENAI_DEPLOYMENT = "agentsobs360-gpt-4.1"
AZURE_OPENAI_API_VERSION = "2025-01-01-preview" 


mcp = FastMCP(name="White Chess Agent",
              description="White chess agent using SSE transport",
              base_url="http://localhost:8000",
              host="0.0.0.0",
              describe_all_responses=True,  # Include all possible response schemas
              describe_full_response_schema=True)  # Include full JSON schema in descriptions)

def initiate_ai_agent():
    with tracer.start_as_current_span("init_agent") as span:
        
        span.set_attribute("azure_endpoint", os.getenv("AZURE_OPENAI_ENDPOINT"))
        span.set_attribute("azure_deployment", AZURE_OPENAI_DEPLOYMENT)
        span.set_attribute("azure_openai_model", AZURE_OPENAI_MODEL)
        span.set_attribute("azure_openai_api_version", AZURE_OPENAI_API_VERSION)
        
        client = AzureOpenAIChatCompletionClient(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
            model=AZURE_OPENAI_MODEL,
            api_version=AZURE_OPENAI_API_VERSION     
        )
   
        agent = AssistantAgent(
            name="white_player",
            model_client=client,
            description="""You are a chess player, playing with WHITE pieces.
                        Before you decide about a next move, you must analyze the current 
                        board state and provide a legal best move in UCI notation. 
                        Provide LEGAL MOVES in UCI notation only.
                        Double check and reason about the selected move before sending it. 
                        Your goal is to win the game.""",
            system_message="""You are world renowned chess grandmaster. You play WHITE. 
            Respond only with one legal UCI move (e.g. e2e4) for the given FEN. 
            You must output exactly ONE move in Universal Chess Interface (UCI) format:
                • four characters like e2e4, or
                • five if promotion, e.g. e7e8q
                No capture symbol (x), no checks (+/#), no words. Output ONLY the move.
            Double check the selected move is a valid and legal given current FEN!
            Don't make stupid moves! 
            Follow those basic rules:
                Prevents the most common blunder (self-check).
                Avoids pointless sacrifices.
                Stops discovered checks/loss of queen.
                Reduces illegal “through-piece” moves.
                Eliminates illegal backward-pawn or straight captures.
                Your move must remove any check to your own king. If not, try again.
                Reason your move choice.
        """)

    return agent

@mcp.tool(
    name="move",
    description="Return a legal WHITE move in UCI for the provided FEN.",
)
async def move_tool(fen: str):
    """Return one legal white move (UCI)."""
    log.info("[WhiteAgent] Received FEN %s", fen)
    
    with tracer.start_as_current_span("make_move") as span:
        span.set_attribute("current_player", "white")
        #span.set_attribute("azure_openai_model", azure_openai_model)
        #span.set_attribute("azure_openai_deployment", azure_openai_deployment)
        #span.set_attribute("azure_openai_api_version", azure_openai_api_version)
        span.set_attribute("FEN", fen)
        
        agent = initiate_ai_agent()

        # 1 ─ Build a fresh board from the FEN
        try:
            board = chess.Board(fen)
        except ValueError as e:
            log.error("[WhiteAgent] Invalid FEN: %s", e)
            return {"error": f"Invalid FEN: {e}"}

        if not board.turn:  # False → Black to move
            log.error("[WhiteAgent] It's not white's turn.")
            return {"error": "It's not white's turn in this position"}
        
        
        with tracer.start_as_current_span("list_legal_moves") as span:
            # 2 ─ Enumerate all legal moves
            legal_uci = [m.uci() for m in board.legal_moves]
            if not legal_uci:  # mate / stalemate
                log.error("[WhiteAgent] No legal moves available. Mate or stalemate. Game over.")
                return {"error": "no legal moves"}
            span.set_attribute("legal_moves:", legal_uci)

        with tracer.start_as_current_span("run_agent_for_next_move") as span:
            
            prompt = (
            f"You are playing with WHITE pieces. Current is FEN: {fen}\n"
            "Choose ONE BEST move from this list and output it. Reason your choice.\n"
            + ", ".join(legal_uci)
            )
            span.set_attribute("prompt", prompt)
        
            # 3 ─ Up to MAX_NUMBER_OF_RETRIES attempts to get a legal reply
            for _ in range(MAX_NUMBER_OF_RETRIES):
                resp = await agent.run(task=prompt)
                uci = resp.messages[-1].content.strip().split()[0].lower()
                span.set_attribute("response:", resp.messages[-1].content)
                span.set_attribute("uci:", uci)

                if uci in legal_uci:
                    log.info("[WhiteAgent] Accepted move %s", uci)
                    span.set_attribute(f"Accepted move: {uci}", uci)
                    return {"uci": uci}

                # feedback for retry
                prompt = (
                    f"That move:{uci} is illegal or not in the valid moves list.\n"
                    "Pick ONE move from: " + ", ".join(legal_uci)
                )
                span.set_attribute("feedback for retry", prompt)

        # 4 ─ Give up after MAX_NUMBER_OF_RETRIES bad tries
        log.error("[WhiteAgent] Too many illegal replies.")
        return {"error": "illegal move (max retries exceeded)"}

if __name__ == "__main__":
    log.info("Starting White Player Agent...")
    mcp.run(transport='sse')
