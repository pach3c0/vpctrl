# BP_VPB1 — Configuração OSC para VP CTRL v3

## Visão Geral

| Direção  | Porta | Quem envia |
|----------|-------|------------|
| app → BP | 8001  | App Python |
| BP → app | 9001  | BP_VPB1    |

---

## O que já existe no BP (confirmado pelo export)

| Item | Status |
|------|--------|
| Struct `S_CameraPath` com PointA, PointB, Duration, FocalLengthA, FocalLengthB, FocusDistanceA, FocusDistanceB | ✅ |
| Array `Paths` de `S_CameraPath` | ✅ |
| `OSCServer` criado, `Listen`, delegate `OnOscMessageReceived` | ✅ |
| Switch on String com `/path1`…`/path8` | ✅ |
| Timeline `TL_Path1` → `TLerp(PointA, PointB, Alpha)` → `K2_SetActorTransform` | ✅ |
| `SetPlayRate` = `1 / Duration` | ✅ |
| Variável `Cam1` (CineCameraComponent) | ✅ |
| Variável `IsMoving` | ✅ |

**Nomes reais dos campos na struct (usar exatamente assim nos nós Break/Make):**

| Campo amigável  | Nome interno no BP |
|-----------------|--------------------|
| PointA          | `PointA_2_E2A3B2574AA445774A644AA9C4543471` |
| PointB          | `PointB_4_79EA0A0F4348175D184B1AB5950F8A90` |
| Duration        | `Duration_7_0006AB414D0294F0BD24D3B577B45E90` |
| FocalLengthA    | `FocalLengthA_13_92BE25BC412AA650716E4B95FCA95D0A` |
| FocusDistanceA  | `FocusDistanceA_17_A57059FD4EA546AD73B2B5911BBB20FE` |
| FocalLengthB    | `FocalLengthB_16_BAB936384E6C4445DE5C7D93020A20B8` |
| FocusDistanceB  | `FocusDistanceB_19_10482C2042CB3301AF7A8CAB95BB36DC` |

> No BP esses nomes aparecem como labels curtos (PointA, Duration etc.) — o BP resolve automaticamente.

---

## 1. Variáveis a adicionar

| Nome           | Tipo    | Valor padrão |
|----------------|---------|--------------|
| `ActivePath`   | Integer | 0            |
| `HeartbeatAcc` | Float   | 0.0          |

---

## 2. Event BeginPlay — adicionar ao final

Após o `Listen` que já existe, adicionar a chamada para a Macro **SendSync** (seção 4).

---

## 3. Event Tick — Heartbeat (a cada 2s)

```
Event Tick
  └─► HeartbeatAcc = HeartbeatAcc + DeltaSeconds
        └─► Branch: HeartbeatAcc >= 2.0
              True ──► Set HeartbeatAcc = 0.0
                   └─► Create OSC Message "/heartbeat"
                         └─► Send OSC Message
                               ├─ IP Address: "127.0.0.1"
                               └─ Port: 9001
```

---

## 4. Macro: SendSync

Envia todos os dados de todos os paths para o app (porta 9001).
Chamar no **BeginPlay** e após **/record/a** e **/record/b**.

```
For Each Loop (índice 0 a 7):
  ├─ Create OSC Message "/sync/duration"
  │    → Add Int32 Argument (ArrayIndex)
  │    → Add Float Argument (Paths[ArrayIndex].Duration)
  │    → Send OSC Message  IP:"127.0.0.1"  Port:9001
  │
  ├─ Create OSC Message "/sync/focal_a"
  │    → Add Int32 Argument (ArrayIndex)
  │    → Add Float Argument (Paths[ArrayIndex].FocalLengthA)
  │    → Send OSC Message  IP:"127.0.0.1"  Port:9001
  │
  ├─ /sync/focal_b  → FocalLengthB
  ├─ /sync/focus_a  → FocusDistanceA
  └─ /sync/focus_b  → FocusDistanceB

Completed (após loop):
  └─► Create OSC Message "/sync/done"
        └─► Send OSC Message  IP:"127.0.0.1"  Port:9001
```

> **Nota:** Use `For Each Loop` no array Paths para pegar o ArrayIndex automaticamente.
> Para leitura use `Array Get (Paths, ArrayIndex)` → `Break S_CameraPath`.

---

## 5. Novos cases no SwitchString existente

O `Message` pin vem do `OnOscMessageReceived_Event` — reutilize em todos os handlers.

---

### /active_path
```
└─► Get OSC Message Int32 Argument (Message, Index 0)
      └─► Set ActivePath
```

---

### /goto/a
```
└─► Array Get (Paths, ActivePath)
      └─► Break S_CameraPath → PointA (Transform)
            └─► K2_SetActorTransform (Self, NewTransform=PointA)
```

---

### /goto/b
```
└─► Array Get (Paths, ActivePath)
      └─► Break S_CameraPath → PointB (Transform)
            └─► K2_SetActorTransform (Self, NewTransform=PointB)
```

---

### /record/a
```
└─► Get Actor Transform (Self) → salva como LocalTransform
└─► Array Get (Paths, ActivePath) → Break S_CameraPath → guarda todos os campos
└─► Make S_CameraPath
      ├─ PointA = LocalTransform   ← campo que muda
      ├─ PointB = (valor anterior)
      ├─ Duration = (valor anterior)
      ├─ FocalLengthA = (valor anterior)
      └─ ... (demais campos iguais)
└─► Array Set (Paths, ActivePath, novo struct)
└─► SendSync (Macro)
```

---

### /record/b
```
(mesmo padrão — PointB = LocalTransform)
```

---

### /focal/a
```
└─► Get OSC Message Float Argument (Message, Index 0) → valor
└─► Array Get (Paths, ActivePath) → Break S_CameraPath
└─► Make S_CameraPath (FocalLengthA = valor, demais = anterior)
└─► Array Set (Paths, ActivePath, novo struct)
└─► Set FocalLength no Cam1 (para preview imediato)
```

---

### /focal/b
```
(mesmo — campo FocalLengthB)
```

---

### /focus/a
```
└─► Get OSC Message Float Argument (Message, Index 0) → valor
└─► Array Get (Paths, ActivePath) → Break → Make (FocusDistanceA = valor)
└─► Array Set
└─► Set FocusSettings.ManualFocusDistance no Cam1 (para preview imediato)
```

---

### /focus/b
```
(mesmo — campo FocusDistanceB)
```

---

### /duration
```
└─► Get OSC Message Float Argument (Message, Index 0) → valor
└─► Array Get (Paths, ActivePath) → Break → Make (Duration = valor)
└─► Array Set
```

---

### /freecam
```
└─► Get OSC Message Int32 Argument (Message, Index 0)
      └─► Branch: valor == 1
            True  → Set Actor Hidden In Game (BP_FreeCamera) = false
            False → Set Actor Hidden In Game (BP_FreeCamera) = true
```

---

## 6. Event EndPlay

```
Event EndPlay
  └─► OSCServer → Stop
```

---

## 7. Checklist de teste

- [ ] Play no UE5 → app recebe `/heartbeat` → status "PIE ativo"
- [ ] Para PIE → 5s sem heartbeat → banner laranja no app
- [ ] BeginPlay → app recebe `/sync/*` → sidebar mostra valores corretos
- [ ] Clicar Path 1 no app → `/path1` → Timeline dispara → câmera anima
- [ ] Clicar A no app → `/goto/a` → câmera vai para PointA instantâneo
- [ ] Clicar B no app → `/goto/b` → câmera vai para PointB instantâneo
- [ ] Clicar REC (ponto A ativo) → `/record/a` → BP grava transform → envia sync → sidebar atualiza
- [ ] Slider Focal → `/focal/a` → BP salva + Cam1 atualiza focal em tempo real
- [ ] Slider Focus → `/focus/a` → BP salva + Cam1 atualiza foco em tempo real
- [ ] Duration spin → `/duration` → BP salva (afeta SetPlayRate na próxima animação)
