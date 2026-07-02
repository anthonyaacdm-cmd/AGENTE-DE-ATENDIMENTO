import { defineBackground } from "wxt/sandbox";

const DEFAULT_API_BASE = "https://agente-de-atendimento.onrender.com/api/v1";
let API_BASE = DEFAULT_API_BASE;

interface ConversationTurn {
  author: string;
  message: string;
  timestamp?: string;
}

export default defineBackground({
  main() {
    browser.storage.local.get("serverUrl").then((saved: any) => {
      if (saved.serverUrl) {
        API_BASE = saved.serverUrl.replace(/\/+$/, "") + "/api/v1";
      }
    });

    browser.runtime.onMessage.addListener(async (message: any) => {
      switch (message.type) {
        case "GENERATE_RESPONSE":
          return handleGenerate(message.payload);
        case "ADD_KNOWLEDGE":
          return handleAddKnowledge(message.payload);
        case "SEARCH_KNOWLEDGE":
          return handleSearchKnowledge(message.payload);
        case "FETCH_PAGE_TEXT":
          return handleFetchPageText();
        case "GET_HEALTH":
          return handleHealth();
        case "SET_SERVER_URL":
          API_BASE = message.url.replace(/\/+$/, "") + "/api/v1";
          return { ok: true };
        case "EXTRACT_TEXT":
          return handleExtractText(message.fileData, message.fileName);
        case "LIST_KNOWLEDGE":
          return handleListKnowledge(message.query, message.offset, message.limit);
        case "GET_KNOWLEDGE":
          return handleGetKnowledge(message.id);
        case "UPDATE_KNOWLEDGE":
          return handleUpdateKnowledge(message.id, message.payload);
        case "DELETE_KNOWLEDGE":
          return handleDeleteKnowledge(message.id);
        case "CAPTURE_SCREENSHOT":
          return handleCaptureScreenshot();
        default:
          return { error: "unknown_type" };
      }
    });
  },
});

async function apiFetch(path: string, options?: RequestInit) {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers as Record<string, string>),
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return { error: err.detail || `HTTP ${res.status}` };
    }
    return await res.json();
  } catch (e: any) {
    return { error: `Servidor indisponível: ${e.message}` };
  }
}

async function apiUpload(path: string, fileData: number[], fileName: string) {
  const url = `${API_BASE}${path}`;
  try {
    const form = new FormData();
    const bytes = new Uint8Array(fileData);
    const blob = new Blob([bytes]);
    form.append("file", blob, fileName);
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return { error: err.detail || `HTTP ${res.status}` };
    }
    return await res.json();
  } catch (e: any) {
    return { error: `Erro no upload: ${e.message}` };
  }
}

async function handleGenerate(payload: {
  conversation: ConversationTurn[];
  ticketTitle?: string;
  attachmentText?: string;
}) {
  return apiFetch("/generate", {
    method: "POST",
    body: JSON.stringify({
      conversation: payload.conversation,
      ticket_title: payload.ticketTitle || "",
      attachment_text: payload.attachmentText || "",
    }),
  });
}

async function handleAddKnowledge(payload: {
  title: string;
  content: string;
  category?: string;
  tags?: string[];
}) {
  return apiFetch("/knowledge", {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      content: payload.content,
      category: payload.category || "geral",
      tags: payload.tags || [],
    }),
  });
}

async function handleSearchKnowledge(payload: { query: string }) {
  return apiFetch(`/knowledge/search?query=${encodeURIComponent(payload.query)}`);
}

async function handleFetchPageText() {
  try {
    const [tab] = await browser.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!tab?.id) return { text: "" };

    const results = await browser.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.body?.innerText || "",
    });

    return { text: results[0]?.result || "" };
  } catch {
    return { text: "" };
  }
}

async function handleHealth() {
  return apiFetch("/health");
}

async function handleExtractText(fileData: number[], fileName: string) {
  return apiUpload("/knowledge/extract", fileData, fileName);
}

async function handleListKnowledge(query: string, offset: number, limit: number) {
  let path = `/knowledge?offset=${offset}&limit=${limit}`;
  if (query) path += `&query=${encodeURIComponent(query)}`;
  return apiFetch(path);
}

async function handleGetKnowledge(id: string) {
  return apiFetch(`/knowledge/${encodeURIComponent(id)}`);
}

async function handleUpdateKnowledge(id: string, payload: any) {
  return apiFetch(`/knowledge/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

async function handleDeleteKnowledge(id: string) {
  return apiFetch(`/knowledge/${encodeURIComponent(id)}`, { method: "DELETE" });
}

async function handleCaptureScreenshot() {
  try {
    const dataUrl = await browser.tabs.captureVisibleTab();
    const res = await fetch(dataUrl);
    const blob = await res.blob();
    const buffer = await blob.arrayBuffer();
    const bytes = Array.from(new Uint8Array(buffer));
    return apiUpload("/knowledge/extract", bytes, "screenshot.png");
  } catch (e: any) {
    return { error: `Falha ao capturar tela: ${e.message}` };
  }
}
