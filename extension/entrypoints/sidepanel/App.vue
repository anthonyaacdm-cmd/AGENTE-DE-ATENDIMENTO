<script setup lang="ts">
import { ref, onMounted } from "vue";

interface Suggestion {
  suggested_response: string;
  sources: string[];
  confidence: number;
  error?: string;
  conversation_id?: string;
  intent?: string;
  sentiment?: string;
}

interface KnowledgeMatch {
  title: string;
  category: string;
  score: number;
  content_preview: string;
}

interface PageAnalysis {
  summary: string;
  topics: string[];
  key_points: string[];
  suggested_knowledge_title?: string;
  suggested_knowledge_category?: string;
  page_type?: string;
  entities?: string[];
  intent?: string;
  sentiment?: string;
  knowledge_matches?: KnowledgeMatch[];
  suggested_actions?: string[];
}

const pageAnalysis = ref<PageAnalysis | null>(null);
const analysisLoading = ref(false);
const analysisError = ref("");

const suggestion = ref<Suggestion | null>(null);
const loading = ref(false);
const conversationText = ref("");
const ticketTitle = ref("");
const useStream = ref(false);
const streamContent = ref("");
const feedbackRating = ref(0);
const feedbackComment = ref("");
const feedbackSent = ref(false);
const lastConversationId = ref("");

const activeTab = ref<"analisar" | "gerar">("analisar");

const intentLabels: Record<string, string> = {
  duvida_matricula: "Dúvida Matrícula",
  problema_financeiro: "Problema Financeiro",
  suporte_tecnico: "Suporte Técnico",
  informacao_academica: "Informação Acadêmica",
  reclamacao: "Reclamação",
  solicitacao_documento: "Solicitação Documento",
  cancelamento: "Cancelamento",
  outro: "Outro",
};

const sentimentLabels: Record<string, string> = {
  positivo: "Positivo",
  neutro: "Neutro",
  negativo: "Negativo",
  irritado: "Irritado",
};

onMounted(async () => {
  const saved = await browser.storage.local.get("pendingAnalysis");
  if (saved.pendingAnalysis) {
    await browser.storage.local.remove("pendingAnalysis");
    if (saved.pendingAnalysis === "__page__") {
      autoAnalyzePage();
    } else {
      conversationText.value = saved.pendingAnalysis;
      activeTab.value = "gerar";
    }
  } else {
    autoAnalyzePage();
  }
});

async function autoAnalyzePage() {
  analysisLoading.value = true;
  analysisError.value = "";
  pageAnalysis.value = null;
  try {
    const result = await browser.runtime.sendMessage({ type: "ANALYZE_PAGE" });
    if (result.error) {
      analysisError.value = result.error;
    } else {
      pageAnalysis.value = result as PageAnalysis;
    }
  } catch (err: any) {
    analysisError.value = `Erro: ${err.message}`;
  } finally {
    analysisLoading.value = false;
  }
}

async function fetchPageText() {
  try {
    const result = await browser.runtime.sendMessage({ type: "FETCH_PAGE_TEXT" });
    if (result.text) {
      conversationText.value = result.text.slice(0, 15000);
    }
  } catch {
    // silent
  }
}

async function generateSuggestion() {
  loading.value = true;
  suggestion.value = null;
  streamContent.value = "";
  feedbackSent.value = false;

  const text = conversationText.value.trim();
  if (!text) {
    suggestion.value = {
      suggested_response: "",
      sources: [],
      confidence: 0,
      error: "Nenhum conteúdo para gerar resposta.",
    };
    loading.value = false;
    return;
  }

  const turns = [{ author: "Aluno", message: text }];

  try {
    const result = await browser.runtime.sendMessage({
      type: "GENERATE_RESPONSE",
      payload: {
        conversation: turns,
        ticketTitle: ticketTitle.value,
        conversationId: lastConversationId.value || undefined,
      },
    });
    if (result.conversation_id) {
      lastConversationId.value = result.conversation_id;
    }
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

async function generateStreaming() {
  loading.value = true;
  suggestion.value = null;
  streamContent.value = "";
  feedbackSent.value = false;

  const text = conversationText.value.trim();
  if (!text) {
    suggestion.value = {
      suggested_response: "",
      sources: [],
      confidence: 0,
      error: "Nenhum conteúdo para gerar resposta.",
    };
    loading.value = false;
    return;
  }

  const turns = [{ author: "Aluno", message: text }];

  try {
    const result = await browser.runtime.sendMessage({
      type: "GENERATE_STREAM",
      payload: {
        conversation: turns,
        ticketTitle: ticketTitle.value,
        conversationId: lastConversationId.value || undefined,
      },
    });

    if (result.error) {
      suggestion.value = { suggested_response: "", sources: [], confidence: 0, error: result.error };
      loading.value = false;
      return;
    }

    const reader = result.stream;
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.token) {
              streamContent.value += data.token;
            }
            if (data.done) {
              if (data.conversation_id) {
                lastConversationId.value = data.conversation_id;
              }
              suggestion.value = {
                suggested_response: streamContent.value,
                sources: [],
                confidence: 0.5,
              };
            }
            if (data.error) {
              suggestion.value = { suggested_response: "", sources: [], confidence: 0, error: data.error };
            }
          } catch {}
        }
      }
    }
  } catch (err: any) {
    suggestion.value = { suggested_response: "", sources: [], confidence: 0, error: `Erro: ${err.message}` };
  } finally {
    loading.value = false;
  }
}

function copyText(text: string) {
  navigator.clipboard.writeText(text);
}

function newConversation() {
  lastConversationId.value = "";
  conversationText.value = "";
  suggestion.value = null;
  streamContent.value = "";
  feedbackSent.value = false;
}

async function submitFeedback() {
  if (!suggestion.value?.conversation_id || feedbackRating.value === 0) return;
  try {
    await browser.runtime.sendMessage({
      type: "SUBMIT_FEEDBACK",
      payload: {
        conversation_id: suggestion.value.conversation_id,
        response_text: suggestion.value.suggested_response,
        rating: feedbackRating.value,
        comment: feedbackComment.value,
      },
    });
    feedbackSent.value = true;
  } catch {}
}
</script>

<template>
  <div class="sidepanel">
    <div class="header">
      <h1>Agente de Atendimento</h1>
      <p class="subtitle">Analisa a aba atual e gera respostas inteligentes</p>
    </div>

    <div class="tabs">
      <button :class="{ active: activeTab === 'analisar' }" @click="activeTab = 'analisar'">Análise</button>
      <button :class="{ active: activeTab === 'gerar' }" @click="activeTab = 'gerar'">Responder</button>
    </div>

    <!-- Tab: Análise -->
    <div v-if="activeTab === 'analisar'" class="tab-content">
      <div v-if="analysisLoading" class="loading">
        <div class="spinner"></div>
        <span>Analisando página...</span>
      </div>

      <div v-if="analysisError" class="error">{{ analysisError }}</div>

      <div v-if="pageAnalysis" class="analysis-box">
        <div class="section">
          <h3>Resumo</h3>
          <p>{{ pageAnalysis.summary }}</p>
        </div>

        <div class="meta-bar">
          <span v-if="pageAnalysis.page_type" class="meta-badge type-badge">{{ pageTypeLabel(pageAnalysis.page_type) }}</span>
          <span v-if="pageAnalysis.intent" class="meta-badge intent-badge">{{ intentLabel(pageAnalysis.intent) }}</span>
          <span v-if="pageAnalysis.sentiment" class="meta-badge" :class="'sent-' + pageAnalysis.sentiment">{{ sentimentLabel(pageAnalysis.sentiment) }}</span>
        </div>

        <div v-if="pageAnalysis.topics.length" class="section">
          <h3>Tópicos</h3>
          <div class="topic-list">
            <span v-for="t in pageAnalysis.topics" :key="t" class="topic-tag">{{ t }}</span>
          </div>
        </div>

        <div v-if="pageAnalysis.key_points.length" class="section">
          <h3>Pontos-chave</h3>
          <ul>
            <li v-for="p in pageAnalysis.key_points" :key="p">{{ p }}</li>
          </ul>
        </div>

        <div v-if="pageAnalysis.entities?.length" class="section">
          <h3>Entidades identificadas</h3>
          <div class="entity-list">
            <span v-for="e in pageAnalysis.entities" :key="e" class="entity-tag">{{ e }}</span>
          </div>
        </div>

        <div v-if="pageAnalysis.suggested_actions?.length" class="section">
          <h3>Ações sugeridas</h3>
          <ul>
            <li v-for="a in pageAnalysis.suggested_actions" :key="a">{{ a }}</li>
          </ul>
        </div>

        <div v-if="pageAnalysis.knowledge_matches?.length" class="section">
          <h3>Conhecimento relacionado</h3>
          <div v-for="km in pageAnalysis.knowledge_matches" :key="km.title" class="km-card">
            <div class="km-header">
              <strong>{{ km.title }}</strong>
              <span class="km-cat">{{ km.category }}</span>
              <span class="km-score">{{ (km.score * 100).toFixed(0) }}%</span>
            </div>
            <p class="km-preview">{{ km.content_preview }}</p>
          </div>
        </div>

        <div v-if="pageAnalysis.suggested_knowledge_title" class="suggest-add">
          <p>Sugestão: adicionar <strong>"{{ pageAnalysis.suggested_knowledge_title }}"</strong> à base de conhecimento</p>
          <span class="km-cat">{{ pageAnalysis.suggested_knowledge_category }}</span>
        </div>

        <div class="section actions">
          <button class="btn-primary" @click="activeTab = 'gerar'; fetchPageText()">
            Gerar resposta baseada nesta página
          </button>
          <button class="btn-secondary" @click="autoAnalyzePage">
            Reanalisar página
          </button>
        </div>
      </div>

      <div v-if="!analysisLoading && !pageAnalysis && !analysisError" class="empty">
        <p>Clique em "Analisar" para entender o conteúdo da página atual.</p>
        <button class="btn-primary" @click="autoAnalyzePage">Analisar página</button>
      </div>
    </div>

    <!-- Tab: Responder -->
    <div v-if="activeTab === 'gerar'" class="tab-content">
      <div class="field">
        <label>Título do ticket (opcional)</label>
        <input v-model="ticketTitle" placeholder="Ex: Problema com matrícula" />
      </div>

      <div class="field">
        <label>Conteúdo / Conversa</label>
        <div class="textarea-actions">
          <button class="btn-sm" @click="fetchPageText">Usar texto da página</button>
          <button v-if="lastConversationId" class="btn-sm" @click="newConversation">Nova</button>
        </div>
        <textarea
          v-model="conversationText"
          placeholder="Cole a conversa ou descrição do atendimento..."
          rows="6"
        ></textarea>
      </div>

      <div class="stream-toggle">
        <label>
          <input type="checkbox" v-model="useStream" @change="() => {}" id="streamToggle" />
          Streaming (tempo real)
        </label>
      </div>

      <button
        class="btn-primary"
        :disabled="loading || !conversationText.trim()"
        @click="useStream ? generateStreaming() : generateSuggestion()"
      >
        {{ loading ? "Gerando..." : "Gerar Resposta" }}
      </button>

      <div v-if="loading && streamContent" class="stream-box">
        <p>{{ streamContent }}</p>
      </div>

      <div v-if="suggestion" class="result-box">
        <div v-if="suggestion.error" class="error">{{ suggestion.error }}</div>
        <div v-else>
          <div class="response-card">
            <div class="response-header">
              <strong>Resposta Sugerida</strong>
              <span class="badge" :class="confidenceClass(suggestion.confidence)">
                {{ (suggestion.confidence * 100).toFixed(0) }}%
              </span>
            </div>
            <div v-if="suggestion.intent" class="meta-tags">
              <span class="tag-intent">{{ intentLabels[suggestion.intent] || suggestion.intent }}</span>
              <span v-if="suggestion.sentiment" class="tag-sentiment">{{ sentimentLabels[suggestion.sentiment] || suggestion.sentiment }}</span>
            </div>
            <p>{{ suggestion.suggested_response }}</p>
            <button class="btn-copy" @click="copyText(suggestion.suggested_response)">
              Copiar resposta
            </button>
          </div>

          <div v-if="suggestion.sources.length" class="sources">
            <strong>Fontes:</strong>
            <ul>
              <li v-for="s in suggestion.sources" :key="s">{{ s }}</li>
            </ul>
          </div>

          <div v-if="suggestion.conversation_id && !feedbackSent" class="feedback-box">
            <strong>Útil?</strong>
            <div class="stars">
              <button v-for="n in 5" :key="n" class="star" :class="{ active: n <= feedbackRating }" @click="feedbackRating = n">{{ n <= feedbackRating ? '★' : '☆' }}</button>
            </div>
            <input v-model="feedbackComment" placeholder="Comentário (opcional)" class="feedback-input" />
            <button class="btn-sm" :disabled="feedbackRating === 0" @click="submitFeedback">Enviar</button>
          </div>
          <div v-if="feedbackSent" class="feedback-ok">Obrigado!</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
function confidenceClass(score: number): string {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}

function pageTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    ticket_atendimento: "Ticket",
    chat_transcricao: "Chat",
    faq: "FAQ",
    artigo_conhecimento: "Artigo",
    formulario: "Formulário",
    painel_admin: "Painel",
    perfil_usuario: "Perfil",
    lista_processos: "Lista",
    dashboard: "Dashboard",
    erro: "Erro",
  };
  return labels[type] || type;
}

function intentLabel(intent: string): string {
  const labels: Record<string, string> = {
    duvida_matricula: "Matrícula",
    problema_financeiro: "Financeiro",
    suporte_tecnico: "Suporte Técnico",
    informacao_academica: "Acadêmico",
    reclamacao: "Reclamação",
    solicitacao_documento: "Documento",
    cancelamento: "Cancelamento",
    consulta: "Consulta",
  };
  return labels[intent] || intent;
}

function sentimentLabel(sentiment: string): string {
  const labels: Record<string, string> = {
    positivo: "Positivo",
    neutro: "Neutro",
    negativo: "Negativo",
    irritado: "Irritado",
    urgente: "Urgente",
  };
  return labels[sentiment] || sentiment;
}
</script>

<style scoped>
.sidepanel {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  color: white;
  padding: 16px;
}

.header h1 {
  font-size: 15px;
  font-weight: 700;
}

.subtitle {
  font-size: 11px;
  opacity: 0.8;
  margin-top: 2px;
}

.tabs {
  display: flex;
  gap: 2px;
  padding: 8px 12px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
}

.tabs button {
  flex: 1;
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s;
}

.tabs button.active {
  background: white;
  color: #4f46e5;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.tab-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

.field {
  margin-bottom: 10px;
}

.field label {
  display: block;
  font-size: 11px;
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
  box-sizing: border-box;
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

.textarea-actions {
  display: flex;
  gap: 4px;
  margin-bottom: 6px;
}

.textarea-actions label {
  margin-bottom: 0;
}

.stream-toggle {
  font-size: 11px;
  color: #64748b;
  margin-bottom: 8px;
}

.stream-toggle label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
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
  white-space: nowrap;
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
  font-size: 13px;
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

.btn-secondary {
  width: 100%;
  padding: 8px;
  background: transparent;
  color: #4f46e5;
  border: 1px solid #4f46e5;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
}

.btn-secondary:hover {
  background: #eef2ff;
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
  margin-top: 12px;
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
  font-size: 12px;
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
  font-size: 10px;
  font-weight: 600;
}

.badge.high { background: #dcfce7; color: #166534; }
.badge.mid { background: #fef9c3; color: #854d0e; }
.badge.low { background: #fee2e2; color: #991b1b; }

.sources {
  margin-top: 10px;
  font-size: 11px;
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
  margin-bottom: 8px;
}

.feedback-ok {
  margin-top: 8px;
  font-size: 12px;
  color: #16a34a;
  font-weight: 500;
}

h3 {
  font-size: 12px;
  margin-bottom: 6px;
  color: #1e293b;
}

.section {
  margin-bottom: 14px;
}

.section p {
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
}

.section ul {
  margin: 4px 0 0 16px;
  font-size: 13px;
  color: #475569;
}

.section ul li {
  margin-bottom: 4px;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.topic-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.topic-tag {
  font-size: 11px;
  background: #e0e7ff;
  color: #4338ca;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #64748b;
  padding: 24px;
  font-size: 13px;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #e2e8f0;
  border-top-color: #4f46e5;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty {
  text-align: center;
  color: #94a3b8;
  padding: 24px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.stream-box {
  margin-top: 12px;
  padding: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: #0f172a;
  max-height: 200px;
  overflow-y: auto;
}

.meta-tags {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.tag-intent {
  font-size: 10px;
  background: #e0e7ff;
  color: #4338ca;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.tag-sentiment {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  background: #fef9c3;
  color: #854d0e;
}

.feedback-box {
  margin-top: 10px;
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 12px;
}

.feedback-box strong {
  display: block;
  margin-bottom: 6px;
}

.stars {
  display: flex;
  gap: 2px;
  margin-bottom: 6px;
}

.star {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #cbd5e1;
  padding: 0;
}

.star.active {
  color: #f59e0b;
}

.feedback-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  font-size: 12px;
  margin-bottom: 6px;
  box-sizing: border-box;
}

.meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.meta-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.type-badge { background: #e0e7ff; color: #4338ca; }
.intent-badge { background: #fef9c3; color: #854d0e; }
.sent-positivo { background: #dcfce7; color: #166534; }
.sent-neutro { background: #f1f5f9; color: #64748b; }
.sent-negativo { background: #fee2e2; color: #dc2626; }
.sent-irritado { background: #fecaca; color: #991b1b; }
.sent-urgente { background: #ffedd5; color: #c2410c; }

.entity-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.entity-tag {
  font-size: 11px;
  background: #f0fdf4;
  color: #166534;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  border: 1px solid #86efac;
}

.km-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.km-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.km-header strong {
  font-size: 12px;
  color: #1e293b;
}

.km-cat {
  font-size: 9px;
  background: #e0e7ff;
  color: #4338ca;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.km-score {
  font-size: 10px;
  color: #64748b;
  font-weight: 600;
  margin-left: auto;
}

.km-preview {
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}
</style>
