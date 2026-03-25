# VP CTRL — Documentação de Arquitetura
**Virtual Production Control · v1.0**

## 1. Visão Geral do Sistema

VP CTRL é uma aplicação de controle para produção virtual (Virtual Production) que opera como camada de controle sobre o Unreal Engine 5 via Remote Control API. O operador controla câmeras, chroma key, iluminação, animações e outros objetos da cena UE5 através de uma interface web moderna, sem precisar tocar no editor do Unreal Engine.

### Premissas fundamentais
- O UE5 precisa estar aberto com o projeto carregado antes de usar o VP CTRL
- O app não substitui o UE5 — ele o controla remotamente
- Todos os objetos controlados têm nomes fixos (convenção VPCtrl_*)
- Presets e painéis são salvos por projeto UE5 (não por IP)

## 2. Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Backend | Python 3.11+ / FastAPI async | I/O não-bloqueante ideal para chamadas HTTP ao UE5 |
| Comunicação real-time | WebSocket (FastAPI nativo) | Tally, status de conexão, FPS/GPU ao vivo |
| Frontend | HTML5 / CSS3 / JavaScript puro | Zero dependências, leve, funciona em qualquer browser |
| Preview de vídeo | NDI → MJPEG bridge (Python) | Browser não fala NDI nativo; backend decodifica e serve como stream HTTP |
| Janela desktop | pywebview | Encapsula o HTML em janela nativa sem chrome do browser |
| Empacotamento | PyInstaller | Gera .exe standalone sem Python instalado na máquina |
| Dados locais | JSON por projeto | Simples, editável, sem banco de dados |

## 3. Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────┐
│                    MÁQUINA DE PRODUÇÃO                   │
│                                                          │
│  ┌──────────────┐    HTTP REST     ┌──────────────────┐  │
│  │  VP CTRL     │◄────────────────►│  Unreal Engine 5  │  │
│  │  (FastAPI)   │    porta 30010   │  Remote Control   │  │
│  │              │                  │  API              │  │
│  │  porta 8000  │    NDI stream    │                   │  │
│  │              │◄────────────────│  NDI Output       │  │
│  └──────┬───────┘                  └──────────────────┘  │
│         │ WebSocket + HTTP                                │
│         │                                                 │
│  ┌──────▼───────┐                                        │
│  │  pywebview   │  ← janela nativa (segundo monitor)     │
│  │  (HTML/JS)   │                                        │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
         │
         │ HTTP (rede local)
         ▼
┌─────────────────┐
│  Tablet / Outro │  ← browser, mesmo IP da máquina
│  PC na rede     │
└─────────────────┘
```

## 4. Plugin UE5 — Estratégia em 2 Fases

### Fase 1 — Blueprint + Remote Control Preset (manual)
Para desenvolvimento e MVP. O técnico configura manualmente o projeto UE5 de referência:

- Cria os atores com nomes fixos na cena (VPCtrl_Cam1, VPCtrl_Cam2, VPCtrl_Cam3, VPCtrl_PlaneB1, VPCtrl_Composure, etc.)
- Configura o Remote Control Preset com todas as propriedades expostas
- Cria Blueprints para Custom Events (switcher de câmera, Timeline de Camera Paths)
- Habilita os plugins necessários: Remote Control API, NDI IO Plugin

**Resultado**: permite desenvolver e testar 100% do backend Python e frontend sem C++.

### Fase 2 — Plugin C++ (produto comercial)
Para distribuição ao cliente. O plugin automatiza a Fase 1:

- Ao ser instalado no projeto UE5 do cliente, cria todos os atores automaticamente
- Configura o Remote Control Preset com um clique
- Instala os Blueprints necessários
- Executa lógica de alta performance no lado UE5 (Timeline para Camera Paths, interpolação)

**Nota**: A lógica de interpolação de Camera Paths DEVE rodar no lado UE5 (C++ ou Blueprint Timeline), nunca ser conduzida frame a frame pelo Python, pois causaria movimento instável.

## 5. Nomes Fixos — Convenção VPCtrl_*

Todos os objetos controlados pelo VP CTRL têm nomes fixos no UE5. Isso garante que a API Python sempre sabe onde encontrar cada objeto:

| Nome UE5 | Tipo | Função |
|----------|------|--------|
| VPCtrl_Cam1 | CineCameraActor | Câmera virtual 1 |
| VPCtrl_Cam2 | CineCameraActor | Câmera virtual 2 |
| VPCtrl_Cam3 | CineCameraActor | Câmera virtual 3 |
| VPCtrl_Billboard1 | MediaPlate | Billboard/plano do apresentador 1 |
| VPCtrl_Composure | CompositingElement | Pipeline de composição |
| VPCtrl_MediaProfile | MediaProfile | Perfil de entrada de vídeo (SDI/NDI futuro) |
| VPCtrl_Manager | Blueprint Actor | Gerenciador central — Custom Events expostos via RC |
| VPCtrl_Preset | RemoteControlPreset | Preset central do Remote Control |
| VPCtrl_Output | NDI Output | Saída NDI do UE5 |

## 6. Módulos da Aplicação

### Módulos Fixos (estrutura técnica)

| # | Módulo | Função |
|---|--------|--------|
| 1 | Input de Vídeo | Billboard 1: File Media via MediaPlate. SDI/NDI via MediaProfile (futuro) |
| 2 | Chroma Key / Billboard | Key color, crop assimétrico, color grade do Delta Keyer e do plano billboard |
| 3A | Switcher de Câmeras | Troca entre VPCtrl_Cam1/2/3 com blend time e blend function configurável |
| 3B | Camera Paths | 16 slots de path por câmera; animação ease-in/out executada no UE5 |
| 4 | Output de Vídeo | Configuração de saída: AJA, Blackmagic, NDI, Viewport |
| 5 | Cena 3D | Open Level, visibilidade de objetos, materiais, iluminação global |
| 6 | Áudio | Controle de Media Player, volume, mute |
| 7 | Presets | Salvar/carregar/renomear/deletar snapshots completos da cena |
| 8 | Tally | Envio de sinal tally para dispositivos externos via HTTP |
| — | Controles | Propriedades auto-descobertas do Remote Control Preset (geração dinâmica de UI) |

### Meus Painéis (personalizável pelo operador)

O operador cria painéis customizados mesclando controles de qualquer módulo ou grupo de Controles. Cada painel é salvo como JSON no contexto do projeto ativo. Os painéis são destinados ao uso durante a produção — o operador vê apenas o que precisa em um único lugar.

## 6B. Módulo Input — Detalhes de Implementação (UE5.5)

### Remote Control API — Descobertas UE5.5

A API do UE5.5 mudou em relação a versões anteriores. Endpoints corretos confirmados:

| Operação | Endpoint | Método |
|----------|----------|--------|
| Listar presets | `/remote/presets` | GET |
| Ler preset | `/remote/preset/{name}` | GET |
| Chamar função Blueprint | `/remote/object/call` | PUT |
| Ler propriedade de objeto | `/remote/object/property` | PUT (access: READ_ACCESS) |
| Escrever propriedade de objeto | `/remote/object/property` | PUT (access: WRITE_ACCESS) |

**Atenção**: O endpoint `/remote/preset/{name}/function` não existe no UE5.5. Usar `/remote/object/call` com o path do actor.

### Billboard 1 — Media Plate

O Billboard 1 usa um **Media Plate Actor** (`VPCtrl_Billboard1`) que é o método recomendado pela Epic para Virtual Production no UE5.5+.

**Objetos envolvidos:**
- Actor: `MediaPlate_0` (instância na cena)
- Componente de controle: `MediaPlate_0.MediaPlateComponent0`
- Propriedade de recurso: `MediaPlateResource` (tipo `FMediaPlateResource`)

**Estrutura do MediaPlateResource:**
```json
{
  "Type": "External",
  "ExternalMediaPath": "C:/caminho/para/video.mp4",
  "MediaAsset": "",
  "SourcePlaylist": "",
  "ExternalMedia": ""
}
```

**Funções de playback disponíveis via `/remote/object/call`:**
- `Open` — abre e inicia o media (necessário após setar o path)
- `Play` — retoma a reprodução
- `Pause` — pausa
- `Rewind` — volta ao início

**Fluxo para trocar o vídeo:**
1. Setar `MediaPlateResource` com o novo `ExternalMediaPath`
2. Chamar `Open` para iniciar a reprodução

### VPCtrl_Manager — Blueprint Actor

O `VPCtrl_Manager` é o actor Blueprint central que expõe Custom Events via Remote Control Preset.

**Path na cena:** `/Game/VprodProject/Maps/Main.Main:PersistentLevel.VPCtrl_Manager_C_1`

**Custom Events implementados:**
- `ApplyMediaProfile` — aplica o `VPCtrl_MediaProfile` via `MediaProfileBlueprintLibrary.SetMediaProfile`

**Como chamar:**
```python
PUT /remote/object/call
{
  "objectPath": "/Game/.../VPCtrl_Manager_C_1",
  "functionName": "ApplyMediaProfile",
  "generateTransaction": True
}
```

### VPCtrl_MediaProfile — Status atual

O `VPCtrl_MediaProfile` está implementado e funcional para futura integração com SDI (AJA/Blackmagic). Por ora é mantido como fallback e para quando for necessário entrada via placa de captura.

- **Media Source interno:** `FileMediaSource_0` (label `InputMediaB1`, nome fixo para API futura)
- **Exposto no Preset:** propriedade `File Path` com ID `E7F50AA84BD71FADDD51D08D7D7BB6B6`
- **Aplicação:** função `Apply Media Profile` (DisplayName com espaços) exposta no Preset

### Configuração do Remote Control Preset

Propriedades expostas no `VPCtrl_Preset`:

| DisplayName | Owner | Tipo | Uso |
|-------------|-------|------|-----|
| Active Media Profile | VPCtrl_Manager | UMediaProfile | Trocar Media Profile ativo |
| File Path | FileMediaSource_0 | FString | Path do arquivo no Media Profile |
| Media Plate Resource | MediaPlateComponent0 | FMediaPlateResource | Recurso do Billboard 1 |

Funções expostas:

| DisplayName | Owner | Nome interno | Uso |
|-------------|-------|-------------|-----|
| Apply Media Profile | VPCtrl_Manager | ApplyMediaProfile | Aplica o Media Profile |

### Settings do Remote Control (Project Settings)

Para funcionar corretamente, habilitar em **Edit → Project Settings → Remote Control**:
- ✅ Ignore Remote Control Protected Check
- ✅ Ignore Remote Control Getter/Setter Check

## 7. Sistema de Contexto por Projeto

### Problema
Múltiplos projetos UE5 no mesmo PC (mesmo IP:porta) precisam de configurações completamente independentes.

### Solução
Ao conectar, o backend consulta o nome do projeto aberto no UE5:
```
GET /remote/info → { "projectName": "ProjetoTV_2026" }
```
O nome do projeto é usado como chave para todos os dados salvos.

### Estrutura de dados
```
dados/
  ProjetoTV_2026/
    presets/
      preset_A.json
      preset_B.json
    paineis/
      show_ao_vivo.json
      ensaio.json
    config.json
  ProjetoCasamento/
    presets/
      preset_A.json
    paineis/
      cerimonia.json
    config.json
```

### Troca de projeto em tempo real
Se o UE5 abrir um projeto diferente enquanto o app está conectado, o WebSocket detecta e exibe um modal de confirmação para carregar os presets e painéis do novo projeto.

## 8. Preview NDI no Browser

### Pipeline
```
UE5 (NDI Output: VPCtrl_Output)
  → stream NDI na rede local
    → backend Python (ndi-python + opencv)
      → decodifica frames, faz downscale 640×360
        → serve como MJPEG multipart HTTP
          → browser exibe em <img src="/api/preview">
```

### Requisitos para o operador
1. NDI Runtime instalado na máquina do VP CTRL (download gratuito)
2. Plugin NDI IO habilitado no projeto UE5
3. NDI Output configurado no UE5 com nome "VPCtrl_Output"

### Verificação automática na conexão
O app verifica cada requisito ao conectar e exibe status detalhado:
- NDI Runtime presente na máquina
- Plugin NDI detectado no projeto UE5
- Fonte "VPCtrl_Output" descoberta na rede

### Estados possíveis
- Preview ativo com FPS em tempo real
- Plugin NDI ausente no UE5 (com instrução de como habilitar)
- NDI Runtime não instalado (com link para download)

## 9. Controles Auto-Descobertos

### Como funciona
O Remote Control Preset do UE5 pode expor propriedades de qualquer objeto da cena. O VP CTRL consulta o preset ao conectar e gera controles de UI automaticamente baseado no tipo de dado:

| Tipo UE5 | Widget gerado |
|----------|--------------|
| float | Slider com min/max |
| bool | Toggle ON/OFF |
| FLinearColor | Color picker |
| FVector | 3 inputs X Y Z |
| enum | Dropdown |
| Custom Event | Botão |
| int32 | Input numérico |

### Vantagem
O operador adiciona qualquer objeto ao Remote Control Preset no UE5 (LED panel, luz, material, animação) e ele aparece automaticamente no módulo Controles do VP CTRL, sem nenhuma configuração adicional no app.

## 10. WebSocket — Eventos em Tempo Real

O backend mantém uma conexão WebSocket com cada cliente frontend e emite eventos:

| Evento | Dados | Gatilho |
|--------|-------|---------|
| `status` | connected, fps, gpu, vram | polling UE5 a cada 1s |
| `tally` | camera_id, on_air | mudança de câmera ativa |
| `project_changed` | old_name, new_name | UE5 troca de projeto |
| `ndi_status` | ok/no_plugin/no_runtime | verificação de requisitos NDI |
| `preset_loaded` | preset_name | preset carregado |

## 11. Gerenciamento de Estado

O backend mantém um estado em memória que representa o estado atual da cena UE5:

```python
state = {
  "connected": False,
  "project_name": None,
  "active_camera": 1,
  "tally_on": False,
  "active_preset": None,
  "chroma": { "key_color": [0, 0.78, 0], "crop": {...}, "color_grade": {...} },
  "ndi": { "runtime_ok": False, "plugin_ok": False, "source_found": False },
  "fps": 0,
  "gpu": 0
}
```

O UE5 não tem endpoint de "dump completo do estado". Por isso o estado local é a fonte de verdade para o frontend.

## 12. Interface — Decisões de Design

### Layout principal
- **3 colunas**: nav lateral esquerda (168px) + painel central (flex) + monitor direito (230px)
- **Status bar** no topo: logo, IP, projeto ativo, preset, tally
- Tema escuro obrigatório (ambiente de estúdio com luz baixa)
- Tally vermelho pulsante sempre visível independente do módulo ativo

### Responsividade
| Tela | Comportamento |
|------|--------------|
| Segundo monitor 1080p | Layout completo 3 colunas (uso principal) |
| Laptop / tela menor | Coluna monitor recolhe, nav vira ícones |
| Tablet | Nav vira menu hambúrguer, colunas empilham |

### Janela desktop (pywebview)
- Abre automaticamente ao executar o .exe
- Sem barra de endereço ou abas — parece app nativo
- Ideal para segundo monitor em produção
- Mesma URL funciona em browser para acesso remoto (tablet)

## 13. Sistema de Licença

Abordagem: arquivo de licença local assinado (sem dependência de servidor online):

- Chave gerada a partir de hardware ID (hash de MAC address + volume serial)
- Arquivo `.lic` criptografado, verificado ao iniciar
- Fallback offline: licença válida por 30 dias sem conexão de validação
- Status exibido na tela de conexão

## 14. Empacotamento

```
PyInstaller → vpctrl.exe (standalone)
  Inclui:
    - Python runtime
    - FastAPI + uvicorn
    - pywebview
    - ndi-python + opencv (preview NDI)
    - todos os arquivos HTML/CSS/JS
    - pasta dados/ (criada na primeira execução)
```

O operador não precisa instalar Python, pip ou qualquer dependência.

## 15. Requisitos para o Operador

### Máquina do VP CTRL
- Windows 10/11 64-bit
- NDI Runtime (download gratuito em ndi.tv/tools)
- Conexão de rede com a máquina do UE5 (ou mesmo PC)

### Projeto UE5
- UE5 5.x com Remote Control API plugin habilitado
- NDI IO Plugin habilitado
- Projeto configurado com atores VPCtrl_* (Fase 1: manual / Fase 2: plugin automático)

## 16. Ordem de Desenvolvimento

```
Fase 1 — Fundação
  ├── Estrutura de pastas do projeto
  ├── FastAPI skeleton + pywebview + PyInstaller test
  ├── Cliente HTTP async para UE5 Remote Control
  ├── WebSocket backend → frontend
  └── Tela de conexão funcionando (com detecção de projeto)

Fase 2 — Core de produção ao vivo
  ├── Módulo Switcher (mais crítico em produção)
  ├── Módulo Chroma Key / Billboard
  └── Módulo Tally

Fase 3 — Input/Output e Controles
  ├── Módulo Input de Vídeo (MediaProfile)
  ├── Preview NDI (MJPEG bridge)
  └── Módulo Controles (auto-descoberta RC Preset)

Fase 4 — Personalização
  ├── Sistema de Presets por projeto
  ├── Meus Painéis (editor + runtime)
  └── Módulo Cena 3D

Fase 5 — Recursos avançados
  ├── Módulo Camera Paths (Timeline UE5)
  ├── Módulo Áudio
  └── Módulo Output

Fase 6 — Produto comercial
  ├── Sistema de licença
  ├── Log persistente
  ├── Plugin C++ UE5 (Fase 2 do plugin)
  └── PyInstaller / empacotamento final
```
