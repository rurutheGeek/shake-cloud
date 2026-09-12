# Shared Ollama service

This is the single Ollama process for game1. Pokémon AI and generic RAG join
the `game1-ai` Docker network; neither project starts a second Ollama instance.
The host listener is loopback-only and models live below
`/srv/game1/ollama/models` by default.

```bash
python3 manage.py init
python3 manage.py up
python3 manage.py pull qwen3:4b
python3 manage.py status
python3 manage.py down
```

`up` only pins the pulled image digest and starts the service. Model downloads
are always explicit. Use `OLLAMA_IMAGE` and `OLLAMA_VULKAN=1` only after the
game1 GPU and driver check; the default is a CPU-safe image configuration.
Backups require root and are cold snapshots of the model cache and deployment
files. Do not place model credentials or personal data in `.env`.
