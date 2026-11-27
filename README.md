# SignEdu

Plataforma web gamificada para o ensino de **Libras** com reconhecimento de sinais em tempo real pela câmera e por envio de vídeo, combinando **MediaPipe** (mãos, corpo e rosto) e **Random Forest**, com backend em **Flask** e banco de dados **MySQL**.

---

## Sumário

- [Funcionalidades](#funcionalidades)
- [Tecnologias](#tecnologias)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Pré-requisitos e instalação](#pré-requisitos-e-instalação)
- [Como funciona o reconhecimento](#como-funciona-o-reconhecimento)
- [Como treinar os modelos](#como-treinar-os-modelos)
- [Banco de dados e API](#banco-de-dados-e-api)
- [Créditos do dataset](#créditos-do-dataset)

---

## Funcionalidades

- **Alfabeto estático pela câmera:** reconhecimento em tempo real de 21 letras estáticas (`A B C D E F G I L M N O P Q R S T U V W Y`) com desenho do esqueleto da mão e barra de confirmação. O quadro enviado é sempre o centro 4:3 da câmera (webcams 16:9 são recortadas), igual à área mostrada na tela.
- **Números parados:** os números de `0` a `9` são reconhecidos em tempo real como as letras (só o formato da mão, sem gravar), com um modelo próprio treinado com as mãos do especialista em LIBRAS (`backend/modelo_numeros.joblib`). Cada número tem uma foto de exemplo da mão do especialista.
- **Sinais com movimento:** 18 sinais dinâmicos — letras `H, J, K, X, Z, Ç` e as saudações *Oi, Tchau, Bom dia, Boa tarde, Boa noite, Obrigado, Por favor, Desculpa, Tudo bem, Sim, Não* e *Nome*. As letras usam **só a mão** (dá pra fazer sentado e perto da câmera); as saudações usam mão, corpo e rosto quando eles aparecem e só a mão quando não aparecem. Funciona ao vivo na câmera (automático ou pelo botão Gravar sinal) e por envio de vídeo (`MP4`, `MOV`, `AVI`, `WEBM` ou `MKV`, até 50 MB e 3 minutos).
- **Reconhecimento automático dos sinais com movimento:** com a câmera ligada, basta fazer o sinal inteiro. O site guarda os últimos 3 segundos e, a cada 0,8 s, pergunta ao servidor qual sinal foi feito (`POST /api/maos/movimento` com `"verificar": true`, que responde sem salvar tentativa). O cartão "Sinal reconhecido" mostra o que o modelo está vendo; quando o sinal certo aparece com certeza suficiente, a mesma janela é enviada como tentativa e conta o acerto.
- **Gravar sinal:** continua como alternativa, logo abaixo do exemplo (no celular, também embaixo da câmera). Os sinais com movimento têm uma bolinha vermelha no botão.
- **Certeza mínima:** letras e números parados precisam de 50% de certeza em 8 quadros seguidos; sinais com movimento precisam que o sinal certo seja o mais provável e tenha pelo menos **30%** (`CERTEZA_MINIMA_MOVIMENTO` em `banco.py`). Com 18 sinais, o modelo divide a certeza entre eles: no teste com os vídeos do especialista (uma luz contra a outra), o sinal certo foi o mais provável em 80% dos vídeos, mas só 17% passavam de 50%; com 30%, passam 57%.
- **Celular e computador:** as telas se ajustam ao tamanho da tela (Bootstrap). Na prática, o resultado e o botão de gravar ficam logo abaixo da câmera, e a área da câmera acompanha a proporção da câmera do celular em pé. Para abrir no celular, veja [Usar no celular](#usar-no-celular).
- **Categorias:** os sinais são organizados em **Alfabeto**, **Números** e **Saudações**, na tela de prática e no banco.
- **Vídeos de exemplo:** cada sinal com movimento tem um vídeo curto de demonstração, gravado por um especialista em LIBRAS (com autorização de uso de imagem).
- **Duas mãos na imagem:** quando aparecem as duas mãos, o sistema usa a que faz o sinal (a que mais se mexe e fica mais alta), e não a mão parada.
- **Envio de vídeo nos sinais com movimento:** em vez de gravar ao vivo, a pessoa pode enviar um vídeo. Nas letras e números parados o botão não aparece (basta segurar o sinal na câmera); o servidor ainda aceita vídeo de letra parada pela API, analisando quadro a quadro e decidindo pela letra mais votada.
- **Termos de Uso e Política de Privacidade:** ao criar a conta, a pessoa lê os termos numa janela e só consegue se cadastrar se aceitar; a data do aceite fica salva (`usuarios.termos_aceitos_em`). O texto completo está em `frontend/termos.html`.
- **Contas e autenticação:** cadastro, login, logout (sessão em cookie `HttpOnly` e senhas armazenadas com hash), edição de nome, troca de senha e exclusão de conta.
- **Pontos por acerto:** o 1º acerto de cada sinal vale os pontos cheios (10 nos parados, 20 nos com movimento) mais 5 de bônus de sinal novo; repetir o mesmo sinal no mesmo dia vale 2; revisar em outro dia vale metade. Assim repetir a letra mais fácil não vale o mesmo que aprender um sinal novo (`pontos_do_acerto` em `banco.py`).
- **Gamificação e progresso no banco:** sessões de treino, resultados, pontuação, XP, níveis (1 a 8), moedas, sequência de dias, ranking semanal por ligas (`Bronze`, `Prata`, `Ouro` e `Diamante`), missões semanais, conquistas, loja de itens e molduras, foto de perfil e configurações, tudo salvo no MySQL. Só a contagem de minutos da meta diária fica no navegador (`localStorage`).

---

## Tecnologias

| Camada | Ferramentas |
| --- | --- |
| **Backend** | Python 3, Flask, Flask-SQLAlchemy, PyMySQL, python-dotenv |
| **Visão Computacional e IA** | MediaPipe Tasks (`Hand`, `Pose` e `Face Landmarker`), OpenCV, scikit-learn (`RandomForestClassifier`), NumPy, joblib |
| **Banco de Dados** | MySQL 8 |
| **Frontend** | HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons |

---

## Estrutura do projeto

```text
SignEdu/
├── README.md
├── .gitignore
├── venv/                                # ambiente virtual local (não vai pro Git)
├── backend/
│   ├── app.py                           # servidor Flask: frontend, API, banco e detecção
│   ├── banco.py                         # modelos MySQL (SQLAlchemy), níveis, ligas e ranking
│   ├── detector_maos.py                 # MediaPipe (mão, corpo e rosto) + classificadores Random Forest
│   ├── extrair_landmarks.py             # treino estático (1/2): extrai 21 pontos da mão das fotos
│   ├── treinar_modelo.py                # treino estático (2/2): valida (K=5) e treina modelo_letras.joblib
│   ├── extrair_sequencias.py            # treino movimento (1/2): extrai mão, corpo e rosto dos vídeos
│   ├── treinar_modelo_movimento.py      # treino movimento (2/2): valida (K=5) e treina modelo_movimento.joblib
│   ├── treinar_modelo_numeros.py        # treino dos números parados (0 a 9) a partir dos clipes
│   ├── avaliar_por_iluminacao.py        # teste extra: treina com uma gravação e testa com a outra
│   ├── avaliar_formato_e_tempo.py       # teste extra: acerto em quadros 4:3 e 16:9 e tempo por quadro
│   ├── modelo_letras.joblib             # Random Forest já treinado para as 21 letras estáticas
│   ├── modelo_movimento.joblib          # Random Forest de sinais com movimento (gerado após o treino)
│   ├── modelo_numeros.joblib            # Random Forest dos números 0 a 9 (sinais parados)
│   ├── hand_landmarker.task             # modelo MediaPipe de mãos (baixar — não vai pro Git)
│   ├── pose_landmarker.task             # modelo MediaPipe de corpo (baixar — não vai pro Git)
│   ├── face_landmarker.task             # modelo MediaPipe de rosto (baixar — não vai pro Git)
│   ├── hand_landmarker_test.py          # script de teste antigo direto na webcam com OpenCV
│   ├── requirements.txt                 # dependências Python
│   ├── .env.example                     # modelo de variáveis de ambiente
│   ├── .env                             # credenciais do MySQL e SECRET_KEY (local, não vai pro Git)
│   ├── dados/
│   │   ├── landmarks.csv                # landmarks extraídos das fotos do alfabeto
│   │   ├── relatorio_treino.txt         # métricas do modelo estático (K=5, teste e matriz de confusão)
│   │   ├── sequencias.csv               # características extraídas dos vídeos (gerado no treino)
│   │   └── relatorio_movimento.txt      # métricas do modelo de movimento (gerado no treino)
│   ├── dataset/                         # fotos do cnn-libras (opcional, só para retreinar; não vai pro Git)
│   └── dataset_videos/                  # seus vídeos, uma pasta por sinal (não vai pro Git)
└── frontend/                            # servido pelo app.py em http://localhost:5000
    ├── login.html                       # login e cadastro
    ├── perfil.html                      # painel inicial (nível, XP, estatísticas, missões e liga)
    ├── praticar.html                    # prática com câmera ao vivo e envio de vídeo
    ├── ranking.html                     # ranking semanal por liga
    ├── conta.html                       # edição de nome, troca de senha e exclusão de conta
    ├── conquistas.html                  # conquistas
    ├── loja.html                        # loja de itens e molduras
    ├── configuracoes.html               # preferências de acessibilidade e avisos
    ├── img/letras/                      # imagens de exemplo das 21 letras estáticas
    ├── videos/                          # vídeos de exemplo (<Sinal>.mp4) dos sinais com movimento (não vai pro Git)
    ├── css/                             # folhas de estilo
    ├── js/                              # scripts das telas (geral.js é compartilhado após o login)
    └── vendor/                          # Bootstrap Icons local
```

---

## Pré-requisitos e instalação

Você precisa de **Python 3.10+** e **MySQL** instalado e em execução.

### 1. Criar o ambiente virtual e instalar dependências

Na raiz do projeto (`SignEdu`), pelo PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 2. Configurar o banco de dados (`.env`)

Copie `backend/.env.example` para `backend/.env` e preencha os dados do seu MySQL:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=sua_senha_do_mysql
DB_NAME=signedu
SECRET_KEY=cole_aqui_uma_chave_aleatoria
```

Para gerar uma `SECRET_KEY` segura:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

> Na primeira execução, o servidor cria automaticamente o banco `signedu`, as tabelas que ainda não existirem e os exercícios das 21 letras estáticas (além dos sinais de movimento treinados), sem apagar dados já cadastrados.

### 3. Baixar os modelos do MediaPipe

Os arquivos `.task` não são versionados no Git. Baixe-os para dentro da pasta `backend/`:

```powershell
Invoke-WebRequest https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task -OutFile backend/hand_landmarker.task
Invoke-WebRequest https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task -OutFile backend/pose_landmarker.task
Invoke-WebRequest https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task -OutFile backend/face_landmarker.task
```

- `hand_landmarker.task` é obrigatório para iniciar o servidor.
- `pose_landmarker.task` e `face_landmarker.task` são necessários para extrair e reconhecer sinais com movimento, corpo e rosto.

### 4. Iniciar o servidor

```powershell
python backend/app.py
```

Abra **http://localhost:5000** no navegador.

> A câmera só funciona acessando o site pelo endereço acima (não abrindo o arquivo `.html` diretamente). Nas próximas vezes, basta ativar o `venv` e rodar `python backend/app.py`.

---

## Como funciona o reconhecimento

### Letras estáticas (1 imagem por vez)

O modelo de fotos (`backend/modelo_letras.joblib`, já treinado) reconhece **21 letras**:
`A B C D E F G I L M N O P Q R S T U V W Y`.

1. A tela `praticar.html` captura quadros da câmera espelhados, recorta o centro 4:3 (o modelo foi treinado com imagens 4:3 e erra mais com quadros 16:9) e envia via `POST /api/maos/detectar`.
2. O `detector_maos.py` extrai os 21 landmarks da mão com o MediaPipe Hand Landmarker.
3. Os pontos são normalizados em 63 características (`x, y, z` de cada ponto): pulso transladado para a origem `(0, 0, 0)`, escala dividida pela maior distância ao pulso e mão esquerda espelhada no eixo `x`.
4. O `RandomForestClassifier` (200 árvores) prediz a letra e a confiança. Se aparecerem as duas mãos, vale a mão em que o modelo tem mais certeza.
5. O frontend desenha o esqueleto da mão. Com uma sessão de treino aberta, o servidor soma 1 a cada quadro em que a letra pedida aparece com certeza mínima de 50% e desconta 2 a cada quadro errado; ao chegar a 8, registra o acerto, os pontos e o progresso no banco.

Exemplo de resposta de `POST /api/maos/detectar`:

```json
{
  "maos": [
    {
      "lado": "Direita",
      "confianca": 0.97,
      "pontos": [{ "x": 0.51, "y": 0.72, "z": 0.0 }, "... 21 pontos no total"]
    }
  ],
  "proporcao": 1.3333,
  "letra": "A",
  "certeza": 0.93
}
```

**Desempenho do modelo estático** (registrado em `backend/dados/relatorio_treino.txt`):
- **Dataset:** 34.292 exemplos de treino e 11.402 exemplos de teste.
- **Validação cruzada estratificada (`K=5`, apenas no treino):** média de **99,94%** (desvio padrão `0,01%`).
- **Acurácia no conjunto de teste:** **99,8%**.
- **Proporção do quadro e tempo** (`backend/avaliar_formato_e_tempo.py`, 2.310 imagens de teste da cnn-libras colocadas em quadros de webcam): sem o recorte 4:3, o acerto era de 97,4% em quadros 4:3 e caía para 75,7% em 16:9; com o recorte (versão 2.4), fica em 97,4% nos dois. Tempo por quadro no servidor: mediana de 57 ms (95% em até 77 ms), medido num processador Intel Xeon de 2,1 GHz com 2 núcleos.
- **Teste com uma pessoa de fora da base** (vídeos do especialista em LIBRAS, `backend/dados/relatorio_teste_especialista.txt`): **41,8%** de 502 repetições (55,4% nas repetições com o corpo mais de frente). O 99,8% vale para as fotos da própria cnn-libras, que não separa as pessoas entre treino e teste; com uma pessoa nova o modelo erra bem mais, principalmente com o corpo virado. Ampliar a base com mais pessoas é o próximo passo.

### Sinais com movimento, corpo e rosto (vídeo)

As letras `H, J, K, X, Z, Ç` e as saudações dependem de movimento, ponto de articulação no corpo/rosto e expressões faciais, por isso não podem ser reconhecidas com uma foto isolada.

Na tela de prática, esses sinais funcionam de duas formas:
- **Câmera ao vivo:** escolha o sinal, enquadre-se **de frente e da cintura para cima** (rosto e ombros visíveis — o site desenha o esqueleto do corpo e pontos do rosto e indica no painel se o enquadramento está `ok`), clique em **Gravar sinal**, aguarde a contagem de 3 segundos e faça o sinal em 3 segundos.
- **Envio de vídeo:** clique em **Enviar um vídeo** (`MP4`, `MOV`, `AVI`, `WEBM` ou `MKV`, até 50 MB). (Nas letras e números parados o botão não aparece: é só segurar o sinal na câmera.)

Em cada quadro analisado, o `detector_maos.py` combina os três modelos do MediaPipe (`Hand`, `Pose` e `Face`) e gera um vetor fixo de **904 características**, invariantes à distância da câmera e à velocidade do sinal:
- **Formato da mão** em 8 instantes reamostrados;
- **Trajetória e velocidade do pulso** em 16 instantes + resumos (distância percorrida, deslocamento e amplitude);
- **Corpo e braços** em 8 instantes (nariz, ombros, cotovelos, pulsos, palma e ponta do indicador normalizados pela largura dos ombros);
- **Relação mão–rosto** (distância da palma até nariz, queixo, testa e boca, diferenciando sinais como *Obrigado* ou *Bom dia*);
- **Movimento da cabeça** (giro, inclinação e amplitude horizontal/vertical);
- **Expressão facial** (13 grupos de blendshapes: sobrancelhas, olhos, bochechas e boca).

Antes disso, se aparecerem as duas mãos, o detector acompanha cada uma pela sequência e usa a que faz o sinal: a de maior nota de **movimento da palma + altura** (a mão parada costuma ficar embaixo, na cintura). A trilha inteira usa o lado (direita/esquerda) mais frequente, porque o MediaPipe às vezes troca o lado em alguns quadros. A câmera ao vivo envia as duas mãos de cada quadro e o servidor faz essa escolha.

Os sinais com movimento usam `RandomForestClassifier` (200 árvores) **por grupo**. O site sabe qual sinal a pessoa escolheu, então o modelo só precisa escolher entre os sinais do mesmo grupo (`backend/modelo_movimento_grupos.joblib`):
- **Letras com movimento** (`H, J, K, X, Z, Ç`): **só a mão** (formato da mão + caminho do pulso, as 570 primeiras características). Não precisa de corpo nem de rosto: funciona sentado e perto da câmera, e a câmera nem calcula corpo e rosto nessas letras (fica mais rápida).
- **Saudações:** um modelo com **mão + corpo + rosto** (904 características), usado quando o corpo e o rosto aparecem, e outro **só com a mão**, usado quando não aparecem (pessoa sentada ou perto da câmera).
- O `backend/modelo_movimento.joblib` (mão + corpo + rosto, sem grupo) fica para chamadas da API sem o sinal escolhido.

**Corte dos vídeos do especialista** (versão 2.4): cada repetição começa no primeiro movimento depois que ele diz o nome do sinal e termina quando ele relaxa os braços. Antes, alguns cortes (como *Boa noite* e *Boa tarde*) começavam depois da parte do sinal perto da boca e ficavam incompletos.

**Desempenho** (`backend/dados/relatorio_movimento.txt` e `relatorio_por_iluminacao.txt`). A base tem 12 repetições por sinal em duas gravações (luz direta e luz indireta): 431 clipes no "só mão" e 329 no completo (vídeos em que o corpo ou o rosto não aparecem ficam só no "só mão").
- **Validação cruzada `K=5`** (otimista, porque repetições quase iguais caem no treino e no teste): letras só mão **97,2%**; saudações completo **93,6%**; saudações só mão **91,3%**.
- **Teste por iluminação** (treina com uma gravação e testa com a outra, vídeos que o modelo nunca viu). "Vale" é a regra do site: o sinal certo é o mais provável e tem pelo menos 30% de certeza.
  - Letras só mão: sinal certo como o mais provável em **87,6%**; vale como acerto em **84,1%**.
  - Saudações completo: **79,3%**; vale em **63,2%**.
  - Saudações só mão: **75,5%**; vale em **65,4%**.
  - Maior confusão: *Obrigado* com *Por favor*. *Boa noite*, *Boa tarde* e *Bom dia* também se confundem entre si, porque agora os três começam com a mão perto da boca.
- Todos os vídeos são de uma única pessoa: o desempenho com outras pessoas ainda precisa ser medido.

**Aumento de dados** (versão 4, `backend/aumento_dados.py`). Ao vivo o site não vê o vídeo cortado certinho: ele olha **janelas de 2 a 3 segundos** da câmera, que pegam só um pedaço do sinal, em câmeras de formatos diferentes (notebook 16:9, celular em pé) e com a mão de cada pessoa um pouco mais inclinada. Treinado só com os vídeos inteiros, o modelo errava muito nessa situação. Agora cada vídeo do especialista vira várias versões de treino: o vídeo inteiro, **janelas de 2, 2,5 e 3 s** e **câmeras simuladas** (16:9 e 3:4, com a mão girada de 9° a 11°). Não é sinal inventado: é o mesmo movimento do especialista visto de outro jeito. O `extrair_sequencias.py` guarda os pontos de cada quadro em `dados/deteccoes_videos.pkl` e o `treinar_modelo_movimento.py` usa esse arquivo quando ele existe.
- Teste "ao vivo" (validação cruzada por vídeo, testando em janelas de 2–3 s; vale = sinal certo em primeiro com pelo menos 30%):

  | Modelo | Antes (só vídeo inteiro) | Com aumento de dados |
  |---|---|---|
  | Letras com movimento (só mão) | 87% | 92% |
  | Saudações (mão + corpo + rosto) | 81% | 95% |
  | Saudações (só mão) | 77% | 92% |

  Os maiores ganhos: *J* (63% → 97%), *Obrigado* no modelo completo (75% → 96%), *Bom dia* e *Boa tarde* (cerca de 50% → 92%). Na câmera de celular em pé, as letras com movimento sem aumento caíam para 48–73% (*Z*, *Ç*, *H*) e com aumento ficam entre 88% e 98%.
- Continua sendo uma pessoa só nos vídeos: o aumento de dados ajuda com câmera e enquadramento, mas não substitui gravar outras pessoas sinalizando.

**"Nenhum sinal" e filtro de movimento** (versão 4). Como o site sabe qual sinal a pessoa escolheu, o modelo do grupo só escolhia entre os sinais daquele grupo, e não tinha a opção "não é nenhum destes". Resultado: mão parada, palma aberta tremendo ou o formato do I sem desenhar o J eram validados como "o sinal mais parecido". Agora são duas proteções:
1. **Filtro de movimento** (`detector_maos.quantidade_de_movimento`): mede quanto o pulso andou (em tamanhos de mão) e quanto o formato da mão mudou (giro e dedos), as duas medidas suavizadas para o tremor não contar. Abaixo do mínimo, o sinal com movimento não vale e o site mostra "Mão parada: faça o movimento do sinal". Calibração: os vídeos inteiros do especialista passam em 96% a 100%, e mãos paradas com tremor simulado passam em 0% a 1%.
2. **Classe "Nenhum sinal"** nos modelos de movimento (`aumento_dados.exemplos_sem_sinal`), treinada com exemplos feitos a partir dos próprios vídeos: mão parada com tremor, mão que sobe e para (ex.: formato do I sem o movimento do J) e formato de mão de outro grupo sacudindo (ex.: palma aberta balançando nas letras).

| Modelo | Aceitava por engano (antes) | Aceita por engano (agora) | Acerto nas janelas ao vivo (agora) |
|---|---|---|---|
| Letras com movimento (só mão) | 90% | 2% | 86% |
| Saudações (mão + corpo + rosto) | 81% | 6% | 86% |
| Saudações (só mão) | 81% | 5% | 83% |

"Aceito por engano" = exemplos sem sinal que o site validaria como algum sinal (antes: modelo com aumento de dados, sem as duas proteções; agora: validação cruzada por vídeo, com os exemplos feitos só dos vídeos de teste). O acerto ficou um pouco menor que sem as proteções (cerca de 92%) porque agora as janelas que pegam só um pedaço parado do sinal deixam de valer, e é isso que deve acontecer: o sinal só vale quando o movimento aparece.

**Letra B** (sinal parado): o modelo das letras também não tem "nenhum destes", e a palma aberta comum virava B. Regra extra (`detector_maos.polegar_dobrado`): no B o polegar fica dobrado sobre a palma, então a ponta do polegar precisa estar perto da base do dedo médio (até 0,2 tamanho de mão). Nas fotos de B da base, 98,9% passam; nos quadros de palma aberta dos vídeos (Tchau) que o modelo chamava de B, só 9% continuam passando.

**Calibração com a câmera de verdade** (modo de coleta, `praticar.html?teste=1`). Os ajustes acima foram feitos só com os vídeos do especialista e com mãos paradas simuladas, e no teste ao vivo ainda falhavam (Ç e X parados passavam, Oi deixou de passar, M, 5 e 6 aceitavam formatos errados). Por isso o site ganhou um modo de coleta: a pessoa escolhe o sinal, marca "fazendo CERTO" ou "fazendo ERRADO" e o servidor guarda só os pontos da mão (sem imagem) em `dados/coleta_testes.jsonl`, sem valer ponto. Com uma coleta de 15 minutos (11 sinais):
- **Filtro de movimento por sinal** (`MOVIMENTO_MINIMO_POR_SINAL` em `detector_maos.py`): a mão parada dá 0,1 a 0,4 e o sinal certo de movimento pequeno (Ç, Sim, Oi) dá 0,5 a 0,8, então o mínimo virou 0,45 (Não: 0,25). J, K, X e Z ficam em 0,9, porque o X parado "treme" até 0,7 no MediaPipe. Nos vídeos do especialista, as janelas que passam no filtro subiram (ex.: Não 61% → 98%, Oi 82% → 93%, Ç 76% → 89%).
- **Duas confirmações seguidas** no reconhecimento automático: o sinal certo precisa aparecer em 2 verificações seguidas (0,8 s de diferença). Um movimento de passagem (levantar a mão até a posição) não basta.
- **"Nenhum sinal" nas letras e nos números parados** (`treinar_nenhum_parados.py`): os quadros ERRADOS da coleta entram no treino como "Nenhum sinal"; os quadros CERTOS nunca entram no treino, só no teste.

| Sinal parado | Feito errado: aceito antes → agora | Feito certo: quadros aceitos agora | Vale (8 quadros seguidos) |
|---|---|---|---|
| M | 86% → 0% | 83% | certo sim, errado não |
| 5 | 65% → 2% | 64% | certo sim, errado não |
| 6 | 94% → 1% | 58% | certo sim, errado não |
| B / P / 4 | 0–4% → 0% | 82% / 96% / 62% | certo sim, errado não |

Na base de teste das letras (11.402 fotos) o acerto continuou igual (99,80% → 99,88%). Nos sinais com movimento, com o filtro por sinal e as duas confirmações, todos os sinais feitos certo na coleta valeram (J, K, Não, X, Ç; Sim em 1 de 2 tentativas) e, com a mão parada, nenhum valeu; os únicos aceites por engano aconteceram no instante em que a mão estava entrando ou saindo da posição.

**Limitações conhecidas:** a calibração usou a câmera e as mãos de uma só pessoa (a autora), em 15 minutos; com outras pessoas e câmeras os números podem mudar. O número 5 do especialista são dois dedos levantados com as pontas dobradas; dois dedos esticados ainda podem passar como 5, porque o modelo dos números só conhece 0 a 9 (precisaria de mais exemplos de outras pessoas e de formatos errados). *Bom dia* e *Boa tarde* começam iguais (mão perto da boca) e ainda se confundem.

### Números (0 a 9) como sinais parados

Em LIBRAS os números de 0 a 9 não precisam de movimento: o que diz o número é o formato da mão. Por isso eles têm um modelo próprio (`backend/modelo_numeros.joblib`, Random Forest de 200 árvores) com as mesmas 63 características das letras, e na tela funcionam como as letras: é só segurar o sinal na câmera (o site manda `grupo=numeros` e o servidor usa esse modelo no lugar do das letras). Fica separado do modelo das letras porque alguns números têm o mesmo formato de letras.

Os exemplos vêm dos clipes dos números do especialista: em cada clipe ficam os quadros em que a mão do sinal está levantada e parada (até 10 por clipe), o que deu **2.319 quadros de 232 clipes** (`backend/treinar_modelo_numeros.py`, relatório em `backend/dados/relatorio_numeros.txt`):
- **Validação cruzada por clipe** (`K=5`, os quadros de um clipe ficam sempre juntos): **94,4%** por quadro (desvio 2,2%) e **95,7%** por clipe. A maior confusão é entre *3* e *4*.
- **Teste por iluminação:** **77,2%** (treino na luz direta, onde não há o *2*) e **79,1%** (treino na luz indireta).
- As fotos de exemplo (`frontend/img/numeros/`) foram recortadas dos mesmos vídeos e, como os vídeos, não vão para o repositório.

Para retreinar: `python backend/treinar_modelo_numeros.py pasta_dos_clipes` (uma subpasta por número, `0/` a `9/`).

---

## Iniciar com um clique (Windows)

O `INICIAR_SignEdu.bat`, na pasta do projeto, faz tudo: usa o `venv\` do projeto (ou cria na primeira vez, com internet, e instala o `requirements.txt`), cria o `backend\.env` a partir do `.env.example` se ele ainda não existir (abre o Bloco de Notas para colocar a senha do MySQL), confere os arquivos `.task` do MediaPipe e liga o servidor com dois endereços: `http://localhost:5000` neste computador e `https://IP-DO-PC:5443` para celular ou outro computador na mesma rede. A janela preta precisa ficar aberta enquanto a plataforma é usada.

## Acessar pela internet (ex.: a feira acessando o servidor que está em casa)

Coloque o `cloudflared.exe` (Cloudflare Tunnel, gratuito, baixado do [GitHub oficial da Cloudflare](https://github.com/cloudflare/cloudflared/releases)) na pasta do projeto, ao lado do `INICIAR_SignEdu.bat`. Ao iniciar, o bat abre uma segunda janela ("SignEdu - internet") (`backend/tunel_internet.py`) que mostra um endereço `https://...trycloudflare.com` e grava a mensagem pronta para enviar em `ENDERECO_PARA_ENVIAR.txt`, aberto sozinho no Bloco de Notas. Esse endereço abre a plataforma de qualquer lugar, com câmera, porque já é `https` de verdade. O endereço muda toda vez que o servidor é iniciado, e qualquer pessoa com o link consegue entrar. O computador do servidor precisa ficar ligado (sem suspender), com o MySQL e as duas janelas abertas. Pelo túnel, o IP de cada pessoa vem no cabeçalho `CF-Connecting-IP` (o `ip_cliente` usa esse cabeçalho só quando o pedido chega do próprio computador).

## Usar no celular

O navegador do celular só libera a câmera em endereço seguro (`https`). Para testar com o celular (ou outro computador) na mesma rede, rode o servidor com `PORTA_REDE=5443` (no Windows: `set PORTA_REDE=5443` e depois `python backend/app.py`). O servidor continua em `http://localhost:5000` neste computador, sem aviso, e abre também um endereço `https` para a rede. O servidor cria um certificado próprio na hora e mostra o endereço para abrir no celular (ex.: `https://192.168.0.10:5443`). O navegador avisa que o certificado não é verificado: toque em **Avançado** e continue. Se o Windows perguntar sobre o firewall, permita o acesso em redes privadas.

Para publicar de verdade (fora da rede de casa), use um servidor com certificado HTTPS de verdade e `COOKIE_SECURE=1`.

---

## Como treinar os modelos

### 1. Sinais com movimento, corpo e rosto (necessário para habilitar esses sinais)

O `modelo_movimento.joblib` já vem treinado com a base própria (18 sinais; pastas com nome de número são ignoradas, porque os números usam o `modelo_numeros.joblib`). Os vídeos de treino não vão para o repositório. Para retreinar ou acrescentar sinais:

1. Crie subpastas em `backend/dataset_videos/`, sendo o **nome da pasta o nome do sinal**:

```text
backend/dataset_videos/
├── Z/
│   ├── video01.mp4
│   └── ...
├── H/
├── Obrigado/
└── Bom dia/
```

   **Boas práticas de gravação:**
   - Grave pelo menos **20 vídeos por sinal** (quanto mais variedade, melhor);
   - Vídeos de **1 a 4 segundos**, um sinal completo por vídeo (sem cortar o início ou o fim);
   - Pessoa **de frente, da cintura para cima**, com o rosto inteiro, os dois ombros e a mão bem visíveis;
   - Varie pessoas, iluminação, fundos, roupas e use tanto a mão direita quanto a esquerda.

2. Extraia as características e treine o modelo:

```powershell
python backend/extrair_sequencias.py
python backend/treinar_modelo_movimento.py
python backend/avaliar_por_iluminacao.py   # opcional: clipes com _D_ (luz direta) ou _I_ (luz indireta) no nome
```

3. Reinicie `python backend/app.py`. Os sinais treinados são cadastrados automaticamente no banco, com a categoria certa (**Alfabeto** para letras, **Saudações** para o resto), e aparecem na tela de prática.
   - Coloque um vídeo de demonstração em `frontend/videos/<NomeDoSinal>.mp4` (por exemplo `frontend/videos/Bom dia.mp4`) para exibi-lo ao lado do desafio. Essa pasta está no `.gitignore`: os vídeos do especialista são autorizados para uso dentro da plataforma, não para publicação no repositório. Copie a pasta direto para o servidor.
   - As métricas (validação cruzada estratificada `K=5`, teste final de 20% e matriz de confusão) ficam em `backend/dados/relatorio_movimento.txt`.

> Caso exista um `modelo_movimento.joblib` treinado em uma versão antiga (sem corpo e rosto), o servidor exibe um aviso na inicialização e desativa os sinais com movimento até que o modelo seja retreinado.

### 2. Letras estáticas (opcional — `modelo_letras.joblib` já vem pronto)

Só é necessário se quiser modificar o dataset ou os parâmetros do treino:

1. Copie a pasta `dataset` do projeto `cnn-libras` para `SignEdu/backend/` (`backend/dataset/training/A/...` e `backend/dataset/test/A/...`).
2. Execute:

```powershell
python backend/extrair_landmarks.py
python backend/treinar_modelo.py
```

O primeiro script percorre ~46 mil imagens com o MediaPipe e salva `backend/dados/landmarks.csv`. O segundo leva menos de um minuto, executa validação cruzada `K=5`, avalia o teste e gera `backend/modelo_letras.joblib` e `backend/dados/relatorio_treino.txt`.

---

## Testes automáticos

Os testes ficam na pasta `tests/` e usam um banco SQLite temporário (não mexem no MySQL). Na pasta do projeto:

```powershell
pip install pytest
python -m pytest -v
```

São 34 testes: normalização dos pontos da mão, espelhamento da mão esquerda, recorte 4:3, escolha da mão que faz o sinal, modelos treinados (classes e número de características, incluindo o modelo dos números), reconhecimento de vídeos de exemplo reais, cadastro com e sem aceite dos termos, e-mail repetido, login, rotas protegidas, categorias, lista dos números parados, verificação automática de movimento sem salvar tentativa, validação dos quadros, detecção numa imagem sem mão e exclusão de conta. O resultado da última execução fica em `tests/resultado_ultima_execucao.txt`.

## Banco de dados e API

O schema MySQL (`signedu`, definido em `backend/banco.py`) contém 13 tabelas. As que ainda não existirem são criadas automaticamente na primeira execução, e as colunas novas são acrescentadas sem apagar dados.

**Tabelas principais**
- `usuarios` — cadastro (nome e e-mail), senha em hash, foto de perfil e data do aceite dos termos;
- `progresso` — nível, experiência (XP), moedas, moldura ativa e bônus de XP em dobro;
- `sinais` — catálogo de sinais, com categoria;
- `exercicios` — exercícios vinculados aos sinais (nível 1 = 10 XP para letras estáticas; nível 2 = 20 XP para sinais com movimento);
- `sessoes_treinamento` — sessões de prática (`em_andamento`, `concluida` ou `abandonada`);
- `resultados` — tentativas com sinal identificado, confiança, acerto e pontos obtidos;
- `pontuacoes` — histórico de pontos usado no perfil e no ranking semanal (contado a partir de segunda-feira, 00:00).

**Tabelas da gamificação**
- `usuario_itens` — itens comprados na loja e quantidade;
- `usuario_molduras` — molduras de perfil do usuário;
- `usuario_configuracoes` — meta diária, velocidade, lembrete, horário, avisos e tamanho da fonte;
- `missoes_resgatadas` — missões semanais já resgatadas;
- `usuario_conquistas` — conquistas obtidas;
- `exclusoes_conta` — motivo de exclusão de conta, sem nenhum dado pessoal.

**Níveis e ligas:**
- XP acumulado por nível (1 a 8): `0`, `100`, `250`, `450`, `700`, `1000`, `1400`, `1900`.
- Liga derivada do nível: níveis `1–2` **Bronze**, `3–4` **Prata**, `5–6` **Ouro**, `7–8` **Diamante**.

### Rotas da API

Todas as rotas, exceto cadastro e login, exigem usuário conectado.

| Grupo | Rota | Descrição |
| --- | --- | --- |
| **Autenticação** | `POST /api/auth/cadastro` | Cria usuário (exige `aceiteTermos: true`), inicia progresso e abre sessão (até 5 por minuto) |
| | `POST /api/auth/login` | Autentica usuário com cookie `HttpOnly` (até 10 por minuto) |
| | `POST /api/auth/logout` | Encerra a sessão atual |
| **Conta** | `GET /api/usuarios/me` | Dados do usuário logado |
| | `PUT /api/usuarios/me` | Atualiza o nome |
| | `PUT /api/usuarios/me/senha` | Altera a senha validando a senha atual |
| | `DELETE /api/usuarios/me` | Exclui a conta e todo o histórico (pede a senha) |
| | `POST /api/usuarios/me/foto` | Envia foto de perfil (JPG, PNG ou WEBP, até 2 MB) |
| | `DELETE /api/usuarios/me/foto` | Remove a foto de perfil |
| | `PUT /api/usuarios/me/moldura` | Troca a moldura da foto |
| | `GET/PUT /api/usuarios/configuracoes` | Consulta ou salva as preferências |
| **Progresso e ranking** | `GET /api/usuarios/progresso` | Nível, XP, liga, posição, pontos, sinais aprendidos, taxa de acerto e sequência |
| | `GET /api/usuarios/conquistas` | Conquistas obtidas e as que faltam |
| | `POST /api/sessoes` | Inicia uma sessão de treino para um sinal |
| | `GET /api/ranking/semana` | Ranking semanal da liga do usuário |
| **Missões e loja** | `GET /api/missoes/semana` | Missões da semana e progresso |
| | `POST /api/missoes/{id}/resgatar` | Resgata a recompensa de uma missão |
| | `GET /api/loja` | Itens, molduras e saldo de moedas |
| | `POST /api/loja/comprar` | Compra um item ou moldura |
| | `POST /api/loja/usar` | Usa um item comprado |
| **Detecção e vídeo** | `POST /api/maos/detectar` | Recebe um quadro (`frame`, opcional `corpo=1` e `sessaoId`) e retorna mãos, letra e certeza; com `sessaoId`, registra o acerto (até 30 quadros por segundo) |
| | `GET /api/sinais/movimento` | Sinais com movimento disponíveis no modelo |
| | `POST /api/maos/movimento` | Classifica a sequência de pontos (mão, corpo e rosto) dos quadros gravados |
| | `POST /api/maos/video` | Classifica um vídeo enviado (`tipo=movimento` ou `tipo=letra`) |

---

## Créditos do dataset

Os vídeos dos sinais com movimento (treino do `modelo_movimento.joblib` e do `modelo_numeros.joblib`, vídeos de exemplo e fotos dos números) foram gravados por um especialista em LIBRAS, com termo de autorização de uso de imagem e dados assinado (o nome dele é citado no TCC, conforme o termo).

As imagens das letras estáticas são do projeto **cnn-libras**, de Lucas Lacerda ([github.com/lucaaslb/cnn-libras](https://github.com/lucaaslb/cnn-libras)). Como o repositório original não possui arquivo de licença explícito, cite o autor no TCC e, caso o SignEdu seja publicado, solicite autorização prévia.

## Acessibilidade (WCAG 2.1)

A interface foi ajustada aos critérios de nível A e AA da WCAG 2.1 que podem ser verificados automaticamente. A verificação usa a ferramenta axe-core (`scripts/avaliar_acessibilidade.js`), que abre todas as páginas logado e lista as violações: antes havia problemas de contraste de cor, barras de progresso sem nome e cartões de conquista com nome diferente do texto visível; depois dos ajustes, **0 violações** em todas as páginas (login, termos, perfil, praticar, conquistas, ranking, loja, conta e configurações). Ajustes feitos:
- textos roxos e cinzas um pouco mais escuros (contraste mínimo de 4,5:1, critério 1.4.3); o roxo da marca continua nos fundos, botões e barras;
- itens bloqueados (níveis, ligas, conquistas) com o ícone apagado, mas o texto legível;
- foco do teclado sempre visível (2.4.7) e link "Pular para o conteúdo" no topo das páginas com menu (2.4.1);
- nome para todas as barras de progresso e situação (conquistada ou bloqueada) lida pelo leitor de tela nos cartões de conquista (4.1.2 e 2.5.3);
- animações reduzidas para quem ativa "reduzir movimento" no sistema (2.3.3).
Nenhuma ferramenta automática cobre toda a WCAG; por isso a plataforma não é declarada "totalmente acessível".
