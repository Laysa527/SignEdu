"""
Sinais com MOVIMENTO, passo 1 do treino: extrair os pontos da mão dos VÍDEOS.

Passa cada vídeo da pasta dataset_videos pelo MediaPipe (quadro a quadro: mãos, corpo e
rosto), transforma a sequência de quadros nas características do modelo de movimento
(detector_maos.sequencia_para_caracteristicas) e salva uma linha por vídeo em
dados/sequencias.csv (mão + corpo + rosto) e em dados/sequencias_mao.csv (só a mão).
O arquivo "só mão" também recebe os vídeos em que o corpo ou o rosto não aparecem.
Também guarda os pontos de cada quadro em dados/deteccoes_videos.pkl: o treino usa esse
arquivo para o aumento de dados (janelas e câmeras simuladas, veja aumento_dados.py).

Precisa dos modelos hand_landmarker.task, pose_landmarker.task e face_landmarker.task
na pasta backend (veja o README pra baixar).

Estrutura esperada (uma pasta por sinal, o NOME DA PASTA é o nome do sinal):
    dataset_videos/Z/*.mp4
    dataset_videos/H/*.mp4
    dataset_videos/J/*.mp4
    dataset_videos/Oi/*.mp4
    dataset_videos/Tchau/*.mp4
    ...

Dicas pra gravar bons vídeos (o modelo aprende só com o que você mostrar):
  - grave pelo menos 20 vídeos por sinal (quanto mais, melhor), de preferência com
    pessoas, roupas, fundos e luz diferentes, e com mão direita e esquerda;
  - 1 a 4 segundos cada, um sinal por vídeo, de frente, com a mão inteira visível o tempo todo;
  - enquadre da CINTURA pra cima: os dois ombros e o rosto inteiro precisam aparecer
    (o modelo usa a posição da mão no corpo e no rosto, o movimento da cabeça e a expressão);
  - o sinal deve começar e terminar dentro do vídeo (sem cortar o movimento).
Vídeos em que a mão, o corpo ou o rosto quase não aparecem são pulados (e listados no final).

Como rodar:
    python extrair_sequencias.py
"""

import csv
import pickle
import time
from pathlib import Path

import cv2

from detector_maos import DetectorDeMaos, EXTENSOES_VIDEO, sequencia_para_caracteristicas

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_VIDEOS = PASTA_PROJETO / "dataset_videos"
ARQUIVO_SAIDA = PASTA_PROJETO / "dados" / "sequencias.csv"
ARQUIVO_SAIDA_MAO = PASTA_PROJETO / "dados" / "sequencias_mao.csv"
ARQUIVO_DETECCOES = PASTA_PROJETO / "dados" / "deteccoes_videos.pkl"


def duracao_do_video(caminho):
    """Duração em segundos (para saber quantos quadros analisados cabem em 1 segundo)."""
    captura = cv2.VideoCapture(str(caminho))
    try:
        quadros = captura.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        fps = captura.get(cv2.CAP_PROP_FPS) or 0
        return quadros / fps if quadros > 0 and fps > 0 else None
    finally:
        captura.release()


def main():
    if not PASTA_VIDEOS.exists():
        raise FileNotFoundError(
            f"Pasta {PASTA_VIDEOS} não encontrada. Crie ela e coloque os vídeos em "
            "subpastas, uma por sinal (ex.: dataset_videos/Z/video1.mp4)."
        )

    pastas = sorted(p for p in PASTA_VIDEOS.iterdir() if p.is_dir())
    if not pastas:
        raise FileNotFoundError(f"Nenhuma pasta de sinal dentro de {PASTA_VIDEOS}.")

    detector = DetectorDeMaos(
        PASTA_PROJETO / "hand_landmarker.task",
        caminho_corpo=PASTA_PROJETO / "pose_landmarker.task",
        caminho_rosto=PASTA_PROJETO / "face_landmarker.task",
    )
    if not detector.tem_corpo:
        raise FileNotFoundError(
            "Faltam pose_landmarker.task e/ou face_landmarker.task na pasta backend. "
            "Veja no README como baixar."
        )
    ARQUIVO_SAIDA.parent.mkdir(exist_ok=True)

    inicio = time.time()
    total_ok = 0
    puladas = []
    cabecalho = None
    deteccoes = {}

    with open(ARQUIVO_SAIDA, "w", newline="", encoding="utf-8") as arquivo_csv, \
            open(ARQUIVO_SAIDA_MAO, "w", newline="", encoding="utf-8") as arquivo_mao:
        escritor = csv.writer(arquivo_csv)
        escritor_mao = csv.writer(arquivo_mao)
        cabecalho_mao = None

        for pasta_sinal in pastas:
            sinal = pasta_sinal.name
            videos = sorted(v for v in pasta_sinal.iterdir() if v.suffix.lower() in EXTENSOES_VIDEO)
            ok = 0

            for video in videos:
                try:
                    quadros = detector.ler_video(video)
                    so_mao = sequencia_para_caracteristicas(quadros, so_mao=True)
                except ValueError as erro:
                    puladas.append(f"{sinal}/{video.name}: {erro}")
                    continue
                duracao = duracao_do_video(video)
                deteccoes[(sinal, video.name)] = {
                    "quadros": quadros,
                    "quadros_por_segundo": len(quadros) / duracao if duracao else 13.0,
                }
                if cabecalho_mao is None:
                    cabecalho_mao = ["sinal", "arquivo"] + [f"c{i}" for i in range(len(so_mao))]
                    escritor_mao.writerow(cabecalho_mao)
                escritor_mao.writerow([sinal, video.name] + [round(float(v), 6) for v in so_mao])
                try:
                    caracteristicas = sequencia_para_caracteristicas(quadros)
                except ValueError as erro:
                    puladas.append(f"{sinal}/{video.name} (só no modelo completo; entrou no só mão): {erro}")
                    continue

                if cabecalho is None:
                    cabecalho = ["sinal", "arquivo"] + [f"c{i}" for i in range(len(caracteristicas))]
                    escritor.writerow(cabecalho)

                escritor.writerow([sinal, video.name] + [round(float(v), 6) for v in caracteristicas])
                ok += 1

            total_ok += ok
            print(f"{sinal:12} {ok}/{len(videos)} vídeos usados")

    detector.fechar()
    with open(ARQUIVO_DETECCOES, "wb") as arquivo:
        pickle.dump(deteccoes, arquivo)

    if total_ok == 0:
        ARQUIVO_SAIDA.unlink(missing_ok=True)
        raise SystemExit("\nNenhum vídeo pôde ser usado. Confira se tem vídeos nas pastas.")

    minutos = (time.time() - inicio) / 60
    print(f"\nPronto! {total_ok} vídeos salvos, {len(puladas)} pulados, em {minutos:.1f} min.")
    for motivo in puladas:
        print(f"  pulado - {motivo}")
    print(f"Arquivo: {ARQUIVO_SAIDA}")


if __name__ == "__main__":
    main()
