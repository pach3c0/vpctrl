# VP CTRL — Como Iniciar

**Virtual Production Control** · v1.0

---

## 1. Instalar dependências

```bash
pip install -r requirements.txt
```

> Requer Python 3.11 ou superior.

---

## 2. Executar o aplicativo

```bash
python app/main.py
```

Uma janela nativa abrirá automaticamente via pywebview apontando para `http://localhost:8000`.

---

## 3. Acesso alternativo pelo browser

Se preferir usar o browser diretamente (ou acessar de outro dispositivo na mesma rede):

```
http://localhost:8000
```

Para acesso de tablet ou outro PC na rede local, substitua `localhost` pelo IP da máquina onde o VP CTRL está rodando.

---

## 4. Requisitos do UE5

Para conectar ao Unreal Engine 5:

- Plugin **Remote Control API** habilitado no projeto (`Edit → Plugins → Remote Control API`)
- Projeto aberto e rodando no UE5 antes de clicar em Conectar
- Porta padrão: **30010** (configurável na tela de conexão)
- Atores com a convenção `VPCtrl_*` criados na cena (ver `VPCtrl_Arquitetura.md`, seção 5)

---

## 5. Modo Mock (sem UE5)

O UE5 **não é obrigatório** para testar a interface. Quando o UE5 não está disponível, o app opera em **modo mock**:

- A tela de conexão mostrará "UE5 não encontrado" mas permitirá continuar
- Todos os controles de UI funcionam normalmente
- As chamadas à API do UE5 são ignoradas silenciosamente (sem erros)
- Útil para desenvolver e testar o frontend sem o UE5 aberto

---

## Estrutura de arquivos

```
ControlUE/
  app/
    main.py              ← servidor FastAPI + janela pywebview
    static/
      index.html         ← interface completa (HTML/CSS/JS)
  requirements.txt       ← dependências Python
  README_INICIO.md       ← este arquivo
  VPCtrl_Arquitetura.md  ← documentação técnica completa
```
