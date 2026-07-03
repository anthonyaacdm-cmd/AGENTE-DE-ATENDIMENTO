from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

router = APIRouter()

WIDGET_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agente de Atendimento</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  body { background: #f5f5f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
  .chat-container { width: 380px; max-width: 100vw; height: 600px; max-height: 100vh; background: white; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); display: flex; flex-direction: column; overflow: hidden; }
  .header { background: linear-gradient(135deg, #4f46e5, #7c3aed); color: white; padding: 16px; }
  .header h1 { font-size: 16px; font-weight: 700; }
  .header p { font-size: 12px; opacity: 0.8; margin-top: 2px; }
  .messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
  .msg { max-width: 85%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; }
  .msg.user { background: #4f46e5; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.bot { background: #f1f5f9; color: #1e293b; align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg.system { background: #fef9c3; color: #854d0e; align-self: center; font-size: 12px; border-radius: 8px; }
  .input-area { padding: 12px; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; }
  .input-area input { flex: 1; padding: 10px 14px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; outline: none; }
  .input-area input:focus { border-color: #4f46e5; }
  .input-area button { padding: 10px 20px; background: #4f46e5; color: white; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .input-area button:disabled { background: #a5b4fc; cursor: not-allowed; }
  .typing { font-size: 12px; color: #94a3b8; padding: 4px 14px; }
</style>
</head>
<body>
<div class="chat-container">
  <div class="header">
    <h1>Agente de Atendimento</h1>
    <p>Assistente virtual de suporte</p>
  </div>
  <div class="messages" id="messages">
    <div class="msg bot">Olá! Como posso ajudar você hoje?</div>
  </div>
  <div class="typing" id="typing" style="display:none">Digitando...</div>
  <div class="input-area">
    <input id="input" type="text" placeholder="Digite sua mensagem..." onkeydown="if(event.key==='Enter') send()" />
    <button id="sendBtn" onclick="send()">Enviar</button>
  </div>
</div>
<script>
const API_URL = window.location.origin + '/api/v1';
let conversationId = null;

async function send() {
  const input = document.getElementById('input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  addMessage(msg, 'user');
  setTyping(true);
  try {
    const res = await fetch(API_URL + '/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation: [{ author: 'Aluno', message: msg }],
        conversation_id: conversationId
      })
    });
    const data = await res.json();
    if (data.conversation_id) conversationId = data.conversation_id;
    if (data.error) {
      addMessage('Erro: ' + data.error, 'system');
    } else {
      addMessage(data.suggested_response, 'bot');
    }
  } catch(e) {
    addMessage('Erro de conexão. Verifique o servidor.', 'system');
  } finally {
    setTyping(false);
  }
}

function addMessage(text, type) {
  const el = document.createElement('div');
  el.className = 'msg ' + type;
  el.textContent = text;
  document.getElementById('messages').appendChild(el);
  el.scrollIntoView({ behavior: 'smooth' });
}

function setTyping(show) {
  document.getElementById('typing').style.display = show ? 'block' : 'none';
}
</script>
</body>
</html>"""


@router.get("/chat-widget", response_class=HTMLResponse)
async def chat_widget():
    return HTMLResponse(WIDGET_HTML)
