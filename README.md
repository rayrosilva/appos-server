# Appos Server

Backend do mensageiro Appos — projeto acadêmico.

## Deploy no Render.com

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Faça fork deste repositório
2. No Render.com: **New > Web Service > Connect a repository**
3. Selecione este repo
4. Clique **Create Web Service** (as configurações são detectadas automaticamente)

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Servidor inicia em `http://localhost:8765`

## API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Status do servidor |
| POST | `/api/register` | Criar conta |
| POST | `/api/login` | Entrar |
| GET | `/api/users` | Listar usuários |
| GET | `/api/users/search?q=` | Buscar usuário |
| GET/POST | `/api/contacts` | Listar/adicionar contatos |
| DELETE | `/api/contacts/<id>` | Remover contato |
| GET | `/api/conversations` | Listar conversas |
| POST | `/api/conversations/dm` | Criar DM |
| GET | `/api/messages/<id>` | Mensagens de uma conversa |
| POST | `/api/messages` | Enviar mensagem |
| GET/POST | `/api/calls` | Listar/criar chamadas |
| GET/POST | `/api/profile` | Ver/atualizar perfil |
