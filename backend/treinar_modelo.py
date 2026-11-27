"""
Passo 2 do treino: treinar o Random Forest com os pontos da mão.

Lê o dados/landmarks.csv (gerado pelo extrair_landmarks.py), treina o
Random Forest com as fotos de "training", testa com as fotos de "test"
e salva o modelo em modelo_letras.joblib (é esse arquivo que o app.py usa).

Antes do treino final, faz uma validação cruzada estratificada com K=5 (K-fold)
só nas fotos de "training" (as de "test" ficam guardadas pro teste final).

Também salva um relatório com o acerto de cada letra em
dados/relatorio_treino.txt, bom pra colocar no TCC.

Como rodar:
    python treinar_modelo.py
"""

import csv
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score

from detector_maos import pontos_para_caracteristicas

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_DADOS = PASTA_PROJETO / "dados" / "landmarks.csv"
ARQUIVO_MODELO = PASTA_PROJETO / "modelo_letras.joblib"
ARQUIVO_RELATORIO = PASTA_PROJETO / "dados" / "relatorio_treino.txt"

K_FOLDS = 5   # quantidade de partes da validação cruzada


def carregar_dados():
    """Lê o CSV e separa em treino e teste (X = características, y = letra)."""
    dados = {"training": ([], []), "test": ([], [])}

    with open(ARQUIVO_DADOS, encoding="utf-8") as arquivo_csv:
        for linha in csv.DictReader(arquivo_csv):
            pontos = [
                {"x": float(linha[f"x{i}"]), "y": float(linha[f"y{i}"]), "z": float(linha[f"z{i}"])}
                for i in range(21)
            ]
            X, y = dados[linha["conjunto"]]
            X.append(pontos_para_caracteristicas(pontos, linha["lado"]))
            y.append(linha["letra"])

    X_treino, y_treino = np.array(dados["training"][0]), np.array(dados["training"][1])
    X_teste, y_teste = np.array(dados["test"][0]), np.array(dados["test"][1])
    return X_treino, y_treino, X_teste, y_teste


def main():
    if not ARQUIVO_DADOS.exists():
        raise FileNotFoundError(
            f"{ARQUIVO_DADOS} não encontrado. Rode antes: python extrair_landmarks.py"
        )

    X_treino, y_treino, X_teste, y_teste = carregar_dados()
    print(f"Treino: {len(X_treino)} exemplos | Teste: {len(X_teste)} exemplos")
    print(f"Letras: {', '.join(sorted(set(y_treino)))}")

    modelo = RandomForestClassifier(
        n_estimators=200,   # quantidade de árvores
        n_jobs=-1,          # usa todos os núcleos do processador
        random_state=42,    # pra dar o mesmo resultado toda vez
    )

    # Validação cruzada: o treino é dividido em 5 partes (mantendo a proporção de cada
    # letra). Cada parte vira "teste" uma vez, e o modelo treina nas outras 4.
    print(f"\nValidação cruzada (K-fold estratificado, K={K_FOLDS})...")
    inicio = time.time()
    divisao = StratifiedKFold(n_splits=K_FOLDS, shuffle=True, random_state=42)
    acuracias_cv = cross_val_score(modelo, X_treino, y_treino, cv=divisao, scoring="accuracy")
    for numero, valor in enumerate(acuracias_cv, start=1):
        print(f"  Fold {numero}: {valor:.1%}")
    print(f"  Média: {acuracias_cv.mean():.2%} (desvio padrão {acuracias_cv.std():.2%}) "
          f"- {time.time() - inicio:.1f} s")

    inicio = time.time()
    modelo.fit(X_treino, y_treino)
    print(f"Treinado em {time.time() - inicio:.1f} s")

    previsto = modelo.predict(X_teste)
    acuracia = accuracy_score(y_teste, previsto)
    relatorio = classification_report(y_teste, previsto, digits=3)
    letras = list(modelo.classes_)
    matriz = confusion_matrix(y_teste, previsto, labels=letras)

    print(f"\nAcurácia no teste: {acuracia:.1%}\n")
    print(relatorio)

    joblib.dump(modelo, ARQUIVO_MODELO, compress=3)
    print(f"Modelo salvo em {ARQUIVO_MODELO}")

    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as arquivo:
        arquivo.write("Random Forest - reconhecimento do alfabeto em Libras\n")
        arquivo.write(f"Exemplos de treino: {len(X_treino)}\n")
        arquivo.write(f"Exemplos de teste: {len(X_teste)}\n")
        arquivo.write(f"Acurácia no teste: {acuracia:.1%}\n\n")
        arquivo.write(f"Validação cruzada (K-fold estratificado, K={K_FOLDS}, só nos dados de treino):\n")
        for numero, valor in enumerate(acuracias_cv, start=1):
            arquivo.write(f"  Fold {numero}: {valor:.2%}\n")
        arquivo.write(f"  Média: {acuracias_cv.mean():.2%} (desvio padrão {acuracias_cv.std():.2%})\n\n")
        arquivo.write("Acerto por letra (precision, recall, f1-score):\n")
        arquivo.write(relatorio)
        arquivo.write("\nMatriz de confusão (linha = letra certa, coluna = letra prevista):\n")
        arquivo.write("    " + " ".join(f"{l:>4}" for l in letras) + "\n")
        for letra, linha in zip(letras, matriz):
            arquivo.write(f"{letra:>3} " + " ".join(f"{n:>4}" for n in linha) + "\n")
    print(f"Relatório salvo em {ARQUIVO_RELATORIO}")


if __name__ == "__main__":
    main()
