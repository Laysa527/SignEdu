"""
Sinais PARADOS (letras e números): ensinar a opção "Nenhum sinal".

Problema: os modelos das letras e dos números só conheciam os sinais certos. Qualquer
formato de mão virava "o sinal mais parecido" (ex.: 4 dedos para baixo virava M, dois
dedos esticados viravam 5, a mão aberta para cima virava 6).

Solução: além dos exemplos certos de sempre (fotos da base para as letras, vídeos do
especialista para os números), o treino recebe a classe "Nenhum sinal" com exemplos
de formatos ERRADOS gravados com a câmera de verdade no modo de coleta do site
(praticar.html?teste=1, arquivo dados/coleta_testes.jsonl). Cada quadro errado entra
também com 4 cópias com um pequeno tremor nos pontos, e o peso total da classe
"Nenhum sinal" é igual ao de um sinal médio.

Os quadros "certo" da coleta NUNCA entram no treino: servem só para testar se o sinal
certo continua sendo reconhecido.

Validação: os quadros errados de cada sinal são divididos em 3 pedaços seguidos no
tempo; treina com 2 e testa com o outro. "Vale" segue a regra do site: 8 quadros
seguidos reconhecidos como o sinal certo com certeza >= 50%.

Como rodar (na pasta backend):
    python treinar_nenhum_parados.py
Precisa de: dados/landmarks.csv (letras), dados/numeros_quadros.csv (números) e
dados/coleta_testes.jsonl (coleta). Os modelos antigos ficam salvos com _ANTES_nenhum.
"""
import csv
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from banco import CERTEZA_MINIMA
from detector_maos import SEM_SINAL, polegar_dobrado, pontos_para_caracteristicas

PASTA = Path(__file__).resolve().parent
DADOS = PASTA / "dados"
QUADROS_PARA_VALER = 8
COPIAS_COM_TREMOR = 4
TREMOR = 0.02            # em "tamanhos de mão"
GRUPOS = {
    "letras": {"modelo": PASTA / "modelo_letras.joblib", "sinais": set("ABCDEFGILMNOPQRSTUVWY")},
    "numeros": {"modelo": PASTA / "modelo_numeros.joblib", "sinais": set("0123456789")},
}


def novo_modelo():
    return RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)


def ler_letras():
    X, y, conjunto = [], [], []
    with open(DADOS / "landmarks.csv", encoding="utf-8") as arquivo:
        for linha in csv.DictReader(arquivo):
            pontos = [{"x": float(linha[f"x{i}"]), "y": float(linha[f"y{i}"]), "z": float(linha[f"z{i}"])}
                      for i in range(21)]
            X.append(pontos_para_caracteristicas(pontos, linha["lado"]))
            y.append(linha["letra"])
            conjunto.append(linha["conjunto"])
    return np.array(X), np.array(y), np.array(conjunto)


def ler_numeros():
    X, y = [], []
    with open(DADOS / "numeros_quadros.csv", encoding="utf-8") as arquivo:
        for linha in csv.reader(arquivo):
            y.append(linha[0])
            X.append([float(v) for v in linha[3:]])
    return np.array(X), np.array(y)


def ler_coleta(sinais):
    registros = []
    with open(DADOS / "coleta_testes.jsonl", encoding="utf-8") as arquivo:
        for linha in arquivo:
            r = json.loads(linha)
            if r["tipo"] == "parado" and r["alvo"] in sinais and r.get("maos"):
                registros.append(r)
    return sorted(registros, key=lambda r: r["momento"])


def mao_do_sinal(registro):
    """A mão mais alta da imagem (a outra costuma estar parada, embaixo)."""
    mao = min(registro["maos"], key=lambda m: m["pontos"][0]["y"])
    return pontos_para_caracteristicas(mao["pontos"], mao["lado"])


def com_tremor(caracteristicas, gerador):
    copias = [caracteristicas]
    for _ in range(COPIAS_COM_TREMOR):
        pontos = caracteristicas.reshape(21, 3).copy()
        pontos[:, :2] += gerador.normal(0, TREMOR, (21, 2))
        pontos[0] = 0.0
        copias.append(pontos.flatten())
    return copias


def treinar(X, y, errados):
    gerador = np.random.default_rng(0)
    negativos = [v for r in errados for v in com_tremor(mao_do_sinal(r), gerador)]
    peso_nenhum = (len(y) / len(set(y))) / max(len(negativos), 1)
    pesos = np.r_[np.ones(len(y)), np.full(len(negativos), peso_nenhum)]
    X_total = np.r_[X, np.array(negativos)] if negativos else X
    y_total = np.r_[y, [SEM_SINAL] * len(negativos)]
    return novo_modelo().fit(X_total, y_total, sample_weight=pesos)


def prever(modelo, registro, grupo):
    """Igual ao servidor: cada mão da imagem dá um palpite e vale o de maior certeza."""
    melhor = (None, -1.0)
    for mao in registro["maos"]:
        caracteristicas = pontos_para_caracteristicas(mao["pontos"], mao["lado"])
        p = modelo.predict_proba([caracteristicas])[0]
        sinal, certeza = str(modelo.classes_[p.argmax()]), float(p.max())
        if grupo == "letras" and sinal == "B" and not polegar_dobrado(caracteristicas):
            certeza = 0.0
        if certeza > melhor[1]:
            melhor = (sinal, certeza)
    return melhor


def vale(acertos):
    """Regra do servidor: +1 a cada quadro certo, -2 a cada errado; vale ao chegar em 8."""
    contador = 0
    for certo in acertos:
        contador = contador + 1 if certo else max(0, contador - 2)
        if contador >= QUADROS_PARA_VALER:
            return True
    return False


def validar(X, y, registros, grupo, linhas):
    errados = defaultdict(list)
    for r in registros:
        if r["rotulo"] == "errado":
            errados[r["alvo"]].append(r)
    pedaco = {id(r): i * 3 // len(lista) for lista in errados.values() for i, r in enumerate(lista)}
    resultado = defaultdict(list)
    for dobra in range(3):
        modelo = treinar(X, y, [r for r in registros if r["rotulo"] == "errado" and pedaco[id(r)] != dobra])
        for r in registros:
            if r["rotulo"] == "errado" and pedaco[id(r)] != dobra:
                continue
            if r["rotulo"] == "certo" and dobra > 0:
                continue
            sinal, certeza = prever(modelo, r, grupo)
            chave = (r["alvo"], r["rotulo"], dobra if r["rotulo"] == "errado" else 0)
            resultado[chave].append(sinal == r["alvo"] and certeza >= CERTEZA_MINIMA)
    juntos, valeu = defaultdict(list), defaultdict(list)
    for (alvo, rotulo, _), acertos in resultado.items():
        juntos[(alvo, rotulo)] += acertos
        valeu[(alvo, rotulo)].append(vale(acertos))
    for (alvo, rotulo) in sorted(juntos):
        linhas.append(f"  {alvo} feito {rotulo.upper():6s}: quadros aceitos {np.mean(juntos[(alvo, rotulo)]):5.0%}"
                      f" | valeu (8 seguidos) em {sum(valeu[(alvo, rotulo)])} de {len(valeu[(alvo, rotulo)])} pedaços")


def main():
    linhas = [f"Sinais parados com a classe \"Nenhum sinal\" - {time.strftime('%d/%m/%Y %H:%M')}", ""]
    X_letras, y_letras, conjunto = ler_letras()
    X_numeros, y_numeros = ler_numeros()
    bases = {"letras": (X_letras[conjunto == "training"], y_letras[conjunto == "training"]),
             "numeros": (X_numeros, y_numeros)}

    for grupo, info in GRUPOS.items():
        X, y = bases[grupo]
        registros = ler_coleta(info["sinais"])
        errados = [r for r in registros if r["rotulo"] == "errado"]
        linhas.append(f"{grupo.upper()}: {len(y)} exemplos certos da base + {len(errados)} quadros errados da "
                      f"coleta (x{COPIAS_COM_TREMOR + 1} com tremor) como \"Nenhum sinal\"")
        linhas.append("Validação com a câmera real (errado: 3 pedaços no tempo; certo: nunca treinado):")
        validar(X, y, registros, grupo, linhas)

        modelo = treinar(X, y, errados)
        if grupo == "letras":
            antigo = joblib.load(info["modelo"])
            teste = conjunto == "test"
            linhas.append(f"Base de teste das letras ({teste.sum()} fotos): antes {np.mean(antigo.predict(X_letras[teste]) == y_letras[teste]):.2%}, "
                          f"agora {np.mean(modelo.predict(X_letras[teste]) == y_letras[teste]):.2%}")
        copia = info["modelo"].with_name(info["modelo"].stem + "_ANTES_nenhum.joblib")
        if not copia.exists():
            shutil.copy(info["modelo"], copia)
        joblib.dump(modelo, info["modelo"], compress=3)
        linhas.append(f"Salvo em {info['modelo'].name} (o anterior ficou em {copia.name})")
        linhas.append("")
        print("\n".join(linhas[-12:]), flush=True)

    (DADOS / "relatorio_nenhum_parados.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))


if __name__ == "__main__":
    main()
