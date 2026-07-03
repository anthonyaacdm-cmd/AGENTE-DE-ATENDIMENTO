import { describe, it, expect } from "vitest";

interface ConversationTurn {
  author: string;
  message: string;
  timestamp?: string;
}

function parseConversation(text: string): ConversationTurn[] {
  const lines = text.split("\n").filter((l) => l.trim());
  if (lines.length === 0) return [];
  const hasColon = lines.some((l) => l.includes(":"));
  if (!hasColon) {
    return [{ author: "Aluno", message: lines.join("\n") }];
  }
  return lines
    .filter((line) => line.includes(":"))
    .map((line) => {
      const i = line.indexOf(":");
      return {
        author: line.slice(0, i).trim(),
        message: line.slice(i + 1).trim(),
      };
    });
}

describe("parseConversation", () => {
  it("returns empty array for empty input", () => {
    expect(parseConversation("")).toEqual([]);
  });

  it("returns empty array for whitespace only", () => {
    expect(parseConversation("  \n  \n  ")).toEqual([]);
  });

  it("parses single line with colon", () => {
    const result = parseConversation("Aluno: Preciso de ajuda");
    expect(result).toHaveLength(1);
    expect(result[0].author).toBe("Aluno");
    expect(result[0].message).toBe("Preciso de ajuda");
  });

  it("parses multiple turns", () => {
    const result = parseConversation(
      "Aluno: Olá\nAtendente: Como posso ajudar?\nAluno: Problema na matrícula"
    );
    expect(result).toHaveLength(3);
    expect(result[1].author).toBe("Atendente");
    expect(result[2].message).toBe("Problema na matrícula");
  });

  it("handles lines without colon as single author", () => {
    const result = parseConversation(
      "Preciso de ajuda com minha matrícula\nNão consigo acessar o sistema"
    );
    expect(result).toHaveLength(1);
    expect(result[0].author).toBe("Aluno");
    expect(result[0].message).toContain("matrícula");
    expect(result[0].message).toContain("sistema");
  });

  it("filters out lines without colon when some lines have it", () => {
    const result = parseConversation(
      "Aluno: Mensagem 1\nlinha sem dois pontos\nAtendente: Resposta"
    );
    expect(result).toHaveLength(2);
    expect(result[0].author).toBe("Aluno");
    expect(result[1].author).toBe("Atendente");
  });

  it("handles colon in message content", () => {
    const result = parseConversation("Aluno: Horário: 14:30");
    expect(result[0].author).toBe("Aluno");
    expect(result[0].message).toBe("Horário: 14:30");
  });

  it("trims whitespace from author and message", () => {
    const result = parseConversation("  Aluno  :  minha mensagem  ");
    expect(result[0].author).toBe("Aluno");
    expect(result[0].message).toBe("minha mensagem");
  });

  it("handles multiple colons correctly", () => {
    const result = parseConversation("Aluno: Nota: 10.0. Problema: falta");
    expect(result[0].author).toBe("Aluno");
    expect(result[0].message).toBe("Nota: 10.0. Problema: falta");
  });
});

function confidenceLevel(score: number): string {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}

describe("confidenceLevel", () => {
  it("returns high for score >= 0.7", () => {
    expect(confidenceLevel(0.7)).toBe("high");
    expect(confidenceLevel(0.95)).toBe("high");
  });

  it("returns mid for score between 0.4 and 0.7", () => {
    expect(confidenceLevel(0.4)).toBe("mid");
    expect(confidenceLevel(0.69)).toBe("mid");
  });

  it("returns low for score < 0.4", () => {
    expect(confidenceLevel(0)).toBe("low");
    expect(confidenceLevel(0.39)).toBe("low");
  });

  it("handles edge cases", () => {
    expect(confidenceLevel(0.7)).toBe("high");
    expect(confidenceLevel(0.4)).toBe("mid");
    expect(confidenceLevel(0.399)).toBe("low");
  });
});
