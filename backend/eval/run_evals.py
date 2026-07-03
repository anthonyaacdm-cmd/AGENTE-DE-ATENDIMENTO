import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from app.services.rag_service import rag_service
from app.services.qdrant_service import qdrant_service
from app.models.schemas import ConversationTurn


EVAL_FILE = os.path.join(os.path.dirname(__file__), "eval_dataset.jsonl")


async def evaluate():
    if not rag_service.is_ready():
        print("ERRO: IA não configurada. Verifique GEMINI_API_KEY.")
        sys.exit(1)

    if not qdrant_service.is_ready():
        print("ERRO: Qdrant não conectado.")
        sys.exit(1)

    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    total = len(questions)
    correct = 0
    scores = []

    print(f"Executando {total} questões de avaliação...\n")

    for q in questions:
        conversation = [ConversationTurn(author="Aluno", message=q["question"])]
        result = await rag_service.generate_response(conversation)
        response = (result.suggested_response or "").lower()
        expected = q["expected_answer"].lower()
        has_info = any(phrase in response for phrase in expected.split() if len(phrase) > 4)
        has_expected = has_info or expected[:30] in response

        score = 1.0 if has_expected else 0.0
        scores.append(score)
        if has_expected:
            correct += 1

        status = "✓" if has_expected else "✗"
        confidence = result.confidence
        sources = result.sources or []
        print(f"  {status} [{q['category']}] {q['question']}")
        print(f"     Confiança: {confidence:.3f} | Fontes: {len(sources)} | Acerto: {score:.0f}")

    accuracy = correct / total * 100
    avg_conf = sum(scores) / len(scores) * 100
    print(f"\n{'='*50}")
    print(f"RESULTADO FINAL:")
    print(f"  Acurácia: {accuracy:.1f}% ({correct}/{total})")
    print(f"  Confiança média: {avg_conf:.1f}%")
    print(f"{'='*50}")

    return accuracy


if __name__ == "__main__":
    asyncio.run(evaluate())
