# board_orchestrator_sse.py
"""
SSE-based orchestrator for a two-engine chess game:

  • Connects to white_agent_sse.py and black_agent_sse.py via HTTP/SSE
  • Calls their `move` tool alternately, validates the moves,
    maintains a python-chess board, renders a tiny GUI,
    and logs all events.

Requires:
 uv add autogen-agentchat autogen-ext[openai,mcp] python-chess chess-board rich
Run from the root of the repository: python -m mcp_sse.board
"""
import asyncio
import json
import os
import re
import chess
from chessboard import display
from autogen_ext.tools.mcp import McpWorkbench, SseServerParams
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.messages import TextMessage
from otel.otel import configure_telemetry
from pydantic import BaseModel
from dotenv import load_dotenv


load_dotenv()

SERVICE_VERSION = "1.0.1"

instruments = configure_telemetry("Board Service", SERVICE_VERSION)
meter = instruments["meter"]
tracer = instruments["tracer"]
log = instruments["logger"]

# endpoints for SSE agents
WHITE_URL = os.getenv("WHITE_URL", "http://localhost:8001")
BLACK_URL = os.getenv("BLACK_URL", "http://localhost:8002")

# Constants
AZURE_OPENAI_MODEL = os.getenv("AZURE_OPENAI_MODEL")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")

# Validate required environment variables
if not AZURE_OPENAI_API_KEY:
    raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")

# UCI move format regex pattern (4 or 5 characters)
UCI_PATTERN = re.compile(r'^[a-h][1-8][a-h][1-8][qrbn]?$')

#Class for model structired output
class ChessMoveResponse(BaseModel):
    """Structured response for chess moves in UCI format."""
    move: str
    
    class Config:
        extra = "forbid"


def validate_fen(fen: str) -> None:
    """Simple FEN validation - throws exception if invalid."""
    with tracer.start_as_current_span("validate_fen") as span:
        span.set_attribute("fen", fen)
        try:
            chess.Board(fen)
        except ValueError as e:
            raise ValueError(f"Invalid FEN: {e}")

async def init_aoai_client(use_structured_output: bool = False) -> AzureOpenAIChatCompletionClient:
    """
    Unified Azure OpenAI client factory.
    
    Args:
        use_structured_output: If True, configures client for structured JSON output with ChessMoveResponse schema.
                              If False, returns plain text responses.
    """
    with tracer.start_as_current_span("init_aoai_client") as span:
        span.set_attribute("azure_endpoint", AZURE_OPENAI_ENDPOINT)
        span.set_attribute("use_structured_output", use_structured_output)
        
        client_kwargs = {
            "azure_endpoint": AZURE_OPENAI_ENDPOINT,
            "azure_deployment": AZURE_OPENAI_DEPLOYMENT,
            "model": AZURE_OPENAI_MODEL,
            "api_version": AZURE_OPENAI_API_VERSION,
            "api_key": AZURE_OPENAI_API_KEY
        }
        if use_structured_output:
            client_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "chess_move_response",
                    "description": "Chess move in UCI format",
                    "schema": ChessMoveResponse.model_json_schema(),
                    "strict": True
                }
            }
        return AzureOpenAIChatCompletionClient(**client_kwargs)


async def create_board_agent() -> AssistantAgent:
    
    with tracer.start_as_current_span("create_board_agent") as span:
        
        span.set_attribute("azure_endpoint", AZURE_OPENAI_ENDPOINT)
        
        client = await init_aoai_client(use_structured_output=False)
        
        agent = AssistantAgent(
            name="board_agent",
            model_client=client,
            description="""Board manager for a chess game.
                        Maintains a python-chess board, selects the next player to make a move based on the current board state (FEN)""",
            system_message="""
            You are a chess game orchestrator. You are responsible for managing the game state and ensuring that the players take turns making moves.
            Decide which player should make the next move based on the current board state (FEN).
            You will receive a as an input FEN string representing the current state of the chessboard.
            Your task is to determine which player should make the next move based on the current board state.
            You should output the name of the player who should make the next move (either "white" or "black")."""
        )
        return agent

async def run_game() -> None:
    
    MAX_RETRIES_ON_INVALID_MOVE:int = 5
    no_retries:int = 0
    with tracer.start_as_current_span("start_game") as span:
        board = chess.Board()
    
        # initialize UI with the starting FEN
        game_board = display.start(board.fen())
    
        board_agent = await create_board_agent()
        aoai_client = await init_aoai_client(use_structured_output=True)

        while not board.is_game_over():
            #get the current board state
            fen = board.fen()
            # Validate FEN before sending to agents
            validate_fen(fen)
            #check who is the next player
            with tracer.start_as_current_span("get_current_player") as span:
                span.set_attribute("FEN:", fen)
                result =\
                    await board_agent.run(task=f"Decide who should make the next move. \
                                  Output: 'white' or 'black' depending on the current FEN: {fen}",)
                assert isinstance(result.messages[-1], TextMessage)
                current_player = result.messages[-1].content.strip().lower()
                span.set_attribute("current_player:", current_player)
            
            with tracer.start_as_current_span("create_mcp_workbench") as span:
                span.set_attribute("current_player:", current_player)
                
                if current_player == "white":
                    current_wb = McpWorkbench(
                        SseServerParams(url=f"{WHITE_URL}/sse", timeout=90)
                    )
                else:
                    current_wb = McpWorkbench(
                        SseServerParams(url=f"{BLACK_URL}/sse", timeout=90)
                    )
            with tracer.start_as_current_span("request_next_move") as span:
                span.set_attribute("current_player:", current_player)
                span.set_attribute("aoai_client:", aoai_client.model_info)
                async with current_wb:
                    player_agent = AssistantAgent(
                        name=current_player,
                        model_client=aoai_client,
                        description=f"Chess agent for {current_player} player. Decides the next move based on the current board state (FEN).",
                        workbench=current_wb,
                        reflect_on_tool_use=True
                    )
                    next_move = \
                    await player_agent.run(task=f"Select the next move based on the current board state (FEN) : {fen} \
                                   Output the move in exact UCI format as a JSON object with 'move' field containing \
                                   only the 4-5 character UCI notation(e.g., {{'move': 'e2e4'}}).")
                    span.set_attribute("next_move_response:", next_move.messages[-1])
            
                    assert isinstance(next_move.messages[-1], TextMessage)
            
                    # Parse JSON response to extract UCI move
                    try:
                        response_content = next_move.messages[-1].content
                        if isinstance(response_content, str):
                            move_data = json.loads(response_content)
                            uci = move_data.get("move", "").strip().lower()
                        else:
                            uci = response_content
                
                        log.info(f"Next move response: {uci}")
                        # Validate UCI format with regex
                        if not UCI_PATTERN.match(uci):
                            raise ValueError(f"Invalid UCI format: {uci}")
                        span.set_attribute("Next move, uci:", uci)
                    except (json.JSONDecodeError, ValueError, KeyError) as e:
                        log.error(f"Failed to parse move response from {current_player}: {uci} ({e})")
                        if no_retries < MAX_RETRIES_ON_INVALID_MOVE:
                            no_retries += 1
                            log.warning(f"Retrying due to invalid move format ({no_retries}/{MAX_RETRIES_ON_INVALID_MOVE})")
                            continue
                        else:
                            log.error("Too many invalid moves; aborting game.")
                            break
                        
                    no_retries=0
                    log.info(f"Next move is: {uci}")
            
                    with tracer.start_as_current_span("update_board") as span:
                        # validate move
                        try:
                            mv = chess.Move.from_uci(uci)
                            if mv not in board.legal_moves:
                                raise ValueError("illegal move")
                        except Exception as e:
                            log.error(f"Illegal move from {current_player}: {uci} ({e})")
                            break

                        # apply and render
                        board.push(mv)
                        display.update(board.fen(), game_board)
                        log.info(f"Applied move: {uci}")
                        await asyncio.sleep(1)
            
        with tracer.start_as_current_span("game_summary") as span:
            result = board.result()
            reason = ("Checkmate" if board.is_checkmate() else
                    "Stalemate" if board.is_stalemate() else
                    "Insufficient material" if board.is_insufficient_material() else
                    "Fifty-move rule" if board.can_claim_fifty_moves() else
                    "Threefold repetition" if board.can_claim_threefold_repetition() else
                    "Unknown")
            span.set_attribute("result", result)
            span.set_attribute("reason", reason)
            log.info(f"Game over: {result} - {reason}")   
       
if __name__ == "__main__":
    # URLs may include /sse or root depending on agent setup
    log.info("Starting Board Agent...")
    asyncio.run(run_game())
