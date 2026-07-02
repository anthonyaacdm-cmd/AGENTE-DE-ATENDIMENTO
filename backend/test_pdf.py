import httpx
import fitz  # PyMuPDF

BASE = 'https://agente-de-atendimento.onrender.com/api/v1'
client = httpx.Client(timeout=30)

# Create a simple PDF using fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((50, 100), "Teste de PDF para extracao", fontsize=14)
pdf_bytes = doc.write()
doc.close()

# Upload
r = client.post(f'{BASE}/knowledge/extract', files={'file': ('test.pdf', pdf_bytes, 'application/pdf')})
print('PDF test:', r.status_code, r.json())

# Test TXT
r = client.post(f'{BASE}/knowledge/extract', files={'file': ('test.txt', b'Hello world', 'text/plain')})
print('TXT test:', r.status_code, r.json())
