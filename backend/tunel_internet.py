"""Liga o endereço pela internet (Cloudflare) e escreve a mensagem pronta para mandar.

O INICIAR_SignEdu.bat roda este arquivo na janela "SignEdu - internet" quando o
cloudflared.exe está na pasta do projeto. Ele:
  1. abre o túnel do Cloudflare para http://localhost:5000;
  2. quando o link https://....trycloudflare.com aparece, grava o arquivo
     ENDERECO_PARA_ENVIAR.txt (na pasta do projeto) com uma mensagem pronta,
     e abre esse arquivo no Bloco de Notas, para é só copiar e mandar.
O link do Cloudflare gratuito muda toda vez que o túnel é aberto, por isso o
arquivo é refeito a cada vez.
"""
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
CLOUDFLARED = PROJETO / "cloudflared.exe"
ARQUIVO = PROJETO / "ENDERECO_PARA_ENVIAR.txt"
PADRAO_LINK = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def ip_da_rede():
    """IP deste computador na rede de casa (prefere 192.168.x.x, como o app.py)."""
    ips = []
    try:
        ips = [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as teste:
            teste.connect(("8.8.8.8", 80))
            ips.append(teste.getsockname()[0])
    except OSError:
        pass
    casa = [ip for ip in ips if ip.startswith("192.168.")]
    outros = [ip for ip in ips if not ip.startswith("127.")]
    return (casa or outros or [None])[0]


def escrever_mensagem(link):
    ip = ip_da_rede()
    porta_rede = os.environ.get("PORTA_REDE", "5443")
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = (
        f"ENDEREÇO DO SIGNEDU (gerado em {agora})\n"
        "=========================================\n"
        "Este link vale enquanto o servidor estiver ligado. Se o INICIAR_SignEdu.bat\n"
        "for aberto de novo, o link muda e este arquivo é refeito.\n"
        "\n"
        "---- COPIE DAQUI PARA BAIXO E MANDE ----\n"
        "\n"
        "Oi! Para testar o SignEdu, plataforma de aprendizado de LIBRAS:\n"
        f"{link}\n"
        "\n"
        "1. Abra o link no Chrome (celular ou computador).\n"
        "2. Toque em \"Criar conta\", faça seu cadastro e entre.\n"
        "3. Vá em Praticar e permita o uso da câmera quando o navegador pedir.\n"
        "\n"
        "---- ATÉ AQUI ----\n"
    )
    if ip:
        texto += (
            "\n"
            "Para quem estiver na MESMA rede Wi-Fi do servidor (opcional, mais rápido):\n"
            f"https://{ip}:{porta_rede}\n"
            "(no aviso \"Sua conexão não é particular\": Avançado > Continuar)\n"
        )
    ARQUIVO.write_text(texto, encoding="utf-8-sig")  # -sig: o Bloco de Notas mostra os acentos certos


def main():
    if not CLOUDFLARED.exists():
        print("Nao achei o cloudflared.exe na pasta do projeto.")
        return 1
    # Apaga o link antigo, para ninguem mandar um endereco que ja nao funciona.
    try:
        ARQUIVO.unlink()
    except FileNotFoundError:
        pass

    print("Abrindo o endereco pela internet (leva uns segundos)...")
    processo = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--url", "http://localhost:5000"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
    )
    achou = False
    for linha in processo.stdout:
        if not achou:
            encontrado = PADRAO_LINK.search(linha)
            if encontrado:
                achou = True
                link = encontrado.group(0)
                escrever_mensagem(link)
                print()
                print("=" * 64)
                print("  LINK PARA MANDAR:", link)
                print("  Mensagem pronta em: ENDERECO_PARA_ENVIAR.txt (abrindo no Bloco de Notas)")
                print("  Deixe esta janela aberta: se fechar, o link para de funcionar.")
                print("=" * 64)
                print()
                if sys.platform.startswith("win"):
                    subprocess.Popen(["notepad.exe", str(ARQUIVO)])
                continue
        print(linha, end="")
    processo.wait()
    print()
    print("O endereco pela internet parou. Feche esta janela e abra o INICIAR_SignEdu.bat de novo.")
    return processo.returncode


if __name__ == "__main__":
    sys.exit(main())
