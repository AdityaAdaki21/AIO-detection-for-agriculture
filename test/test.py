from groq import Groq
import os
from dotenv import load_dotenv, dotenv_values 
# loading variables from .env file
load_dotenv()
client = Groq(
    api_key=os.environ.get("GROQ_API_KEY"),
)

chat_completion = client.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": "whoa are you?",
        }
    ],
    model="qwen-2.5-coder-32b",
    stream=False,
)

print(chat_completion.choices[0].message.content)
