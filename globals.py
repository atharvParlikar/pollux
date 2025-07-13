import logging
from openai.types.shared.chat_model import ChatModel
from rich.console import Console
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

MODEL: ChatModel = "gpt-4o"
MAX_RETRIES = 3
RETRY_DELAY = 1.0
COMMAND_TIMEOUT = 30
MAX_CONTEXT_LENGTH = 10000
MAX_HISTORY_LENGTH = 50

PROJECT_DIR = "/Users/atharvparlikar/dev/pollux-py"

