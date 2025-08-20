import requests
import os
from decouple import config


def get_chat_finished(chat_log):
    """
    Envia um chat_log para a API da OpenAI e retorna 'true' ou 'false'
    dependendo se a conversa foi encerrada.
    """

    if not chat_log:
        return "Chat log is empty."

    # Garante que o chat log seja uma string
    if not isinstance(chat_log, str):
        return "Invalid chat log format. Expected a string."

    # Endpoint da OpenAI
    print(chat_log)
    # OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_API_KEY = config('OPENAI_API_KEY')
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }    
    url = "https://api.openai.com/v1/chat/completions"

    # Monta payload
    payload = {
        "model": "gpt-4.1-nano",
        "messages": [
            {"role": "system", "content": "Você é um classificador. Responda apenas 'true' ou 'false'.\
            Responda 'true' se a conversa claramente foi encerrada, ou 'false' caso contrário."},
            {"role": "user", "content": chat_log}
        ],
        "temperature": 0,  # resposta determinística
        "max_tokens": 5    # garante que só venha 'true' ou 'false'
    }

    print("Enviando para OpenAI:", chat_log)
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        result = response.json()
        resposta = result["choices"][0]["message"]["content"].strip().lower()
        print("Resposta da OpenAI:", resposta)
        return resposta
    else:
        print("Erro ao enviar para OpenAI:", response.status_code, response.text)
        return False



# def get_chat_finished(chat_log):
#     """
#     Sends a chat log to the Ollama API and retrieves the response.
    
#     Args:
#         chat_log (str): The chat log to be sent to the Ollama API.
    
#     Returns:
#         str: The response from the Ollama API.
#     """
#     if not chat_log:
#         return "Chat log is empty."

#     # Ensure the chat log is a string
#     if not isinstance(chat_log, str):
#         return "Invalid chat log format. Expected a string."

#     # Prepare the request to Ollama API
#     url = "https://l5le7b5gpzkmmi3uvkzofv4y.agents.do-ai.run/api/v1/chat/completions"
#     OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
#     if not OPENAI_API_KEY:
#         raise RuntimeError("OPENAI_API_KEY não configurada")

#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {OPENAI_API_KEY}",
#     }
#     payload = {
#         "messages": [
#             {
#                 "role": "user",
#                 "content": chat_log
#             }
#         ],
#         "stream": False,
#         "include_functions_info": False,
#         "include_retrieval_info": False,
#         "include_guardrails_info": False
#     }
#     print("Enviando para Ollama:", chat_log)
#     response = requests.post(url, json=payload, headers=headers)

#     if response.status_code == 200:
#         result = response.json()
#         resposta_ollama = result["choices"][0]["message"]["content"]
#         print("Resposta do Ollama:", resposta_ollama)
#         return resposta_ollama
#     else:
#         print("Erro ao enviar para Ollama:", response.status_code, response.text)
#         return False
