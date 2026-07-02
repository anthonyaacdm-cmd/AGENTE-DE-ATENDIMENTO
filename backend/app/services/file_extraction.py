import io
import os
from app.services.rag_service import rag_service


ALLOWED_EXTENSIONS = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def get_extension(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    return ext


def is_supported(filename: str) -> bool:
    return get_extension(filename) in ALLOWED_EXTENSIONS


async def extract_text(filename: str, content: bytes) -> dict:
    ext = get_extension(filename)

    if ext == ".txt":
        return _extract_txt(content)
    elif ext == ".pdf":
        return _extract_pdf(content)
    elif ext == ".docx":
        return _extract_docx(content)
    elif ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        return await _extract_image(filename, content)
    else:
        return {"text": "", "format": ext, "error": "Formato não suportado"}


def _extract_txt(content: bytes) -> dict:
    text = content.decode("utf-8", errors="replace")
    return {"text": text, "format": "txt"}


def _extract_pdf(content: bytes) -> dict:
    try:
        import fitz
        if not content.startswith(b"%PDF"):
            return {"text": "", "format": "pdf", "error": "Arquivo não parece ser um PDF válido"}
        doc = fitz.open(stream=content, filetype="pdf")
        if doc.is_encrypted:
            doc.close()
            return {"text": "", "format": "pdf", "error": "PDF protegido por senha. Remova a senha e tente novamente."}
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n\n".join(pages).strip()
        if not text:
            return {"text": "", "format": "pdf", "error": "Não foi possível extrair texto deste PDF. Pode ser um PDF escaneado (imagem)."}
        return {"text": text, "format": "pdf"}
    except RuntimeError as e:
        return {"text": "", "format": "pdf", "error": f"Falha ao processar PDF: {e}. Verifique se o arquivo não está corrompido."}
    except Exception as e:
        return {"text": "", "format": "pdf", "error": f"Erro ao extrair PDF: {e}"}


def _extract_docx(content: bytes) -> dict:
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs]
        return {"text": "\n".join(paragraphs), "format": "docx"}
    except Exception as e:
        return {"text": "", "format": "docx", "error": f"Erro ao extrair DOCX: {e}"}


async def _extract_image(filename: str, content: bytes) -> dict:
    if not rag_service.is_ready() or not rag_service.llm:
        return {"text": "", "format": "image", "error": "IA não configurada para análise de imagem"}

    mime_type = ALLOWED_EXTENSIONS.get(get_extension(filename), "image/png")

    try:
        import base64
        b64 = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64}"

        from langchain_core.messages import HumanMessage
        msg = await rag_service.llm.ainvoke([
            HumanMessage(content=[
                {"type": "text", "text": "Descreva detalhadamente o conteúdo desta imagem. Extraia todo o texto visível e descreva imagens, tabelas ou gráficos presentes."},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ])
        ])
        return {"text": msg.content, "format": "image", "filename": filename}
    except Exception as e:
        return {"text": "", "format": "image", "error": f"Erro ao analisar imagem: {e}"}
