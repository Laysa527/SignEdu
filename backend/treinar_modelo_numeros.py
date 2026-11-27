"""
NÚMEROS (0 a 9): treinar o Random Forest dos números como sinais PARADOS.

Em LIBRAS os números 0 a 9 não precisam de movimento: o que diz o número é o formato
da mão. Por isso eles saíram do modelo de movimento e ganharam um modelo próprio, com
as mesmas 63 características das letras (só os 21 pontos da mão).

De onde vêm os exemplos: dos vídeos dos números gravados pelo especialista em LIBRAS
(os mesmos clipes da base de movimento, um vídeo por repetição). Em cada vídeo:
  1. o MediaPipe lê os quadros (igual à câmera: espelhado e recortado em 4:3);
  2. escolhe a mão que faz o sinal (escolher_mao_na_sequencia, a mesma da câmera);
  3. fica só com os quadros em que essa mão está levantada (metade mais alta) e
     PARADA (menor deslocamento da palma), ou seja, o sinal "segurado";
  4. guarda até QUADROS_POR_VIDEO quadros desses.

Teste: validação cruzada por VÍDEO (K=5): os quadros de um mesmo vídeo ficam sempre
juntos, no treino ou no teste, pra não "colar" de um quadro quase igual.
Se os nomes dos vídeos tiverem _D_ e _I_ (luz direta e indireta), também treina
com uma luz e testa com a outra.

Como rodar (pasta com uma subpasta por número: 0/, 1/, ... 9/ com os .mp4):
    python treinar_modelo_numeros.py caminho/da/pasta_dos_clipes

Salva modelo_numeros.joblib (o app.py usa) e dados/relatorio_numeros.txt.
"""

import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold

from detector_maos import (DetectorDeMaos, _palma, _tamanho_mao, escolher_mao_na_sequencia,
                           pontos_para_caracteristicas)

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_MODELO = PASTA_PROJETO / "modelo_numeros.joblib"
ARQUIVO_RELATORIO = PASTA_PROJETO / "dados" / "relatorio_numeros.txt"
NUMEROS = [str(n) for n in range(10)]
QUADROS_POR_VIDEO = 10
K_FOLDS = 5


def novo_modelo():
    return RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)


def quadros_parados(quadros):
    """Escolhe os quadros em que a mão do sinal está levantada e parada."""
    seq = escolher_mao_na_sequencia(quadros)
    indices = [i for i, q in enumerate(seq) if q]
    if len(indices) < 4:
        return []
    alturas = np.array([-seq[i]["pontos"][0]["y"] for i in indices])
    limite = np.percentile(alturas, 40)
    candidatos = []
    for k, i in enumerate(indices):
        if alturas[k] < limite:
            continue
        vizinhos = [j for j in (i - 1, i + 1) if 0 <= j < len(seq) and seq[j]]
        if not vizinhos:
            continue
        proporcao = float(seq[i].get("proporcao") or 4 / 3)
        palma = _palma(seq[i]["pontos"], proporcao)
        tamanho = _tamanho_mao(seq[i]["pontos"], proporcao)
        deslocamento = np.mean([np.linalg.norm(_palma(seq[j]["pontos"], proporcao) - palma)
                                for j in vizinhos]) / tamanho
        candidatos.append((deslocamento, i))
    return [seq[i] for _, i in sorted(candidatos)[:QUADROS_POR_VIDEO]]


def avaliar(X, y, videos, treino, teste):
    """Treina em 'treino', testa em 'teste'. Devolve (acerto por quadro, acerto por vídeo, previsões)."""
    modelo = novo_modelo().fit(X[treino], y[treino])
    previsto = modelo.predict(X[teste])
    votos = defaultdict(list)
    for i, p in zip(np.where(teste)[0], previsto):
        votos[videos[i]].append((p, y[i]))
    por_video = np.mean([Counter(p for p, _ in v).most_common(1)[0][0] == v[0][1] for v in votos.values()])
    return float(np.mean(previsto == y[teste])), float(por_video), previsto


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python treinar_modelo_numeros.py pasta_dos_clipes")
    pasta = Path(sys.argv[1])

    detector = DetectorDeMaos(PASTA_PROJETO / "hand_landmarker.task",
                              caminho_corpo=PASTA_PROJETO / "pose_landmarker.task",
                              caminho_rosto=PASTA_PROJETO / "face_landmarker.task")
    X, y, videos = [], [], []
    inicio = time.time()
    for numero in NUMEROS:
        arquivos = sorted((pasta / numero).glob("*.mp4"))
        for arquivo in arquivos:
            quadros = detector._ler_video(arquivo, True, com_corpo=False)
            for q in quadros_parados(quadros):
                X.append(pontos_para_caracteristicas(q["pontos"], q["lado"]))
                y.append(numero)
                videos.append(arquivo.stem)
        print(f"  {numero}: {len(arquivos)} vídeos", flush=True)
    detector.fechar()
    X, y, videos = np.array(X), np.array(y), np.array(videos)
    print(f"{len(y)} quadros de {len(set(videos))} vídeos ({time.time() - inicio:.0f} s)")

    linhas = [f"Modelo dos números (sinais parados) - {time.strftime('%d/%m/%Y %H:%M')}",
              f"Quadros: {len(y)} | vídeos: {len(set(videos))} | até {QUADROS_POR_VIDEO} quadros por vídeo",
              "Quadros por número: " + ", ".join(f"{n}={c}" for n, c in sorted(Counter(y).items())), ""]

    # Validação cruzada por vídeo
    grupos = np.unique(videos, return_inverse=True)[1]
    k = min(K_FOLDS, min(Counter(v.split("_")[0] for v in set(videos)).values()))
    acertos_q, acertos_v = [], []
    previsto_total = np.empty(len(y), dtype=object)
    for treino_i, teste_i in StratifiedGroupKFold(k, shuffle=True, random_state=42).split(X, y, grupos):
        treino = np.zeros(len(y), bool); treino[treino_i] = True
        a_q, a_v, prev = avaliar(X, y, videos, treino, ~treino)
        acertos_q.append(a_q); acertos_v.append(a_v); previsto_total[~treino] = prev
    linhas.append(f"Validação cruzada por vídeo (K={k}): {np.mean(acertos_q) * 100:.1f}% por quadro "
                  f"(desvio {np.std(acertos_q) * 100:.1f}%), {np.mean(acertos_v) * 100:.1f}% por vídeo")
    largura = 4
    linhas.append("\nMatriz de confusão da validação cruzada (linha = certo, coluna = previsto):")
    linhas.append(" " * largura + " " + " ".join(f"{n:>{largura}}" for n in NUMEROS))
    for n, linha in zip(NUMEROS, confusion_matrix(y, previsto_total.astype(str), labels=NUMEROS)):
        linhas.append(f"{n:>{largura}} " + " ".join(f"{c:>{largura}}" for c in linha))

    # Uma luz contra a outra (se os nomes tiverem _D_ / _I_)
    luz = np.array(["D" if "_D_" in v else "I" if "_I_" in v else "" for v in videos])
    if {"D", "I"} <= set(luz):
        linhas.append("\nTreino com uma luz e teste com a outra:")
        for a, b in (("D", "I"), ("I", "D")):
            a_q, a_v, _ = avaliar(X, y, videos, luz == a, luz == b)
            faltam = sorted(set(y[luz == b]) - set(y[luz == a]))
            nota = f" (no treino faltou: {', '.join(faltam)})" if faltam else ""
            linhas.append(f"  {a} -> {b}: {a_q * 100:.1f}% por quadro, {a_v * 100:.1f}% por vídeo{nota}")

    modelo = novo_modelo().fit(X, y)
    joblib.dump(modelo, ARQUIVO_MODELO, compress=3)
    ARQUIVO_RELATORIO.parent.mkdir(exist_ok=True)
    ARQUIVO_RELATORIO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))
    print(f"\nModelo salvo em {ARQUIVO_MODELO}\nRelatório salvo em {ARQUIVO_RELATORIO}")


if __name__ == "__main__":
    main()
