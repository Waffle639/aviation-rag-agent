# Docker

Docker empaqueta el runtime del proyecto: Python 3.12, dependencias, Streamlit, PyTorch CPU, Transformers y los comandos de trabajo. La base principal sigue siendo Supabase mediante `DATABASE_URL`.

## Uso Principal

Arrancar el chatbot contra Supabase:

```bash
docker compose up -d chat
```

Abrir:

```text
http://localhost:8502
```

Arrancar el dashboard de evaluaciones contra Supabase:

```bash
docker compose up -d dashboard
```

Abrir:

```text
http://localhost:8501
```

Inicializar Prompt Guard en un volumen local:

```bash
docker compose run --rm model-init
```

Ejecutar el agente:

```bash
docker compose run --rm worker python -m rag.query_test_agent "your question"
```

Ejecutar el agente con memoria persistente:

```bash
docker compose run --rm worker python -m rag.query_test_memory
docker compose run --rm worker python -m rag.query_test_memory --session <session-uuid> "follow-up question"
```

Ejecutar evaluaciones:

```bash
docker compose run --rm worker python -m evaluation.runner
```

Sincronizar NTSB:

```bash
docker compose run --rm worker python -m ntsb.sync.cli incremental
```

Parar servicios:

```bash
docker compose down
```

## Deploy

Construir la imagen web del chatbot:

```bash
docker build --target chat -t aviation-rag-chat:latest .
```

La imagen `chat` incluye el agente, memoria PostgreSQL, Streamlit, OpenAI, LangGraph, PyTorch CPU y Prompt Guard. Necesita `DATABASE_URL`, `OPENAI_API_KEY` y, si Prompt Guard no está cacheado o el modelo es gated, `HF_TOKEN`.

Construir la imagen web del dashboard:

```bash
docker build --target dashboard -t aviation-rag-dashboard:latest .
```

El dashboard solo necesita `DATABASE_URL` para conectarse a Supabase. La plataforma de despliegue debe ejecutar la imagen publicando el puerto `8501`.

Construir el worker únicamente si la plataforma también ejecutará el agente, ingestas, evaluaciones o sincronizaciones:

```bash
docker build --target worker -t aviation-rag-worker:latest .
```

El worker recibe en ejecución las variables que necesite, entre ellas:

```text
DATABASE_URL
OPENAI_API_KEY
HF_TOKEN
```

Usa `DASHBOARD_REQUIRE_SSL=true` con Supabase. No subas `.env` a la imagen ni al repositorio.

Los tests no forman parte de las imágenes Docker. Se ejecutan desde el entorno local antes de construir o publicar:

```bash
pytest
```

## Cuándo Usarlo

Docker merece la pena para deploy, CI, pruebas reproducibles, nuevos colaboradores o cuando quieras evitar conflictos de dependencias. Si trabajas solo en local y tu `.venv` funciona, Docker es útil pero no obligatorio.
