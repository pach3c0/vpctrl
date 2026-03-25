# VP CTRL — Instruções para IA

## O que é este projeto

**VP CTRL** é uma aplicação desktop comercial em **PyQt6** para controle de Virtual Production no Unreal Engine 5. O operador controla câmeras (posições, lentes, animações) através de uma interface profissional sem tocar no UE5.

## Versões

```
versions/
  v2/   — versão estável (base de referência, não modificar)
  v3/   — versão atual em produção
```

O projeto UE5 em uso com a v3 é **VP_PachecoV5**, mapa **Main**.

## Stack

- **UI**: PyQt6
- **Comunicação tempo real**: WebSocket porta `30020` (Remote Control WS)
- **Configuração/propriedades**: HTTP REST porta `30010` (Remote Control HTTP)
- **Todos os controles de câmera**: OSC UDP porta `8001`
- **Python no UE5**: via `ExecutePythonScript` no Remote Control HTTP (só fora de PIE)
- **Persistência**: QSettings + JSON (`%APPDATA%\VPCtrl\paths.json`)

## Estrutura de arquivos (v3)

```
versions/v3/
├── main.py                  — Entry point, QApplication, splash 3s, logging
├── config/
│   └── settings.py          — Constantes fixas (paths UE5, portas, timings)
├── core/
│   ├── websocket_client.py  — WebSocket QThread + asyncio
│   ├── http_client.py       — HTTP REST + Python executor + cache de Paths
│   ├── osc_client.py        — OSC UDP (python-osc)
│   └── ue5_api.py           — Builders de mensagens WebSocket
├── data/
│   └── models.py            — AppState, PathData
└── ui/
    ├── main_window.py       — Janela principal, connection bar, polling
    ├── camera_panel.py      — Grid 4×2 de cards + sidebar + toda lógica de câmera
    ├── path_sidebar.py      — OBSOLETO (não usado, manter para referência)
    ├── perf_panel.py        — CPU/RAM/GPU
    ├── log_panel.py         — Log em tempo real colapsável
    ├── splash.py            — Splash screen 3s
    └── styles.py            — QSS dark theme completo
```

## Dinâmica do app v3

- **UE5 sempre em Play mode** — o app inicia Viewport Play automaticamente ao conectar
- **EDIT mode**: operador navega com WASD+mouse no UE5, grava posições A/B, ajusta focal/focus
- **PLAY mode**: clique nos cards dispara animações via OSC
- **HTTP REST não funciona durante PIE** — todos os controles de câmera usam OSC
- **Free Camera**: ejecta o pilot do viewport, devolvendo controle livre ao editor

## UI — camera_panel.py

### Grid de cards
- 8 cards em **FlowLayout** — 4 por linha em tela cheia, quebra linha ao reduzir
- Cards têm tamanho fixo, thumbnails 200×113px (16:9)
- Ao reduzir a janela: scroll vertical, cards não mudam de tamanho

### Cada card (_PathCard)
- Header: nome do path + status (● A / ● B / Ready)
- Thumbnail A (borda azul quando ativa) + Thumbnail B (borda vermelha quando ativa)
- Clique esquerdo na thumb: GoTo A/B (EDIT) ou trigger animação (PLAY)
- Clique direito na thumb: abre imagem em tamanho completo
- Botão REC: grava ponto ativo (A ou B) — aparece só em EDIT mode

### Sidebar lateral direita (_ActiveSidebar)
- Mostra path ativo: título, Duration, Focal Length, Focus Distance
- Sliders com debounce 80ms, Duration com debounce 300ms
- Some em PLAY mode

### Thumbnails
- Caminho fixo: `C:\Users\ricar\Documents\Unreal Projects\VP_PachecoV5\Saved\Screenshots\WindowsEditor\`
- Nomes: `path{n}a.png`, `path{n}b.png` (n = 1-8)
- Geradas pelo UE5 via `HighResShot 1920x1080 filename=path{n}a` no evento RecordA/B do BP
- Ao clicar REC: após 1500ms, recarrega a thumb específica com `QPixmapCache.remove()` para evitar cache

## OSC — todos os controles de câmera

| Mensagem OSC | Função |
|---|---|
| `/active_path [int]` | Seta ActivePath no BP (0-based) |
| `/goto/a` | GoTo Point A |
| `/goto/b` | GoTo Point B |
| `/record/a` | Grava posição atual como Point A |
| `/record/b` | Grava posição atual como Point B |
| `/trigger/1` … `/trigger/8` | Dispara animação do path (Play mode) |

## UE5 Remote Control API — Regras críticas

### Endpoints corretos (UE5.5)

| Operação | Endpoint | Método |
|----------|----------|--------|
| Ler propriedade | `/remote/object/property` | PUT + `"access": "READ_ACCESS"` |
| Escrever propriedade | `/remote/object/property` | PUT + `"access": "WRITE_ACCESS"` |
| Chamar função Blueprint | `/remote/object/call` | PUT |
| Executar Python | `/remote/object/call` → `ExecutePythonScript` | PUT |

**NUNCA usar** `/remote/preset/{name}/function` — não existe no UE5.5.

### Formato de chamada de função

```python
PUT /remote/object/call
{
  "objectPath": "<path do actor>",
  "functionName": "<nome exato>",
  "parameters": {},
  "generateTransaction": False
}
```

### Formato de propriedade

```python
# Leitura
PUT /remote/object/property
{"objectPath": "...", "propertyName": "...", "access": "READ_ACCESS"}

# Escrita
PUT /remote/object/property
{"objectPath": "...", "propertyName": "...", "propertyValue": {"prop": valor}, "access": "WRITE_ACCESS"}
```

## Paths fixos dos objetos UE5 (projeto VP_PachecoV5)

```python
# Blueprint principal — controle de câmera e paths
BP_ACTOR_PATH = "/Game/VprodProject/Maps/Main.Main:PersistentLevel.BP_VPB1_C_1"

# Python executor (sempre este objeto para ExecutePythonScript)
PYTHON_OBJECT = "/Script/PythonScriptPlugin.Default__PythonScriptLibrary"

# Media Capture BlackMagic
MEDIA_OUTPUT_ASSET = "/Game/NewBlackmagicMediaOutput.NewBlackmagicMediaOutput"

# CineCameraActors
CAMERA_ACTORS = {
    1: "CineCameraActor_4",
    2: "CineCameraActor_5",
    3: "CineCameraActor_1",
}
```

## Blueprint BP_VPB1

### Variáveis expostas

| Variável | Tipo | Descrição |
|----------|------|-----------|
| `Paths` | Array\<S_CamPath\> | 8 paths de câmera |
| `ActivePath` | Integer | Path selecionado (0-based) |
| `IsMoving` | Boolean | Câmera em animação |

### Struct S_CamPath

```
PointA / PointB   Transform (Location, Rotation)
Duration          Float
FocalLengthA/B    Float
FocusDistanceA/B  Float
```

### Custom Events

```
GoToA / GoToB         — via OSC /goto/a e /goto/b
RecordA / RecordB     — via OSC /record/a e /record/b
                        + Execute Console Command "HighResShot 1920x1080 filename=path{n}a"
TriggerPath1-8        — via OSC /trigger/1 … /trigger/8 (Play mode)
```

### OSC Server no BP_VPB1

- Criado no BeginPlay com `Create OSC Server` (IP 0.0.0.0, porta 8001, Start Listening=false)
- Variável `OSCServer` (Object Reference) salva a referência para evitar garbage collection
- `Self` conectado no pin `Outer` do Create OSC Server
- EndPlay: `Stop` no OSCServer → `SET OSCServer = None`
- BeginPlay protegido: se OSCServer já válido, não cria novo (evita `EADDRINUSE`)

### Input de navegação (EDIT mode em Play)

- Enhanced Input System: `IA_Move` (Axis3D), `IA_Look` (Axis2D), `IA_RightMouse` (Boolean)
- Mapping Context: `IMC_VPB1`
  - WASD → IA_Move com modificadores de direção
  - Mouse XY → IA_Look com Chord Action em IA_RightMouse
  - Mouse Right Button → IA_RightMouse
- Navegação: `Add Actor Local Offset` (velocidade controlada por variável `Velocidade=10`)
- Mouse look: `Add Actor Local Rotation` via Break Vector2D → Make Rotator
- Botão direito pressionado: `Set Input Mode Game Only`
- Botão direito solto: `Set Show Mouse Cursor = true` + `Set Input Mode Game And UI (Do Not Lock)`

## PIE Control

### Iniciar Viewport Play via Python (só fora de PIE)

```python
script = "import unreal; unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()"

PUT /remote/object/call
{
  "objectPath": "/Script/PythonScriptPlugin.Default__PythonScriptLibrary",
  "functionName": "ExecutePythonScript",
  "parameters": {"PythonScript": "<script>"},
  "generateTransaction": false
}
```

### Limitações críticas do Python Script no UE5.5

- `ExecutePythonScript` **não executa durante PIE** — erro `The Editor is currently in a play mode`
- Objetos do mundo PIE (`UEDPIE_0_Main`) **não são acessíveis** via Remote Control HTTP — retornam 400
- O Remote Control WebSocket **não envia eventos** de mudança de estado PIE
- **Conclusão: HTTP/Python não funcionam em Play mode — usar OSC para tudo**

## Viewport Pilot

```python
# Travar viewport no BP_VPB1
"actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors(); "
"actor = next((a for a in actors if 'BP_VPB1_C_1' in a.get_path_name()), None); "
"unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(actor)"

# Liberar (Free Camera)
"unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).eject_pilot_level_actor()"
```

`pilot_level_actor` trava o viewport do editor — **não** muda a saída BlackMagic.

## Camera Switch (Media Capture BlackMagic)

```python
panel = unreal.MediaFrameworkCapturePanelLibrary.get_media_capture_panel()
output = unreal.load_asset('/Game/NewBlackmagicMediaOutput.NewBlackmagicMediaOutput')
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
cam = next((x for x in actors if 'CineCameraActor_4' in str(x.get_path_name())), None)
panel.stop_capture()
panel.empty_viewport_capture()
panel.add_viewport_capture(output, cam, unreal.MediaCaptureOptions())
panel.start_capture()
```

- Funciona **sem PIE** (usa editor subsystems)
- O aviso `Render Target pixel format doesn't match` é normal
- Media Capture deve estar aberto: Window → Virtual Production → Media Capture

## Cache de Paths

O array `Paths` é lido uma vez no connect (`warm_cache`) e mantido em `_paths_cache`. Escritas individuais atualizam o cache e fazem write-back do array completo de forma assíncrona. **Durante PIE o HTTP não funciona** — o cache não é atualizado em Play mode.

## Plugins UE5 necessários

1. Remote Control API
2. Remote Control WebSocket
3. OSC
4. Python Script Plugin
5. Enhanced Input
6. Project Settings → Remote Control → Security → **Allow Default Objects to be exposed remotely** ✓

## Convenções de código

- Chamadas HTTP em daemon threads (nunca bloqueiam a UI)
- Debounce nos sliders: 80ms (sidebar), 300ms (duration spinbox)
- `logger` em cada módulo com `logging.getLogger(__name__)`
- Nomes de variáveis e comentários em português
- Thumbnails recarregadas com `QPixmapCache.remove()` para evitar cache do Qt

## Pendências v3

1. **NDI**: chamada Open NDI não está trocando a mídia — pendente investigação
2. **Lens override sliders**: não funcionando conforme esperado — revisar após batch atual
3. **Screenshot no BP**: `HighResShot` salva em `Saved/Screenshots/WindowsEditor/` — nome dinâmico montado com Append nodes no BP usando ActivePath+1
