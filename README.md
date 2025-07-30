# 📦 Hotel Reservation API

Sistema de integração e gerenciamento de reservas para múltiplos clientes (hotel, salão, etc) desenvolvido com Django e Django REST Framework.

## 📚 Funcionalidades

* Receber reservas via API externa
* Integração com APIs de terceiros (hospedagem, salões, etc)
* Documentação automática via Swagger
* Sistema de logging e integração

## 🚀 Como executar com Docker

### 1. Requisitos

* Docker
* Docker Compose

### 2. Build da imagem

```bash
docker-compose up --build -d
```

---

## 📘 Documentação da API

A documentação da API está disponível em:

* Swagger UI: [`/api/v1/docs/`](http://localhost:8000/api/v1/docs/)
* ReDoc: [`/api/v1/redoc/`](http://localhost:8000/api/v1/redoc/)

Inclui:

* Autenticação via token Bearer
* Endpoints por tipo de cliente (ex: `/systems/hotel/reservations/...`)
* Modelos e exemplos para cada rota

---

## 🗂 Estrutura

```
app/
├── chats/
├── clients/
├── common/
├── systems/
│   └── hotel/
│       └── reservations.py
├── media/
├── logs/
├── manage.py
└── Dockerfile
```

---

## 🧪 Testes

> Em breve: scripts de testes automatizados para endpoints.

---

---

## 📝 Licença

Este projeto está sob a licença MIT - veja o arquivo [LICENSE](./LICENSE) para mais detalhes.
