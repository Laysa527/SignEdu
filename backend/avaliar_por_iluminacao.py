"""
Sinais com movimento: teste "por iluminação" (mais rigoroso que o do treinar_modelo_movimento.py).

O treinar_modelo_movimento.py separa 20% dos vídeos AO ACASO para o teste. Como as 12 repetições
de cada sinal foram gravadas em sequência, repetições quase iguais caem no treino e no teste, e
o resultado sai otimista.

Aqui o modelo é treinado com os vídeos de UMA gravação (luz direta) e testado com os da OUTRA
(luz indireta), e depois o contrário. São vídeos gravados em outro momento, com outra luz e outra
posição de descanso das mãos, que o modelo nunca viu. A média ponderada dos dois é o número mais
honesto do desempenho com vídeos novos.

O nome de cada clipe precisa ter a luz: <sinal>_D_<n>.mp4 (luz direta) ou <sinal>_I_<n>.mp4
(luz indireta). O resultado fica em dados/relatorio_por_iluminacao.txt.

Como rodar (depois do extrair_sequencias.py):
    python avaliar_por_iluminacao.py
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score

from detector_maos import N_CARACTERISTICAS_MAO, grupo_do_movimento
from treinar_modelo_movimento import novo_modelo

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_DADOS = PASTA_PROJETO / "dados" / "sequencias.csv"
ARQUIVO_RELATORIO = PASTA_PROJETO / "dados" / "relatorio_por_iluminacao.txt"


ARQUIVO_DADOS_MAO = PASTA_PROJETO / "dados" / "sequencias_mao.csv"
CERTEZA_MINIMA = 0.3     # igual a banco.CERTEZA_MINIMA_MOVIMENTO


def carregar(caminho):
    sinais, luzes, linhas = [], [], []
    with open(caminho, encoding="utf-8") as arquivo:
        leitor = csv.reader(arquivo)
        next(leitor)
        for linha in leitor:
            if linha[0].isdigit():       # números: modelo parado próprio (treinar_modelo_numeros.py)
                continue
            partes = Path(linha[1]).stem.split("_")
            if len(partes) < 3 or partes[-2] not in ("D", "I"):
                continue
            sinais.append(linha[0])
            luzes.append(partes[-2])
            linhas.append([float(v) for v in linha[2:]])
    return np.array(linhas, dtype=np.float32), np.array(sinais), np.array(luzes)


def avaliar(X, y, luz, titulo, texto):
    """Treina com uma luz e testa com a outra. "Vale" = o sinal certo é o mais provável e tem
    pelo menos CERTEZA_MINIMA (a mesma regra do site)."""
    certos = valem = total = 0
    acerto_sinal = defaultdict(list)
    confusoes = Counter()
    partes = []
    for treino, teste in (("D", "I"), ("I", "D")):
        a, b = luz == treino, luz == teste
        conhecidos = np.isin(y[b], y[a])           # sinal que não existe no treino não entra no teste
        modelo = novo_modelo().fit(X[a], y[a])
        probabilidades = modelo.predict_proba(X[b][conhecidos])
        previsto = modelo.classes_[probabilidades.argmax(1)]
        real = y[b][conhecidos]
        acertou = previsto == real
        certos += int(acertou.sum())
        valem += int((acertou & (probabilidades.max(1) >= CERTEZA_MINIMA)).sum())
        total += len(real)
        partes.append(f"{accuracy_score(real, previsto) * 100:.1f}% (treino {treino}, teste {teste})")
        for r, p, ok in zip(real, previsto, acertou):
            acerto_sinal[r].append(ok)
            if not ok:
                confusoes[(r, p)] += 1
    texto += ["", titulo,
              f"  Sinal certo como o mais provável: {certos / total * 100:.1f}% ({total} vídeos; " + ", ".join(partes) + ")",
              f"  Vale como acerto no site (mais provável e >= {CERTEZA_MINIMA:.0%}): {valem / total * 100:.1f}%",
              "  Acerto por sinal: " + ", ".join(f"{s} {np.mean(v) * 100:.0f}%" for s, v in
                                                 sorted(acerto_sinal.items(), key=lambda kv: np.mean(kv[1]))),
              "  Confusões mais comuns: " + ", ".join(f"{r} -> {p} ({n})" for (r, p), n in confusoes.most_common(6))]


def main():
    texto = ["Teste por iluminação (treina com uma gravação, testa com a outra)",
             "Cada grupo é avaliado só entre os sinais dele, como no site (que sabe qual sinal a pessoa escolheu)."]
    X, y, luz = carregar(ARQUIVO_DADOS)
    if len(set(luz)) < 2:
        raise SystemExit("Preciso de clipes das duas luzes (_D_ e _I_) no nome dos arquivos.")
    grupos = np.array([grupo_do_movimento(s) for s in y])
    if ARQUIVO_DADOS_MAO.exists():
        Xm, ym, luzm = carregar(ARQUIVO_DADOS_MAO)
    else:
        Xm, ym, luzm = X[:, :N_CARACTERISTICAS_MAO], y, luz
    grupos_m = np.array([grupo_do_movimento(s) for s in ym])

    filtro = grupos_m == "Alfabeto"
    avaliar(Xm[filtro], ym[filtro], luzm[filtro], "Letras com movimento (H, J, K, X, Z, Ç) - só a mão:", texto)
    filtro = grupos == "Saudações"
    avaliar(X[filtro], y[filtro], luz[filtro], "Saudações - mão + corpo + rosto:", texto)
    filtro = grupos_m == "Saudações"
    avaliar(Xm[filtro], ym[filtro], luzm[filtro], "Saudações - só a mão (quando o corpo/rosto não aparecem):", texto)

    ARQUIVO_RELATORIO.parent.mkdir(exist_ok=True)
    ARQUIVO_RELATORIO.write_text("\n".join(texto) + "\n", encoding="utf-8")
    print("\n".join(texto))


if __name__ == "__main__":
    main()
