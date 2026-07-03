import io
import os
import logging
from io import BytesIO
from app.services.rag_service import rag_service
from app.core.config import settings
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

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

MAX_IMAGE_DIMENSION = 2048
VISION_MAX_TOKENS = 4096

_vision_llm: ChatGoogleGenerativeAI | None = None


def _get_vision_llm() -> ChatGoogleGenerativeAI:
    global _vision_llm
    if _vision_llm is None:
        _vision_llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.1,
            max_tokens=VISION_MAX_TOKENS,
        )
    return _vision_llm


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


def _resize_image(content: bytes, max_dim: int = MAX_IMAGE_DIMENSION) -> bytes:
    """Redimensiona a imagem se exceder max_dim para evitar payloads muito grandes."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(content))
        if max(img.width, img.height) <= max_dim:
            return content
        ratio = max_dim / max(img.width, img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        fmt = img.format or "PNG"
        if fmt.upper() == "GIF":
            fmt = "PNG"
        img.save(buf, format=fmt, optimize=True)
        resized = buf.getvalue()
        logger.info(f"Imagem redimensionada: {len(content)} -> {len(resized)} bytes")
        return resized
    except Exception as e:
        logger.warning(f"Não foi possível redimensionar imagem: {e}")
        return content


async def _extract_image(filename: str, content: bytes) -> dict:
    if not rag_service.is_ready() or not rag_service.llm:
        return {"text": "", "format": "image", "error": "IA não configurada para análise de imagem"}

    mime_type = ALLOWED_EXTENSIONS.get(get_extension(filename), "image/png")

    try:
        content = _resize_image(content)
        import base64
        b64 = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64}"

        from langchain_core.messages import HumanMessage

        vision_llm = _get_vision_llm()
        msg = await vision_llm.ainvoke([
            HumanMessage(content=[
                {
                    "type": "text",
                    "text": (
                        "Esta é uma captura de tela de uma conversa de atendimento. "
                        "EXTRAIA TODO O TEXTO VISÍVEL NA IMAGEM, incluindo nome do autor, "
                        "mensagens, horários e qualquer outro texto. Mantenha a estrutura "
                        "da conversa preservando quem disse o que. "
                        "Responda APENAS com o texto extraído, sem comentários adicionais."
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_uri}},
            ])
        ])
        extracted = msg.content.strip()
        if not extracted:
            return {"text": "", "format": "image", "error": "Nenhum texto identificado na imagem"}
        return {"text": extracted, "format": "image", "filename": filename}
    except Exception as e:
        logger.error(f"Erro ao analisar imagem {filename}: {e}", exc_info=True)
        return {"text": "", "format": "image", "error": f"Erro ao analisar imagem: {e}"}
