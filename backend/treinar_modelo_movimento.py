"""
Sinais com MOVIMENTO, passo 2 do treino: treinar o Random Forest com os vídeos.

Lê o dados/sequencias.csv (gerado pelo extrair_sequencias.py: mãos + corpo + rosto de cada
vídeo), separa 20% dos vídeos
pro teste final (escolhidos de forma estratificada: cada sinal entra na mesma
proporção), faz validação cruzada estratificada (K-fold, K=5) só nos outros 80%,
treina o modelo final e salva em modelo_movimento.joblib (o app.py usa esse arquivo).

Os números (0 a 9) ficam de fora: em LIBRAS eles são sinais parados e têm um modelo
próprio (treinar_modelo_numeros.py). Aqui ficam só os sinais que precisam de movimento.

Se algum sinal tiver poucos vídeos, o script se adapta (menos folds, ou sem teste
separado) e avisa no relatório. Com poucos vídeos o resultado é só uma ideia:
grave mais vídeos pra ter números confiáveis.

Também salva um relatório em dados/relatorio_movimento.txt, bom pra colocar no TCC.

Como rodar:
    python treinar_modelo_movimento.py
"""

import csv
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

import pickle

from aumento_dados import exemplos_sem_sinal, janelas, versoes_para_treino
from detector_maos import (N_CARACTERISTICAS_MAO, SEM_SINAL, grupo_do_movimento, movimento_minimo,
                           quantidade_de_movimento, sequencia_para_caracteristicas)

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_DADOS = PASTA_PROJETO / "dados" / "sequencias.csv"
ARQUIVO_MODELO = PASTA_PROJETO / "modelo_movimento.joblib"
ARQUIVO_RELATORIO = PASTA_PROJETO / "dados" / "relatorio_movimento.txt"
ARQUIVO_GRUPOS = PASTA_PROJETO / "modelo_movimento_grupos.joblib"
ARQUIVO_DADOS_MAO = PASTA_PROJETO / "dados" / "sequencias_mao.csv"
ARQUIVO_DETECCOES = PASTA_PROJETO / "dados" / "deteccoes_videos.pkl"

K_FOLDS = 5          # quantidade de partes da validação cruzada
PROPORCAO_TESTE = 0.2
MIN_VIDEOS_POR_SINAL = 2


def novo_modelo():
    return RandomForestClassifier(
        n_estimators=200,   # quantidade de árvores
        n_jobs=-1,          # usa todos os núcleos do processador
        random_state=42,    # pra dar o mesmo resultado toda vez
    )


def main():
    if not ARQUIVO_DADOS.exists():
        raise FileNotFoundError(
            f"{ARQUIVO_DADOS} não encontrado. Rode antes: python extrair_sequencias.py"
        )

    linhas_X, linhas_y = [], []
    with open(ARQUIVO_DADOS, encoding="utf-8") as arquivo_csv:
        for linha in csv.reader(arquivo_csv):
            if linha[0] == "sinal":      # cabeçalho
                continue
            if linha[0].isdigit():       # números são sinais parados (treinar_modelo_numeros.py)
                continue
            linhas_y.append(linha[0])
            linhas_X.append([float(v) for v in linha[2:]])
    X = np.array(linhas_X, dtype=np.float32)
    y = np.array(linhas_y)

    contagem = Counter(y)
    print(f"{len(y)} vídeos | {len(contagem)} sinais")
    for sinal, quantidade in sorted(contagem.items()):
        print(f"  {sinal:12} {quantidade} vídeos")

    if len(contagem) < 2:
        raise SystemExit("Precisa de pelo menos 2 sinais diferentes pra treinar.")
    poucos = [s for s, n in contagem.items() if n < MIN_VIDEOS_POR_SINAL]
    if poucos:
        raise SystemExit(
            f"Esses sinais têm menos de {MIN_VIDEOS_POR_SINAL} vídeos: {', '.join(sorted(poucos))}. "
            "Grave mais vídeos (o ideal é 20 ou mais por sinal)."
        )

    avisos = []
    menor = min(contagem.values())

    # ---- teste final separado (só se der pra manter vídeos de cada sinal dos dois lados)
    quantidade_teste = int(np.ceil(len(y) * PROPORCAO_TESTE))
    if menor >= 5 and quantidade_teste >= len(contagem):
        X_treino, X_teste, y_treino, y_teste = train_test_split(
            X, y, test_size=PROPORCAO_TESTE, stratify=y, random_state=42
        )
    else:
        X_treino, y_treino, X_teste, y_teste = X, y, None, None
        avisos.append("Poucos vídeos: não foi separado um teste final (veja a validação cruzada).")

    # ---- validação cruzada
    menor_treino = min(Counter(y_treino).values())
    k = min(K_FOLDS, menor_treino)
    if k < K_FOLDS:
        avisos.append(f"Poucos vídeos em algum sinal: validação cruzada com K={k} (e não K={K_FOLDS}).")

    print(f"\nValidação cruzada (K-fold estratificado, K={k})...")
    inicio = time.time()
    divisao = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
    acuracias_cv = cross_val_score(novo_modelo(), X_treino, y_treino, cv=divisao, scoring="accuracy")
    for numero, valor in enumerate(acuracias_cv, start=1):
        print(f"  Fold {numero}: {valor:.1%}")
    print(f"  Média: {acuracias_cv.mean():.2%} (desvio padrão {acuracias_cv.std():.2%}) "
          f"- {time.time() - inicio:.1f} s")

    # ---- modelo final: treina com os vídeos de treino (o teste continua guardado)
    modelo = novo_modelo()
    inicio = time.time()
    modelo.fit(X_treino, y_treino)
    print(f"Treinado em {time.time() - inicio:.1f} s")

    relatorio = matriz = acuracia = None
    letras = list(modelo.classes_)
    if X_teste is not None:
        previsto = modelo.predict(X_teste)
        acuracia = accuracy_score(y_teste, previsto)
        relatorio = classification_report(y_teste, previsto, digits=3, zero_division=0)
        matriz = confusion_matrix(y_teste, previsto, labels=letras)
        print(f"\nAcurácia no teste: {acuracia:.1%}\n")
        print(relatorio)

    joblib.dump(modelo, ARQUIVO_MODELO, compress=3)
    print(f"Modelo salvo em {ARQUIVO_MODELO}")

    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as arquivo:
        arquivo.write("Random Forest - reconhecimento de sinais com movimento (vídeos)\n")
        arquivo.write(f"Sinais: {', '.join(letras)}\n")
        arquivo.write(f"Vídeos de treino: {len(y_treino)}\n")
        arquivo.write(f"Vídeos de teste: {0 if X_teste is None else len(y_teste)}\n")
        if acuracia is not None:
            arquivo.write(f"Acurácia no teste: {acuracia:.1%}\n")
        for aviso in avisos:
            arquivo.write(f"ATENÇÃO: {aviso}\n")
        arquivo.write(f"\nValidação cruzada (K-fold estratificado, K={k}, só nos vídeos de treino):\n")
        for numero, valor in enumerate(acuracias_cv, start=1):
            arquivo.write(f"  Fold {numero}: {valor:.2%}\n")
        arquivo.write(f"  Média: {acuracias_cv.mean():.2%} (desvio padrão {acuracias_cv.std():.2%})\n")
        if relatorio is not None:
            arquivo.write("\nAcerto por sinal (precision, recall, f1-score):\n")
            arquivo.write(relatorio)
            arquivo.write("\nMatriz de confusão (linha = sinal certo, coluna = sinal previsto):\n")
            largura = max(4, max(len(s) for s in letras) + 1)
            arquivo.write(" " * largura + " ".join(f"{s:>{largura}}" for s in letras) + "\n")
            for sinal, linha in zip(letras, matriz):
                arquivo.write(f"{sinal:>{largura}} " + " ".join(f"{n:>{largura}}" for n in linha) + "\n")
    print(f"Relatório salvo em {ARQUIVO_RELATORIO}")

    treinar_grupos(X, y)


def ler_csv(caminho):
    linhas_X, linhas_y = [], []
    with open(caminho, encoding="utf-8") as arquivo_csv:
        for linha in csv.reader(arquivo_csv):
            if linha[0] == "sinal" or linha[0].isdigit():
                continue
            linhas_y.append(linha[0])
            linhas_X.append([float(v) for v in linha[2:]])
    return np.array(linhas_X, dtype=np.float32), np.array(linhas_y)


def _caracteristicas(quadros, tipo):
    try:
        return sequencia_para_caracteristicas(quadros, so_mao=(tipo == "mao"))
    except ValueError:
        return None


def _dados_aumentados(deteccoes, tipo):
    """Para cada vídeo: a lista de vetores de treino (vídeo inteiro + janelas + câmeras
    simuladas), as janelas "ao vivo" para a validação e os quadros originais (usados para
    criar os exemplos de "Nenhum sinal")."""
    treino, teste, rotulos, sequencias = [], [], [], []
    for (sinal, _arquivo), item in sorted(deteccoes.items()):
        quadros, qps = item["quadros"], item["quadros_por_segundo"]
        if _caracteristicas(quadros, tipo) is None:
            continue
        vetores = [v for v in (_caracteristicas(q, tipo) for q in versoes_para_treino(quadros, qps))
                   if v is not None]
        ao_vivo = [(v, quantidade_de_movimento(q)) for q in janelas(quadros, qps, passo=4)
                   for v in [_caracteristicas(q, tipo)] if v is not None]
        treino.append(vetores)
        teste.append(ao_vivo)
        rotulos.append(sinal)
        sequencias.append(quadros)
    return treino, teste, np.array(rotulos), sequencias


def _vetores_sem_sinal(sequencias, outras, quantidade, tipo, semente):
    gerador = np.random.default_rng(semente)
    exemplos = exemplos_sem_sinal(list(sequencias), list(outras), quantidade, gerador)
    return [(v, quantidade_de_movimento(q)) for q in exemplos
            for v in [_caracteristicas(q, tipo)] if v is not None]


def _treinar_um(treino, rotulos, indices, sequencias, outras, tipo, semente):
    """Treina com os vídeos 'indices' + exemplos de "Nenhum sinal" (tantos quanto um sinal médio)."""
    X = [v for i in indices for v in treino[i]]
    Y = [rotulos[i] for i in indices for _ in treino[i]]
    quantidade = len(Y) // max(len(set(Y)), 1)
    negativos = _vetores_sem_sinal([sequencias[i] for i in indices], outras, quantidade, tipo, semente)
    X += [v for v, _ in negativos]
    Y += [SEM_SINAL] * len(negativos)
    return novo_modelo().fit(np.array(X), Y), len(Y)


def _validar_com_aumento(treino, teste, rotulos, sequencias, outras, tipo, k):
    """Validação cruzada por VÍDEO: as versões de um vídeo nunca ficam no treino e no teste
    ao mesmo tempo. Mede duas coisas, com as regras do site (filtro de movimento + sinal
    certo em primeiro com certeza >= 30%):
      - acerto: janelas de 2-3 s dos vídeos de teste que valem como o sinal certo;
      - aceito por engano: exemplos de "Nenhum sinal" feitos com os vídeos de teste
        (mão parada, sobe e para, sacudindo) que o site validaria como algum sinal."""
    acertos = total = enganos = total_negativos = 0
    divisoes = StratifiedKFold(n_splits=k, shuffle=True, random_state=42).split(np.zeros(len(rotulos)), rotulos)
    for dobra, (parte_treino, parte_teste) in enumerate(divisoes):
        modelo, _ = _treinar_um(treino, rotulos, parte_treino, sequencias, outras, tipo, dobra)
        for i in parte_teste:
            if not teste[i]:
                continue
            probabilidades = modelo.predict_proba(np.array([v for v, _ in teste[i]]))
            for p, (_, movimento) in zip(probabilidades, teste[i]):
                total += 1
                acertos += int(movimento >= movimento_minimo(rotulos[i]) and
                               modelo.classes_[p.argmax()] == rotulos[i] and p.max() >= 0.3)
        negativos = _vetores_sem_sinal([sequencias[i] for i in parte_teste], outras,
                                       10 * len(parte_teste), tipo, 1000 + dobra)
        if negativos:
            probabilidades = modelo.predict_proba(np.array([v for v, _ in negativos]))
            for p, (_, movimento) in zip(probabilidades, negativos):
                total_negativos += 1
                previsto = str(modelo.classes_[p.argmax()])
                enganos += int(previsto != SEM_SINAL and movimento >= movimento_minimo(previsto) and p.max() >= 0.3)
    return acertos / max(total, 1), total, enganos / max(total_negativos, 1), total_negativos


def treinar_grupos(X, y):
    """
    Modelos por grupo (o site sabe qual sinal a pessoa escolheu, então o modelo só precisa
    escolher entre os sinais do mesmo grupo):
      Alfabeto (H, J, K, X, Z, Ç): só a mão (as N_CARACTERISTICAS_MAO primeiras colunas);
      Saudações: um com mão + corpo + rosto e outro só com a mão (usado quando o corpo ou
      o rosto não aparecem, ex.: pessoa sentada perto da câmera).

    Se existir dados/deteccoes_videos.pkl (gerado pelo extrair_sequencias.py), treina COM
    aumento de dados (aumento_dados.py): cada vídeo vira o vídeo inteiro + janelas de 2-3 s
    + câmeras simuladas. A validação também passa a ser "ao vivo" (janelas de 2-3 s).
    Sem esse arquivo, treina só com os vídeos inteiros dos CSVs (como antes).
    """
    if ARQUIVO_DETECCOES.exists():
        return _treinar_grupos_com_aumento()

    # "só mão": usa o sequencias_mao.csv (tem também os vídeos sem corpo/rosto); se não existir,
    # usa o começo do vetor completo (é o mesmo cálculo)
    if ARQUIVO_DADOS_MAO.exists():
        X_mao, y_mao = ler_csv(ARQUIVO_DADOS_MAO)
    else:
        X_mao, y_mao = X[:, :N_CARACTERISTICAS_MAO], y
    grupos = np.array([grupo_do_movimento(s) for s in y])
    grupos_mao = np.array([grupo_do_movimento(s) for s in y_mao])
    modelos, linhas = {}, ["", "Modelos por grupo (validação cruzada estratificada, K=5, todos os vídeos):"]
    for grupo, tipos in (("Alfabeto", ("mao",)), ("Saudações", ("completo", "mao"))):
        modelos[grupo] = {}
        for tipo in tipos:
            if tipo == "completo":
                Xg, yg = X[grupos == grupo], y[grupos == grupo]
            else:
                Xg, yg = X_mao[grupos_mao == grupo], y_mao[grupos_mao == grupo]
            if len(set(yg)) < 2:
                continue
            k = min(K_FOLDS, min(Counter(yg).values()))
            cv = cross_val_score(novo_modelo(), Xg, yg,
                                 cv=StratifiedKFold(n_splits=k, shuffle=True, random_state=42))
            nome_tipo = "mão + corpo + rosto" if tipo == "completo" else "só mão"
            linhas.append(f"  {grupo} ({nome_tipo}, {len(set(yg))} sinais, {len(yg)} vídeos): "
                          f"{cv.mean():.2%} (desvio {cv.std():.2%})")
            modelos[grupo][tipo] = novo_modelo().fit(Xg, yg)
    _salvar_grupos(modelos, linhas)


def _treinar_grupos_com_aumento():
    with open(ARQUIVO_DETECCOES, "rb") as arquivo:
        deteccoes = pickle.load(arquivo)
    deteccoes = {chave: item for chave, item in deteccoes.items() if not chave[0].isdigit()}
    modelos = {}
    linhas = ["", "Modelos por grupo COM aumento de dados (janelas de 2-3 s + câmeras simuladas)",
              "e com a classe \"Nenhum sinal\" (mão parada, mão que sobe e para, mão sacudindo).",
              "Validação cruzada por vídeo (K=5), com as regras do site (filtro de movimento +",
              "sinal certo em primeiro com certeza >= 30%):"]
    for grupo, tipos in (("Alfabeto", ("mao",)), ("Saudações", ("completo", "mao"))):
        do_grupo = {c: d for c, d in deteccoes.items() if grupo_do_movimento(c[0]) == grupo}
        outras = [d["quadros"] for c, d in sorted(deteccoes.items()) if grupo_do_movimento(c[0]) != grupo]
        modelos[grupo] = {}
        for tipo in tipos:
            treino, teste, rotulos, sequencias = _dados_aumentados(do_grupo, tipo)
            if len(set(rotulos)) < 2:
                continue
            k = min(K_FOLDS, min(Counter(rotulos).values()))
            taxa, janelas_testadas, engano, negativos = _validar_com_aumento(
                treino, teste, rotulos, sequencias, outras, tipo, k)
            nome_tipo = "mão + corpo + rosto" if tipo == "completo" else "só mão"
            modelo, exemplos = _treinar_um(treino, rotulos, range(len(rotulos)), sequencias, outras, tipo, 99)
            linhas.append(f"  {grupo} ({nome_tipo}, {len(set(rotulos))} sinais, {len(rotulos)} vídeos, "
                          f"{exemplos} exemplos de treino): acerto {taxa:.2%} em {janelas_testadas} janelas; "
                          f"aceito por engano {engano:.2%} de {negativos} exemplos sem sinal")
            print(linhas[-1], flush=True)
            modelos[grupo][tipo] = modelo
    _salvar_grupos(modelos, linhas)


def _salvar_grupos(modelos, linhas):
    joblib.dump(modelos, ARQUIVO_GRUPOS, compress=3)
    with open(ARQUIVO_RELATORIO, "a", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")
    print("\n".join(linhas))
    print(f"Modelos por grupo salvos em {ARQUIVO_GRUPOS}")


if __name__ == "__main__":
    main()
