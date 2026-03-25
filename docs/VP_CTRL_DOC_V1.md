# VP CTRL — Documentação Técnica v1.0

## Visão Geral

VP CTRL é uma aplicação desktop comercial em PyQt6 para controle de Virtual Production no Unreal Engine 5 via Remote Control API. O operador controla câmeras, posições e lentes através de uma interface profissional sem necessidade de interagir diretamente com o UE5.

---

## Stack Técnica

| Componente | Tecnologia |
|------------|------------|
| UI Desktop | PyQt6 |
| Comunicação tempo real | WebSocket (porta 30020) |
| Configuração/propriedades | HTTP REST (porta 30010) |
| Triggers em Play mode | OSC UDP (porta 8001) |
| Persistência de settings | QSettings |
| Threading | QThread + asyncio (WebSocket), daemon threads (HTTP/OSC) |

---

## Estrutura de Arquivos

```
vp_control/
├── main.py                  — Entry point, QApplication, logging
├── config/
│   └── settings.py          — Constantes e defaults
├── core/
│   ├── websocket_client.py  — Cliente WebSocket (QThread + asyncio)
│   ├── http_client.py       — Cliente HTTP REST + Python executor + PIE control
│   ├── osc_client.py        — Cliente OSC UDP (python-osc)
│   └── ue5_api.py           — Builders de mensagens WebSocket
└── ui/
    ├── main_window.py       — Janela principal, connection bar, polling
    ├── camera_panel.py      — Painel de câmera (EDIT/PLAY, CAM 1-3, PATH 1-8)
    ├── lens_panel.py        — Painel de lente (Focal Length, Focus Distance)
    └── styles.py            — QSS dark broadcast theme
```

---

## Configuração de Conexão

Campos configuráveis na connection bar (persistidos via QSettings):

| Campo | Default | Descrição |
|-------|---------|-----------|
| Host | 127.0.0.1 | IP do UE5 |
| Porta | 30020 | Porta WebSocket Remote Control |
| Preset | VPControlPreset | Nome do Remote Control Preset |
| BP Path | /Game/.../BP_CameraSwitcher13_C_1 | Path do actor no level |

---

## Plugins UE5 Necessários (Configuração do Usuário Final)

1. **Remote Control API** — habilitar em Plugins
2. **Remote Control WebSocket** — porta 30020
3. **OSC** — habilitar em Plugins (para triggers em Play mode)
4. **Python Script Plugin** — para controle de PIE via Remote Control
5. **Project Settings → Plugins → Remote Control → Security**:
   - ✓ Allow Default Objects to be exposed remotely *(necessário para Play/Stop PIE)*

---

## Arquitetura de Comunicação

### WebSocket (porta 30020)
- Conexão persistente com reconexão automática
- Usado para: polling de `IsMoving` (500ms) e `ActivePath` (1000ms)
- Mensagens: `object.property` READ_ACCESS

### HTTP REST (porta 30010)
- Chamadas em background threads (não bloqueia UI)
- Usado para:
  - Escrever propriedades: `ActivePath`, `Duration`, `FocalLengthOverride`, `FocusDistanceOverride`
  - Chamar funções Blueprint: `RecordA`, `RecordB`, `GoToA`, `GoToB`
  - Controlar PIE: `editor_request_begin_play()`, `editor_request_end_play()` via Python

### OSC UDP (porta 8001)
- Usado para triggers de path em **Play mode** (PIE world)
- Endereços: `/path1` a `/path8`
- O servidor OSC é iniciado no Blueprint via `Event BeginPlay`

---

## Blueprint BP_CameraSwitcher13

### Variáveis Principais

| Variável | Tipo | Descrição |
|----------|------|-----------|
| Paths | Array\<S Camera Path\> | Array com 8 paths, cada um com PointA, PointB, Duration, FocalLengthA/B, FocusDistanceA/B |
| ActivePath | Integer | Path ativo (0-based) |
| IsMoving | Boolean | Câmera em animação |
| Duration | Float | Duração da animação |
| OSCServer | OSCServer | Referência ao servidor OSC |
| Cam1 | CineCameraComponent | Componente da câmera |

### Struct S Camera Path

```
PointA          Transform  (Location, Rotation, Scale)
PointB          Transform  (Location, Rotation, Scale)
Duration        Float
FocalLengthA    Float
FocusDistanceA  Float
FocalLengthB    Float
FocusDistanceB  Float
```

### Custom Events (chamados via HTTP REST)

| Evento | Descrição |
|--------|-----------|
| RecordA | Grava posição atual da câmera como ponto A do ActivePath |
| RecordB | Grava posição atual da câmera como ponto B do ActivePath |
| GoToA | Move câmera instantaneamente para ponto A do ActivePath |
| GoToB | Move câmera instantaneamente para ponto B do ActivePath |
| TriggerPath1-8 | Dispara animação A→B do path correspondente |

### OSC Server (Event Graph)
- Iniciado no `Event BeginPlay` na porta 8001
- Recebe mensagens e roteia via `Switch on String`:
  - `/path1` a `/path8` → `TriggerPath1` a `TriggerPath8`
  - `/goto/a` → `GoToA` *(reservado para futuro)*
  - `/goto/b` → `GoToB` *(reservado para futuro)*
  - `/record/a` → `RecordA` *(reservado para futuro)*
  - `/record/b` → `RecordB` *(reservado para futuro)*

---

## Interface do Usuário

### Connection Bar (sempre visível)
- Status dot (verde/vermelho)
- Host, Porta, Preset, BP Path
- Botão Conectar/Desconectar
- Controles desabilitados enquanto desconectado

### Camera Panel

#### Modo EDIT (laranja)
- PATH 1-8: seleciona o path ativo (define `ActivePath` no UE5)
- **IR A** / **IR B**: move câmera para posição A ou B via HTTP `GoToA`/`GoToB`
- **GRAVAR A** / **GRAVAR B**: grava posição atual via HTTP `RecordA`/`RecordB`
- GRAVAR A/B desabilitado em Play mode

#### Modo PLAY (verde)
- Entra em PIE via Python Remote Control
- PATH 1-8: dispara animação via OSC `/path1` a `/path8`
- IR A/B desabilitado em Play mode

#### CAM 1 / CAM 2 / CAM 3
- Seletor visual de câmera (laranja quando selecionada)
- Atualmente visual apenas — futuro: trocar blueprint ativo

#### Duração
- Spinbox 0.1s a 60s, envia para `Duration` via HTTP

### Lens Panel
- **Focal Length** (10-300mm): slider linear + spinbox, debounce 50ms
- **Focus Distance** (10-100.000cm): slider logarítmico + spinbox, debounce 50ms
- Envia via HTTP para `FocalLengthOverride` e `FocusDistanceOverride` no `Cam1`

### Status Bar
- `● Desconectado` — cinza
- `● Parado` — cinza claro
- `● Animando PATH X` — laranja bold

---

## Fluxo de Uso Típico

```
1. Abrir app → interface visível imediatamente
2. Configurar Host/Porta/Preset/BP Path → Conectar
3. Modo EDIT:
   a. Selecionar CAM → selecionar PATH
   b. Posicionar câmera no UE5 (pilotando o actor)
   c. GRAVAR A → posicionar câmera na posição final → GRAVAR B
   d. Ajustar Focal Length e Focus Distance
   e. IR A / IR B para verificar posições gravadas
4. Modo PLAY:
   a. App entra em PIE no UE5
   b. Apertar PATH 1-8 → animação acontece
5. Voltar para EDIT para ajustes finos
```

---

## Dependências Python

```
PyQt6
websockets
requests
python-osc
```

---

## Limitações Conhecidas v1.0

1. **CAM 1/2/3** — seleção apenas visual, não troca o Blueprint ativo no UE5
2. **OSC só em Play mode** — servidor OSC inicia no BeginPlay, não no Editor
3. **GoToA/GoToB via HTTP** — funciona no Editor world sem Play mode
4. **TriggerPath via OSC** — só funciona em Play mode (PIE world)
5. **Paths 3-8** — existem no Blueprint mas sem posições gravadas (zeros)
6. **Remote Control WebSocket** — não suporta `object.callfunction` nem `preset.callfunction` para funções Blueprint no UE5.5
