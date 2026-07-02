<script setup lang="ts">
import { ref, onMounted } from "vue";

// ─── Types ──────────────────────────────────────────────
interface ConversationTurn {
  author: string;
  message: string;
  timestamp?: string;
}

interface Suggestion {
  suggested_response: string;
  sources: string[];
  confidence: number;
  error?: string;
}

interface HealthStatus {
  status: string;
  qdrant: boolean;
  ai: boolean;
}

// ─── State ──────────────────────────────────────────────
const activeTab = ref<"gerar" | "conhecimento" | "config">("gerar");
const loading = ref(false);
const suggestion = ref<Suggestion | null>(null);
const health = ref<HealthStatus | null>(null);
const serverUrl = ref("https://agente-de-atendimento.onrender.com");
const conversationText = ref("");
const ticketTitle = ref("");

// Knowledge form
const kTitle = ref("");
const kContent = ref("");
const kCategory = ref("geral");
const kTags = ref("");
const kMessage = ref("");

// ─── Lifecycle ──────────────────────────────────────────
onMounted(async () => {
  const saved = await browser.storage.local.get("serverUrl");
  if (saved.serverUrl) serverUrl.value = saved.serverUrl;
  checkHealth();
});

// ─── Methods ────────────────────────────────────────────
async function checkHealth() {
  try {
    const res = await browser.runtime.sendMessage({ type: "GET_HEALTH" });
    health.value = res as HealthStatus;
  } catch {
    health.value = { status: "error", qdrant: false, ai: false };
  }
}

async function generateSuggestion() {
  loading.value = true;
  suggestion.value = null;

  const turns = parseConversation(conversationText.value);
  if (turns.length === 0) {
    suggestion.value = {
      suggested_response: "",
      sources: [],
      confidence: 0,
      error: "Nenhuma conversa encontrada. Use o formato: Nome: Mensagem",
    };
    loading.value = false;
    return;
  }

  try {
    const result = await browser.runtime.sendMessage({
      type: "GENERATE_RESPONSE",
      payload: {
        conversation: turns,
        ticketTitle: ticketTitle.value,
      },
    });
    suggestion.value = result as Suggestion;
  } catch (err: any) {
    suggestion.value = {
      suggested_response: "",
      sources: [],
      confidence: 0,
      error: `Erro: ${err.message}`,
    };
  } finally {
    loading.value = false;
  }
}

function parseConversation(text: string): ConversationTurn[] {
  return text
    .split("\n")
    .filter((line) => line.includes(":"))
    .map((line) => {
      const i = line.indexOf(":");
      return {
        author: line.slice(0, i).trim(),
        message: line.slice(i + 1).trim(),
      };
    });
}

async function fetchPageText() {
  try {
    const result = await browser.runtime.sendMessage({ type: "FETCH_PAGE_TEXT" });
    if (result.text) {
      conversationText.value = result.text.slice(0, 5000);
    }
  } catch {
    // silent
  }
}

function copyText(text: string) {
  navigator.clipboard.writeText(text);
}

async function addKnowledge() {
  if (!kTitle.value || !kContent.value) return;
  kMessage.value = "";

  try {
    const result = await browser.runtime.sendMessage({
      type: "ADD_KNOWLEDGE",
      payload: {
        title: kTitle.value,
        content: kContent.value,
        category: kCategory.value,
        tags: kTags.value.split(",").map((t) => t.trim()).filter(Boolean),
      },
    });
    if (result.error) {
      kMessage.value = `Erro: ${result.error}`;
    } else {
      kMessage.value = "Conhecimento adicionado com sucesso!";
      kTitle.value = "";
      kContent.value = "";
      kTags.value = "";
    }
  } catch (err: any) {
    kMessage.value = `Erro: ${err.message}`;
  }
}

async function saveServerUrl() {
  await browser.storage.local.set({ serverUrl: serverUrl.value });
  await browser.runtime.sendMessage({ type: "SET_SERVER_URL", url: serverUrl.value });
  checkHealth();
}
</script>

<template>
  <div class="app">
    <!-- Header -->
    <div class="header">
      <h1>Agente de Atendimento</h1>
      <div class="tabs">
        <button
          :class="{ active: activeTab === 'gerar' }"
          @click="activeTab = 'gerar'"
        >Gerar</button>
        <button
          :class="{ active: activeTab === 'conhecimento' }"
          @click="activeTab = 'conhecimento'"
        >Conhecimento</button>
        <button
          :class="{ active: activeTab === 'config' }"
          @click="activeTab = 'config'"
        >Config</button>
      </div>
    </div>

    <!-- Tab: Gerar -->
    <div v-if="activeTab === 'gerar'" class="tab-content">
      <div class="field">
        <label>Título do ticket (opcional)</label>
        <input v-model="ticketTitle" placeholder="Ex: Problema com matrícula" />
      </div>

      <div class="field">
        <label>Conversa</label>
        <div class="textarea-actions">
          <button class="btn-sm" @click="fetchPageText">Capturar da página</button>
        </div>
        <textarea
          v-model="conversationText"
          placeholder="Cole a conversa aqui...&#10;Formato:&#10;Aluno: Preciso de ajuda&#10;Atendente: Claro, como posso ajudar?"
          rows="8"
        ></textarea>
      </div>

      <button
        class="btn-primary"
        :disabled="loading || !conversationText"
        @click="generateSuggestion"
      >
        {{ loading ? "Gerando..." : "Gerar Resposta Sugerida" }}
      </button>

      <div v-if="suggestion" class="result-box">
        <div v-if="suggestion.error" class="error">{{ suggestion.error }}</div>
        <div v-else>
          <div class="response-card">
            <div class="response-header">
              <strong>Resposta Sugerida</strong>
              <span class="badge" :class="confidenceLevel(suggestion.confidence)">
                {{ (suggestion.confidence * 100).toFixed(0) }}%
              </span>
            </div>
            <p>{{ suggestion.suggested_response }}</p>
            <button class="btn-copy" @click="copyText(suggestion.suggested_response)">
              Copiar resposta
            </button>
          </div>

          <div v-if="suggestion.sources.length" class="sources">
            <strong>Fontes consultadas:</strong>
            <ul>
              <li v-for="s in suggestion.sources" :key="s">{{ s }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab: Conhecimento -->
    <div v-if="activeTab === 'conhecimento'" class="tab-content">
      <h2>Adicionar Conhecimento</h2>
      <div class="field">
        <label>Título</label>
        <input v-model="kTitle" placeholder="Título do artigo" />
      </div>
      <div class="field">
        <label>Conteúdo</label>
        <textarea v-model="kContent" rows="5" placeholder="Conteúdo do conhecimento..."></textarea>
      </div>
      <div class="field-row">
        <div class="field flex-1">
          <label>Categoria</label>
          <select v-model="kCategory">
            <option value="geral">Geral</option>
            <option value="matricula">Matrícula</option>
            <option value="financeiro">Financeiro</option>
            <option value="tecnico">Técnico</option>
            <option value="academico">Acadêmico</option>
          </select>
        </div>
        <div class="field flex-1">
          <label>Tags (vírgulas)</label>
          <input v-model="kTags" placeholder="tag1, tag2" />
        </div>
      </div>
      <button class="btn-primary" @click="addKnowledge">Adicionar</button>
      <p v-if="kMessage" class="feedback">{{ kMessage }}</p>
    </div>

    <!-- Tab: Config -->
    <div v-if="activeTab === 'config'" class="tab-content">
      <h2>Configuração</h2>
      <div class="field">
        <label>URL do servidor</label>
        <input v-model="serverUrl" placeholder="https://agente-de-atendimento.onrender.com" />
      </div>
      <button class="btn-primary" @click="saveServerUrl">Salvar</button>

      <div class="status-card">
        <h3>Status do Servidor</h3>
        <div v-if="health">
          <p>Servidor: <span :class="health.status === 'ok' ? 'ok' : 'err'">{{ health.status }}</span></p>
          <p>Qdrant: <span :class="health.qdrant ? 'ok' : 'err'">{{ health.qdrant ? 'Online' : 'Offline' }}</span></p>
          <p>IA: <span :class="health.ai ? 'ok' : 'err'">{{ health.ai ? 'Configurada' : 'Sem chave API' }}</span></p>
        </div>
        <p v-else class="err">Não foi possível conectar</p>
        <button class="btn-sm" @click="checkHealth">Verificar novamente</button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
function confidenceLevel(score: number): string {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}
</script>

<style scoped>
.app {
  width: 420px;
  min-height: 300px;
  padding: 0;
}

.header {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: white;
  padding: 16px;
}

.header h1 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
}

.tabs {
  display: flex;
  gap: 4px;
}

.tabs button {
  flex: 1;
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s;
}

.tabs button.active {
  background: white;
  color: #4f46e5;
}

.tab-content {
  padding: 16px;
}

.field {
  margin-bottom: 12px;
}

.field label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 4px;
}

.field input,
.field textarea,
.field select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  background: white;
  color: #1e293b;
  transition: border-color 0.2s;
}

.field input:focus,
.field textarea:focus,
.field select:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.field textarea {
  resize: vertical;
  font-family: inherit;
}

.field-row {
  display: flex;
  gap: 8px;
}

.flex-1 {
  flex: 1;
}

.textarea-actions {
  margin-bottom: 6px;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 11px;
  background: #e2e8f0;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: #475569;
  font-weight: 500;
}

.btn-sm:hover {
  background: #cbd5e1;
}

.btn-primary {
  width: 100%;
  padding: 10px;
  margin-top: 4px;
  background: #4f46e5;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #4338ca;
}

.btn-primary:disabled {
  background: #a5b4fc;
  cursor: not-allowed;
  opacity: 0.7;
}

.btn-copy {
  padding: 6px 14px;
  margin-top: 8px;
  background: white;
  color: #4f46e5;
  border: 1px solid #4f46e5;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
}

.btn-copy:hover {
  background: #eef2ff;
}

.result-box {
  margin-top: 16px;
}

.response-card {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  padding: 12px;
}

.response-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.response-card p {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: #0f172a;
}

.badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.badge.high { background: #dcfce7; color: #166534; }
.badge.mid { background: #fef9c3; color: #854d0e; }
.badge.low { background: #fee2e2; color: #991b1b; }

.sources {
  margin-top: 12px;
  font-size: 12px;
  color: #64748b;
}

.sources ul {
  margin: 4px 0 0 16px;
}

.sources li {
  margin-bottom: 2px;
}

.error {
  color: #dc2626;
  font-size: 13px;
  padding: 8px;
  background: #fef2f2;
  border-radius: 6px;
}

.feedback {
  margin-top: 8px;
  font-size: 13px;
  color: #16a34a;
  font-weight: 500;
}

.status-card {
  margin-top: 16px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  font-size: 13px;
}

.status-card h3 {
  font-size: 13px;
  margin-bottom: 8px;
}

.status-card p {
  margin-bottom: 4px;
}

.ok { color: #16a34a; font-weight: 600; }
.err { color: #dc2626; font-weight: 600; }

h2 {
  font-size: 14px;
  margin-bottom: 12px;
  color: #1e293b;
}
</style>
