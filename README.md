# FieldEye

O FieldEye transforma o vídeo de um jogo ou treino em dados de desempenho. Você
envia a gravação e recebe de volta o mesmo vídeo com cada jogador rastreado,
junto com a velocidade e a distância que cada um percorreu, tudo a partir de
uma câmera comum, sem GPS, coletes ou equipamento caro.

Por baixo, o sistema encontra e acompanha todos os jogadores em campo, separa os
times pela cor do uniforme e calcula as métricas físicas de cada atleta. Quando
você marca os quatro cantos do campo no próprio vídeo, ele passa a medir as
distâncias em metros de verdade e a ignorar quem está fora da área, como a
torcida e o banco de reservas. No final você tem o vídeo anotado com as caixas e
as velocidades, um gráfico de velocidade ao longo do tempo, a exportação em CSV
ou PDF e um histórico das análises no seu perfil.

## Como funciona

O processamento roda em um worker assíncrono e segue estas etapas:

1. Leitura do vídeo com OpenCV (normalizado para frame rate constante).
2. Detecção de pessoas e bola com YOLOv8.
3. Classificação de time por cor (K-means sobre a cor do uniforme).
4. Rastreamento com BoT-SORT (mantém o ID do jogador ao longo do jogo).
5. Homografia: conversão de pixels para metros.
6. Física: velocidade, distância e sprints.
7. Interpolação de falhas de rastreamento e consolidação de IDs.
8. Renderização do vídeo anotado.

## Arquitetura

Microserviços orquestrados por Docker Compose, com Traefik como gateway.

| Serviço | Papel | Stack |
|---|---|---|
| `traefik` | Gateway/roteamento e rate limiting | Traefik |
| `frontend` | Interface web | Next.js, TypeScript, Tailwind |
| `auth-service` | Contas e autenticação (JWT) | FastAPI |
| `video-service` | Upload, jobs e fila | FastAPI |
| `analytics-service` | Resultados e exportações | FastAPI |
| `worker` | Processamento de IA | Celery, YOLOv8, BoT-SORT, OpenCV |
| `redis` | Fila de tarefas e cache | Redis |
| `postgres` | Banco de dados | PostgreSQL |

## Requisitos

- Docker Desktop (Windows/macOS) ou Docker Engine + Compose (Linux).
- Cerca de 8 GB de RAM.
- Espaço em disco para os modelos e os vídeos processados.
- Opcional, para o modo "Qualidade": GPU NVIDIA com drivers atualizados
  (habilita o CUDA no worker — ver [Modos de análise](#modos-de-análise)).

## Como rodar (autohospedagem)

O projeto roda inteiramente na sua máquina; não é preciso servidor nem nuvem.

```bash
# 1. Clonar o repositório
git clone <url-do-repositorio>
cd FieldEye

# 2. Criar o arquivo de ambiente a partir do modelo
cp .env.example .env
#    Edite o .env e troque as senhas/segredos (POSTGRES_PASSWORD, JWT_SECRET).
#    Opcional: defina HOST_DATA_DIR para guardar os vídeos fora do projeto.

# 3. Subir tudo (a primeira vez baixa as imagens e compila — pode demorar)
docker compose up --build
```

Quando os contêineres estiverem no ar, abra **http://localhost**, crie uma conta
e envie um vídeo. O primeiro processamento também baixa o modelo de detecção.

Para parar: `docker compose down` (os dados do banco e os vídeos são preservados).

### Acelerar com GPU NVIDIA (opcional)

Se a máquina tem uma GPU NVIDIA com drivers instalados, suba com o override de
GPU para o worker usar CUDA (bem mais rápido no modo Qualidade):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Sem esse override, tudo roda em CPU e funciona em qualquer máquina. A aceleração
por GPU do PyTorch é exclusiva de placas NVIDIA; GPUs AMD/Intel usam a CPU.

## Como usar

1. Crie uma conta e faça login.
2. No painel, selecione um vídeo.
3. Escolha o **modo de análise** (Velocidade ou Qualidade) e a **área**
   (marcar a região no vídeo ou usar um campo oficial).
4. Se escolher marcar a região, clique nos quatro cantos do campo sobre o frame.
5. Clique em **Executar análise**. Acompanhe o progresso no painel.
6. Ao terminar, abra os resultados: vídeo anotado, métricas por jogador,
   gráfico de velocidade e exportação em CSV/PDF.

## Modos de análise

- **Velocidade**: modelo leve (YOLOv8n) em baixa resolução. Rápido e roda em
  qualquer CPU. Bom para testes e vídeos com boa visão dos jogadores.
- **Qualidade**: modelo maior (YOLOv8s) em resolução alta. Detecta jogadores
  pequenos e distantes (câmera alta/tática), ao custo de mais tempo e memória.

No modo Qualidade você escolhe, no próprio site, se o processamento roda na
**GPU (NVIDIA/CUDA)** ou na **CPU**. A opção de GPU só tem efeito se o projeto
tiver sido iniciado com o override de GPU (ver acima); em qualquer outro caso, o
processamento roda em CPU, mais lento porém compatível com qualquer máquina.

### Juntar jogadores

Quando o mesmo jogador recebe dois identificadores diferentes (o rastreamento
troca o ID depois de uma oclusão longa), a tela de resultados permite
selecionar os dois cards e juntá-los em um só, somando as métricas.

## Configuração

As principais variáveis ficam no `.env` (veja o `.env.example` comentado):

- `POSTGRES_PASSWORD`, `JWT_SECRET`: **troque** antes de usar.
- `HOST_DATA_DIR`: pasta no host onde os vídeos são guardados.
- `MODEL_NAME`, `YOLO_IMGSZ`, `YOLO_CONF`: ajustes do modo Velocidade.
- `MODEL_NAME_HQ`, `YOLO_IMGSZ_HQ`, `YOLO_CONF_HQ`: ajustes do modo Qualidade.

## Estrutura do projeto

```
FieldEye/
├── docker-compose.yml        # orquestração dos serviços
├── gateway/                  # configuração do Traefik
├── frontend/                 # aplicação Next.js
└── services/
    ├── auth/                 # autenticação (FastAPI)
    ├── video/                # upload e jobs (FastAPI)
    ├── analytics/            # resultados e exportações (FastAPI)
    └── worker/               # pipeline de IA (Celery + YOLOv8)
```

## Limitações conhecidas

- A distinção entre goleiro e árbitro por cor não é perfeita; ambos podem cair
  na categoria "outros".
- Câmeras muito distantes tornam a detecção difícil, mesmo no modo Qualidade.
- Um mesmo jogador pode receber IDs diferentes após oclusões longas.

Essas frentes estão em evolução.

## Licença

© 2026 Albuqmarq. Todos os direitos reservados.

Este repositório é público apenas para fins de avaliação e portfólio. Não é
concedida permissão para copiar, modificar, redistribuir ou usar este código,
no todo ou em parte, em outros projetos sem autorização expressa do autor.
Consulte o arquivo [LICENSE](LICENSE) para os termos completos.
