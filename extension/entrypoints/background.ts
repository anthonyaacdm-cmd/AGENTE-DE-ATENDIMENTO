import { defineBackground } from "wxt/sandbox";

const DEFAULT_API_BASE = "https://agente-de-atendimento.onrender.com/api/v1";
let API_BASE = DEFAULT_API_BASE;
let API_KEY = "";

interface ConversationTurn {
  author: string;
  message: string;
  timestamp?: string;
}

export default defineBackground({
  main() {
    browser.storage.local.get(["serverUrl", "apiKey"]).then((saved: any) => {
      if (saved.serverUrl) {
        API_BASE = saved.serverUrl.replace(/\/+$/, "") + "/api/v1";
      }
      if (saved.apiKey) {
        API_KEY = saved.apiKey;
      }
    });

    chrome.action.onClicked.addListener(async (tab) => {
      const windowId = tab.windowId || (await chrome.windows.getCurrent()).id;
      chrome.sidePanel.open({ windowId });
    });

    chrome.runtime.onInstalled.addListener(() => {
      chrome.contextMenus.create({
        id: "analyze-selection",
        title: "Analisar com Agente de Atendimento",
        contexts: ["selection"],
      });
      chrome.contextMenus.create({
        id: "analyze-page",
        title: "Analisar página com Agente de Atendimento",
        contexts: ["page"],
      });
    });

    chrome.contextMenus.onClicked.addListener((info, tab) => {
      if (info.menuItemId === "analyze-selection" && info.selectionText && tab?.id) {
        chrome.storage.local.set({ pendingAnalysis: info.selectionText });
        chrome.sidePanel.open({ windowId: tab.windowId });
      }
      if (info.menuItemId === "analyze-page" && tab?.id) {
        chrome.storage.local.set({ pendingAnalysis: "__page__" });
        chrome.sidePanel.open({ windowId: tab.windowId });
      }
    });

    browser.runtime.onMessage.addListener(async (message: any) => {
      switch (message.type) {
        case "GENERATE_RESPONSE":
          return handleGenerate(message.payload);
        case "GENERATE_STREAM":
          return handleGenerateStream(message.payload);
        case "ADD_KNOWLEDGE":
          return handleAddKnowledge(message.payload);
        case "SEARCH_KNOWLEDGE":
          return handleSearchKnowledge(message.payload);
        case "FETCH_PAGE_TEXT":
          return handleFetchPageText();
        case "ANALYZE_PAGE":
          return handleAnalyzePage();
        case "GET_HEALTH":
          return handleHealth();
        case "SET_SERVER_URL":
          API_BASE = message.url.replace(/\/+$/, "") + "/api/v1";
          return { ok: true };
        case "SET_API_KEY":
          API_KEY = message.apiKey;
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
        case "SUBMIT_FEEDBACK":
          return handleSubmitFeedback(message.payload);
        case "OPEN_SIDEPANEL":
          return handleOpenSidepanel();
        default:
          return { error: "unknown_type" };
      }
    });
  },
});

function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

async function apiFetch(path: string, options?: RequestInit) {
  const url = `${API_BASE}${path}`;
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options?.headers as Record<string, string>),
    };
    const res = await fetch(url, { ...options, headers });
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
    const headers = authHeaders();
    const res = await fetch(url, { method: "POST", body: form, headers });
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
  conversationId?: string;
}) {
  return apiFetch("/generate", {
    method: "POST",
    body: JSON.stringify({
      conversation: payload.conversation,
      ticket_title: payload.ticketTitle || "",
      attachment_text: payload.attachmentText || "",
      conversation_id: payload.conversationId || null,
    }),
  });
}

async function handleGenerateStream(payload: {
  conversation: ConversationTurn[];
  ticketTitle?: string;
  conversationId?: string;
}) {
  const url = `${API_BASE}/generate/stream`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        conversation: payload.conversation,
        ticket_title: payload.ticketTitle || "",
        conversation_id: payload.conversationId || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return { error: err.detail || `HTTP ${res.status}` };
    }
    const reader = res.body?.getReader();
    if (!reader) return { error: "Sem stream" };
    return { stream: reader };
  } catch (e: any) {
    return { error: `Erro no stream: ${e.message}` };
  }
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
      func: () => {
        const metaTags = document.querySelectorAll('meta[name], meta[property]');
        const metadata: Record<string, string> = {};
        metaTags.forEach(m => {
          const name = m.getAttribute('name') || m.getAttribute('property') || '';
          const content = m.getAttribute('content') || '';
          if (name && content) metadata[name] = content.slice(0, 500);
        });

        const structured: Record<string, any> = {};

        structured.forms = Array.from(document.querySelectorAll('form')).map(f => ({
          action: f.action,
          method: f.method,
          inputs: Array.from(f.querySelectorAll('input, select, textarea')).map(el => {
            const field = el as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
            const label = f.querySelector(`label[for="${field.id}"]`)?.textContent?.trim()
              || field.closest('.field, .form-group, .mb-3')?.querySelector('label')?.textContent?.trim()
              || field.placeholder || '';
            return {
              name: field.name || field.id,
              type: (field as HTMLInputElement).type || field.tagName.toLowerCase(),
              value: field.value?.slice(0, 500) || '',
              label: label.slice(0, 200),
            };
          }),
        })).filter(f => f.inputs.length > 0);

        structured.tables = Array.from(document.querySelectorAll('table')).slice(0, 10).map(t => ({
          caption: t.querySelector('caption')?.textContent?.trim() || '',
          headers: Array.from(t.querySelectorAll('thead th, thead td')).map(h => h.textContent?.trim() || ''),
          rows: Array.from(t.querySelectorAll('tbody tr, tr')).slice(0, 30).map(row =>
            Array.from(row.querySelectorAll('td, th')).map(cell => cell.textContent?.trim() || '').slice(0, 8)
          ).filter(r => r.length > 0),
        })).filter(t => t.rows.length > 0);

        structured.buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], a.btn'))
          .map(b => ({
            text: (b.textContent || (b as HTMLInputElement).value || '').trim().slice(0, 100),
            type: (b as HTMLElement).tagName === 'BUTTON' ? 'button' : 'link',
          }))
          .filter(b => b.text)
          .slice(0, 30);

        structured.alerts = Array.from(document.querySelectorAll(
          '.alert, .error, .success, .warning, .toast, [class*="error"], [class*="alert"], [class*="notification"], ' +
          '[class*="toast"], [class*="message"], [class*="feedback"], .invalid-feedback, .text-danger'
        )).map(a => ({
          text: (a.textContent || '').trim().slice(0, 300),
          class: a.className?.slice(0, 100) || '',
        })).filter(a => a.text);

        structured.lists = Array.from(document.querySelectorAll('ul, ol')).slice(0, 10).map(l => ({
          type: l.tagName,
          items: Array.from(l.querySelectorAll('li')).map(li => li.textContent?.trim().slice(0, 200) || '').filter(Boolean),
        })).filter(l => l.items.length > 0);

        const structuredData: Record<string, any>[] = [];
        for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
          try { structuredData.push(JSON.parse(script.textContent || '{}')); } catch {}
        }

        const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4'))
          .map(h => h.tagName + ': ' + (h.textContent || '').trim())
          .slice(0, 40);

        const links = Array.from(document.querySelectorAll('a[href]'))
          .map(a => ({ text: (a.textContent || '').trim(), href: (a as HTMLAnchorElement).href }))
          .filter(l => l.text)
          .slice(0, 50);

        structured.selects = Array.from(document.querySelectorAll('select')).slice(0, 20).map(s => ({
          name: s.name || s.id,
          value: s.value || '',
          options: Array.from(s.selectedOptions).map(o => o.text?.trim() || '').slice(0, 5),
        }));

        structured.cards = Array.from(document.querySelectorAll(
          '.card, [class*="card"], .panel, [class*="panel"], .ticket, .ticket-item'
        )).slice(0, 20).map(c => ({
          title: c.querySelector('.card-title, h3, h4, h5, .title, [class*="title"]')?.textContent?.trim()?.slice(0, 150) || '',
          text: (c.textContent || '').trim().slice(0, 500),
          class: c.className?.slice(0, 60) || '',
        })).filter(c => c.text);

        structured.breadcrumbs = Array.from(document.querySelectorAll(
          '.breadcrumb li, [class*="breadcrumb"] li, nav[aria-label*="breadcrumb"] li'
        )).map(b => b.textContent?.trim() || '').filter(Boolean).slice(0, 10);

        structured.tabs_found = Array.from(document.querySelectorAll(
          '.nav-tabs .nav-link, .tab a, [role="tab"], [class*="tab-header"]'
        )).map(t => t.textContent?.trim() || '').filter(Boolean).slice(0, 20);

        structured.badges = Array.from(document.querySelectorAll(
          '.badge, .tag, [class*="badge"], [class*="status"], [class*="label-info"]'
        )).map(b => b.textContent?.trim() || '').filter(Boolean).slice(0, 15);

        structured.user_info = (() => {
          const userEls = document.querySelectorAll(
            '.user-name, .profile-name, [class*="user-name"], [class*="profile-name"], ' +
            '.user-info, [class*="user-info"], [data-user], .nav-user'
          );
          const texts = Array.from(userEls).map(el => (el as HTMLElement).innerText?.trim().slice(0, 200)).filter(Boolean);
          const avatarAlt = Array.from(document.querySelectorAll(
            'img.avatar, img[class*="avatar"], img[class*="profile"]'
          )).map(img => (img as HTMLImageElement).alt).filter(Boolean);
          return [...texts, ...avatarAlt].slice(0, 5);
        })();

        return {
          title: document.title,
          url: window.location.href,
          text: document.body?.innerText?.slice(0, 20000) || "",
          metadata,
          structured,
          structuredData,
          headings,
          links,
        };
      },
    });

    return results[0]?.result || { title: "", url: "", text: "", metadata: {}, structured: {}, structuredData: [], headings: [], links: [] };
  } catch {
    return { title: "", url: "", text: "", metadata: {}, structured: {}, structuredData: [], headings: [], links: [] };
  }
}

async function handleAnalyzePage() {
  const pageData = await handleFetchPageText();
  if (!pageData.text) return { error: "Não foi possível ler o conteúdo da página" };

  return apiFetch("/analyze-page", {
    method: "POST",
    body: JSON.stringify({
      url: pageData.url || "",
      title: pageData.title || "",
      text: pageData.text,
      html: "",
    }),
  });
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

async function handleSubmitFeedback(payload: {
  conversation_id: string;
  response_text: string;
  rating: number;
  comment?: string;
}) {
  return apiFetch("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function handleOpenSidepanel() {
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (tab?.windowId) {
      await chrome.sidePanel.open({ windowId: tab.windowId });
      return { ok: true };
    }
    return { error: "No active tab" };
  } catch (e: any) {
    return { error: e.message };
  }
}
