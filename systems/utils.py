from systems.models import LogApiSystem

def log_received_json(client_instance, data, origin_name=None, status_message=None):
    """
    Salva o conteúdo JSON recebido em LogReceivedJson.

    :param client_instance: Instância do objeto Client.
    :param data: O conteúdo (JSON) a ser salvo.
    :param origin_name: (Opcional) A origem.
    :param status_message: (Opcional) A mensagem de status/erro. <--- NOVO
    :return: A instância de LogReceivedJson criada ou None em caso de falha.
    """
    try:
        log_entry = LogApiSystem.objects.create(
            client_id=client_instance,
            origin=origin_name,
            content=data,
            status_message=status_message # <--- SALVANDO O ERRO/STATUS
        )
        return log_entry
    except Exception as e:
        print(f"Erro ao salvar LogReceivedJson: {e}")
        return None