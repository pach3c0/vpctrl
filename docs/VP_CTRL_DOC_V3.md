# VP CTRL — Documentação Técnica v3.0

## Visão Geral

VP CTRL é uma aplicação desktop comercial em PyQt6 para controle de Virtual Production no Unreal Engine 5 via Remote Control API. O operador controla câmeras, posições e lentes através de uma interface profissional sem necessidade de interagir diretamente com o UE5.

> **Nota:** A v3 parte da mesma base da v2. As funcionalidades são idênticas. Esta documentação reflete o estado atual do código em `versions/v3/`.

---

## Stack Técnica

| Componente | Tecnologia |
|------------|------------|
| UI Desktop | PyQt6 |
| Comunicação tempo real | WebSocket (porta 30020) |
| Configuração/propriedades | HTTP REST (porta 30010) |
| Triggers em Play mode | OSC UDP (porta 8001) |
| Persistência local | QSettings + JSON (`%APPDATA%\VPCtrl\paths.json`) |
| Threading | QThread + asyncio (WebSocket), daemon threads (HTTP/OSC) |

---

## Estrutura de Arquivos

```
versions/v3/
├── main.py                   — Entry point, QApplication, splash, logging
├── config/
│   └── settings.py           — Constantes fixas (host, portas, paths UE5)
├── core/
│   ├── websocket_client.py   — Cliente WebSocket (QThread + asyncio)
│   ├── http_client.py        — HTTP REST + Python executor + PIE control + cache de Paths
│   ├── osc_client.py         — Cliente OSC UDP (python-osc)
│   └── ue5_api.py            — Builders de mensagens WebSocket
├── data/
│   └── models.py             — AppState, PathData (persistência JSON)
└── ui/
    ├── main_window.py        — Janela principal, connection bar, polling IsMoving
    ├── camera_panel.py       — Painel EDIT/PLAY, PATH 1-8, botões A/B/REC/Duration
    ├── path_sidebar.py       — Sidebar de lente: Focal Length e Focus Distance por ponto A/B
    ├── lens_panel.py         — Painel de lente global (reservado)
    ├── perf_panel.py         — Barra de performance (CPU/RAM/GPU)
    ├── log_panel.py          — Painel de log em tempo real (colapsável)
    ├── spout_widget.py       — Widget Spout (reservado)
    ├── splash.py             — Splash screen de 3 segundos
    └── styles.py             — QSS dark broadcast theme completo
```

---

## Configurações Fixas (`config/settings.py`)

Todas as configurações são fixas no código — invisíveis ao usuário final:

| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `DEFAULT_HOST` | `127.0.0.1` | IP padrão do UE5 |
| `WS_PORT` | `30020` | Porta WebSocket Remote Control |
| `HTTP_PORT` | `30010` | Porta HTTP Remote Control |
| `OSC_PORT` | `8001` | Porta OSC UDP |
| `BP_ACTOR_PATH` | `/Game/VprodProject/Maps/Main.Main:PersistentLevel.BP_VPB1_C_1` | Path do Blueprint no level |
| `PRESET_NAME` | `VPControlPreset` | Nome do Remote Control Preset |
| `POLLING_INTERVAL` | `500ms` | Frequência do poll de `IsMoving` |
| `GRAVAR_PULSE_MS` | `200ms` | Duração do flash do botão REC |
| `NUM_PATHS` | `8` | Número de paths de câmera |
| `MEDIA_OUTPUT_ASSET` | `/Game/NewBlackmagicMediaOutput...` | Asset BlackMagic para Media Capture |
| `CAMERA_ACTORS` | `{1: CineCameraActor_4, 2: _5, 3: _1}` | Mapeamento câmera → actor UE5 |

---

## Plugins UE5 Necessários

1. **Remote Control API** — habilitar em Plugins
2. **Remote Control WebSocket** — porta 30020
3. **OSC** — habilitar em Plugins (para triggers de path em Play mode)
4. **Python Script Plugin** — para controle de PIE e pilot de viewport
5. **Project Settings → Plugins → Remote Control → Security**:
   - ✓ Allow Default Objects to be exposed remotely *(necessário para PIE Play/Stop e viewport pilot)*

---

## Arquitetura de Comunicação

### WebSocket (porta 30020)
- Conexão persistente, reconexão automática via `WebSocketThread` (QThread + asyncio)
- Usado para polling de `IsMoving` a cada 500ms
- Mensagens no formato `object.property` com `READ_ACCESS`

### HTTP REST (porta 30010)
- Chamadas síncronas em daemon threads (não bloqueiam a UI)
- Endpoints utilizados:

| Operação | Endpoint | Método |
|----------|----------|--------|
| Ler propriedade | `/remote/object/property` | PUT + `READ_ACCESS` |
| Escrever propriedade | `/remote/object/property` | PUT + `WRITE_ACCESS` |
| Chamar função Blueprint | `/remote/object/call` | PUT |
| Executar Python no UE5 | `/remote/object/call` → `ExecutePythonScript` | PUT |

### OSC UDP (porta 8001)
- Usado para triggers de path em **Play mode** (mundo PIE)
- Endereços: `/path1` a `/path8`
- O servidor OSC é iniciado no BP via `Event BeginPlay`

---

## Blueprint BP_VPB1

### Variáveis Expostas via Remote Control

| Variável | Tipo | Acesso | Descrição |
|----------|------|--------|-----------|
| `Paths` | Array\<S_CamPath\> | R/W | Array com 8 paths |
| `ActivePath` | Integer | R/W | Path selecionado (0-based) |
| `IsMoving` | Boolean | R | Câmera em animação |

### Struct S_CamPath

```
PointA           Transform  (Location, Rotation)
PointB           Transform  (Location, Rotation)
Duration         Float
FocalLengthA     Float
FocalLengthB     Float
FocusDistanceA   Float
FocusDistanceB   Float
```

### Custom Events (chamados via HTTP `/remote/object/call`)

| Evento | Descrição |
|--------|-----------|
| `GoToA` | Move câmera instantaneamente para ponto A do ActivePath |
| `GoToB` | Move câmera instantaneamente para ponto B do ActivePath |
| `RecordA` | Grava posição atual da câmera como ponto A |
| `RecordB` | Grava posição atual da câmera como ponto B |
| `TriggerPath1`–`TriggerPath8` | Dispara animação A→B via OSC |

### OSC Server
- Iniciado no `Event BeginPlay` na porta 8001
- Rotas: `/path1` a `/path8` → `TriggerPath1` a `TriggerPath8`

---

## Cache de Paths (`http_client.py`)

O array `Paths` do BP é carregado uma vez no connect (`warm_cache`) e mantido em memória local (`_paths_cache`). Todas as escritas de campos individuais (duration, focal, focus) atualizam o cache e fazem write-back assíncrono do array completo.

```
fetch_paths()          → lê array do UE5
warm_cache()           → popula _paths_cache + descobre chaves UUID
set_path_field_async() → atualiza campo no cache + write-back
set_path_transform()   → atualiza transform PointA/B no cache + write-back
```

---

## PIE Control

Iniciado e encerrado via Python Script executado pelo Remote Control:

```python
# Begin Play
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()

# End Play
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
```

**Limitação conhecida:** `ExecutePythonScript` não executa durante PIE — o UE5 bloqueia scripts Python enquanto o Play mode está ativo. Isso impede detecção de estado PIE via Python.

---

## Viewport Pilot

Ao conectar, o app automaticamente trava o viewport do editor no BP_VPB1 via Python:

```python
# Pilot (travar viewport no BP_VPB1)
pilot_level_actor(actor)

# Eject (liberar para free camera)
eject_pilot_level_actor()
```

O botão **Free Camera** na connection bar alterna entre os dois estados.

---

## Interface do Usuário

### Connection Bar (sempre visível)
- Status dot (verde/cinza)
- Campo Host (IP do UE5)
- Botão **Free Camera** — libera/trava viewport
- Botão **Connect / Disconnect**

### Perf Bar
- CPU%, RAM (GB), GPU% — atualizado a cada 1s via `psutil`

### Camera Panel

#### Modo EDIT (laranja)
- **PATH 1–8**: seleciona o path ativo (seta `ActivePath` no UE5 + auto-GoToA)
- **[A]** / **[B]**: move câmera para posição A ou B (`GoToA` / `GoToB`) + atualiza sidebar
- **[REC]**: grava ponto ativo (A ou B) via `RecordA` / `RecordB` + auto-sync
- **Duration spinbox**: debounce 300ms, envia duração para o path

#### Modo PLAY (verde)
- Entra em PIE via `editor_request_begin_play()`
- **PATH 1–8**: dispara via OSC `/path1` a `/path8`
- Botões A/B/REC desabilitados
- Sidebar oculta

### Path Sidebar (só em EDIT)
Mostra e edita os parâmetros de lente do ponto A ou B do path selecionado:
- **Focal Length** (10–300mm) — slider + spinbox, debounce 80ms
- **Focus Distance** (50–50.000cm) — slider + spinbox, debounce 80ms
- Sincroniza automaticamente com `_paths_cache` após cada REC

### Log Panel (colapsável)
- Mostra todos os logs em tempo real (DEBUG, INFO, WARNING, ERROR)
- Máximo 500 linhas, rolagem automática

### Status Bar
- `● Disconnected` — cinza
- `● Idle` — cinza claro
- `● Syncing…` — azul
- `● Running PATH X` — laranja bold

---

## Persistência de Dados

### QSettings
- Salva: host, geometria da janela

### JSON (`%APPDATA%\VPCtrl\paths.json`)
Salva estado local dos paths (nomes, durations):
```json
{
  "last_host": "127.0.0.1",
  "paths": [
    {"name": "PATH 1", "duration": 3.0},
    ...
  ]
}
```

---

## Fluxo de Uso Típico

```
1. Abrir app → splash 3s → janela maximizada
2. Digitar Host → Conectar
3. App: auto-pilot viewport no BP_VPB1, sync dos paths, habilita controles
4. Modo EDIT:
   a. Selecionar PATH → câmera vai para ponto A automaticamente
   b. Posicionar câmera no UE5 → [REC] grava ponto A
   c. Posicionar câmera na posição final → clicar [B] → [REC] grava ponto B
   d. Ajustar Focal Length e Focus Distance na sidebar
   e. [A] / [B] para verificar posições gravadas
5. Modo PLAY:
   a. Clicar PLAY → UE5 entra em PIE
   b. Clicar PATH 1–8 → animação dispara via OSC
6. Clicar EDIT → UE5 sai do PIE → volta a modo edição
```

---

## Dependências Python

```
PyQt6
websockets
requests
python-osc
psutil
```

---

## Limitações Conhecidas v3.0

1. **Detecção de PIE**: `ExecutePythonScript` não executa durante PIE — impossível detectar estado PIE via polling HTTP/Python enquanto PIE está ativo. Investigar alternativa via WebSocket events ou outro mecanismo.
2. **PIE begin_play**: `editor_request_begin_play()` pode iniciar em modo viewport ao invés de PIE dependendo da configuração do editor. Usuário deve garantir que o modo Play esteja configurado como "Play in Editor" em Editor Preferences → Level Editor → Play.
3. **OSC só em Play mode**: servidor OSC inicia no `BeginPlay` do BP — triggers de path não funcionam fora do PIE.
4. **Camera switch**: troca de câmera via Media Capture BlackMagic funciona apenas sem PIE (usa editor subsystems).
5. **Paths 3–8**: existem no Blueprint mas podem estar sem posições gravadas (zeros).
6. **Remote Control WebSocket**: não suporta `object.callfunction` para funções Blueprint no UE5.5 — todas as chamadas de função usam HTTP REST.
