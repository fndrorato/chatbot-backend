import requests

def get_chat_finished(chat_log):
    """
    Sends a chat log to the Ollama API and retrieves the response.
    
    Args:
        chat_log (str): The chat log to be sent to the Ollama API.
    
    Returns:
        str: The response from the Ollama API.
    """
    if not chat_log:
        return "Chat log is empty."

    # Ensure the chat log is a string
    if not isinstance(chat_log, str):
        return "Invalid chat log format. Expected a string."

    # Prepare the request to Ollama API
    url = "https://l5le7b5gpzkmmi3uvkzofv4y.agents.do-ai.run/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer dFByqKuxL-y49Pgwvk9kEPXguc8JGRZY"
    }
    payload = {
        "messages": [
            {
                "role": "user",
                "content": chat_log
            }
        ],
        "stream": False,
        "include_functions_info": False,
        "include_retrieval_info": False,
        "include_guardrails_info": False
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        result = response.json()
        resposta_ollama = result["choices"][0]["message"]["content"]
        print("Resposta do Ollama:", resposta_ollama)
        return resposta_ollama
    else:
        print("Erro ao enviar para Ollama:", response.status_code, response.text)
        return False
