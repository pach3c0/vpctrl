# VP CTRL — Sistema de Licenciamento

## Visão Geral

O VP CTRL utiliza um sistema de licenciamento próprio, hospedado em `https://license.cliquezoom.com.br`. O sistema é baseado em **node-lock** — cada licença fica vinculada a uma única máquina por vez.

---

## Para o Cliente Final

### Como ativar

1. Ao abrir o VP CTRL pela primeira vez, aparece a tela de ativação
2. Insira a chave no formato `XXXX-XXXX-XXXX-XXXX`
3. Clique em **Activate**
4. O app conecta ao servidor, valida a chave e registra sua máquina
5. Pronto — o app abre normalmente

### Regras importantes

- **1 licença = 1 máquina**. A mesma chave não pode ser usada em dois computadores ao mesmo tempo
- A licença fica vinculada à sua máquina pelo hardware (identificador único gerado automaticamente)
- Você **não precisa** de internet para usar o app no dia a dia — ele funciona offline por até **7 dias** após a última validação online
- A cada 7 dias, o app tenta renovar automaticamente a validação em background. Se não conseguir (sem internet), entra em **período de graça** por mais 3 dias
- Se ficar mais de 10 dias sem internet, o app solicita conexão para renovar

### Transferência de máquina

Se precisar instalar em um novo computador (troca de hardware, reinstalação):

1. Entre em contato com o suporte ou acesse o portal de licenças
2. Solicite a desativação da máquina antiga
3. Instale o VP CTRL no novo computador e ative normalmente com a mesma chave

> **Atenção:** a desativação da máquina antiga é necessária antes de ativar em uma nova. Isso é feito pelo suporte.

### O que acontece se a licença for suspensa

- O app bloqueia na próxima inicialização
- Uma mensagem informa que a licença foi suspensa
- Entre em contato com o suporte para regularizar

---

## Para o Vendedor / Revendedor

### Como gerar uma licença para um cliente

1. Acesse `https://license.cliquezoom.com.br`
2. Faça login com suas credenciais de administrador
3. Clique em **New License**
4. Preencha:
   - **Customer Name**: nome do cliente ou empresa
   - **Customer Email**: e-mail do cliente
   - **Expires At**: data de vencimento (deixe vazio para licença vitalícia)
5. Clique em **Create**
6. A chave gerada aparece na tela — copie e envie ao cliente

### Gerenciamento de licenças

No portal você pode:

| Ação | Como fazer |
|---|---|
| Ver todas as licenças | Menu **Licenses** |
| Ver qual máquina está ativa | Clique na licença → aba de ativações |
| Suspender uma licença | Editar licença → status **Suspended** |
| Reativar uma licença | Editar licença → status **Active** |
| Transferir para nova máquina | Clique na ativação → botão **Deactivate** |
| Alterar data de vencimento | Editar licença → campo **Expires At** |

### Estados de uma licença

| Status | Significado |
|---|---|
| **Active** | Licença válida, cliente pode usar |
| **Suspended** | Bloqueada pelo admin (ex: inadimplência) |
| **Expired** | Data de vencimento passou |

---

## Para o Desenvolvedor

### Arquitetura

```
VP CTRL (desktop)
    │
    ├── core/license_client.py     ← cliente Python (PyQt6)
    │       Fingerprint, validação, ativação, heartbeat, token offline
    │
    └── HTTPS ──► license.cliquezoom.com.br (VPS)
                        │
                        ├── FastAPI (porta 8010)
                        ├── PostgreSQL (banco: keygen_production)
                        ├── Nginx (proxy reverso + SSL)
                        └── Systemd (auto-start)
```

### Endpoints da API

#### Públicos (chamados pelo app)

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/v1/licenses/activate` | Primeira ativação da máquina |
| POST | `/api/v1/licenses/validate` | Validação + renovação do token |
| POST | `/api/v1/licenses/heartbeat` | Ping periódico (1x/hora) |
| POST | `/api/v1/licenses/deactivate` | Desativação ao fechar o app |
| GET | `/api/v1/public-key` | Chave pública RSA para validação offline |

#### Admin (portal)

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/admin/login` | Login admin → JWT |
| GET | `/api/admin/licenses` | Listar licenças |
| POST | `/api/admin/licenses` | Criar licença |
| GET | `/api/admin/licenses/{id}` | Detalhe + ativações |
| PUT | `/api/admin/licenses/{id}` | Atualizar status/validade |
| DELETE | `/api/admin/licenses/{id}/activations/{id}` | Desativar máquina |

### Fingerprint da máquina

O identificador único da máquina é gerado assim:

```
SHA256( UUID_hardware | hostname | username )
```

No Windows usa `wmic csproduct get uuid`. É estável entre reinicializações. Muda se trocar a placa-mãe.

### Token JWT (validação offline)

- Assinado com **RSA-2048 / RS256**
- Válido por **7 dias**
- Contém: `license_key`, `fingerprint`, `customer_name`, `expires_at`
- A chave pública RSA está **hardcoded** no `license_client.py`
- Permite validação offline sem contato com o servidor

### Fluxo de inicialização do app

```
App inicia
    │
    ├── Tem chave salva no QSettings?
    │       ├── SIM → valida online
    │       │           ├── OK (200) → salva novo token → abre app
    │       │           ├── 403/404 → bloqueia → mostra erro
    │       │           └── Offline → usa token local
    │       │                   ├── Token válido → abre (modo online normal)
    │       │                   ├── Token em grace period → abre com aviso
    │       │                   └── Token inválido → bloqueia
    │       └── NÃO → mostra dialog de ativação
    │                   ├── Ativa com sucesso → abre app
    │                   └── Falha → encerra
    │
    └── App aberto → heartbeat a cada 60 min em background
```

### Localização dos arquivos no servidor

```
/var/www/vp-license/
├── main.py              ← FastAPI entry point (porta 8010)
├── models.py            ← SQLAlchemy: licenses, activations, admin_users
├── database.py          ← Conexão PostgreSQL
├── auth.py              ← JWT admin (HS256) + JWT licença (RS256)
├── routes/
│   ├── public.py        ← Endpoints do app
│   └── admin.py         ← Endpoints do portal
├── portal/
│   └── index.html       ← Portal SPA (vanilla JS)
├── keys/
│   ├── private.pem      ← Chave privada RSA (NUNCA expor)
│   └── public.pem       ← Chave pública RSA (embed no app)
└── .env                 ← Variáveis de ambiente (NUNCA versionar)
```

### Serviço no VPS

```bash
# Ver status
systemctl status vp-license

# Reiniciar
systemctl restart vp-license

# Ver logs
journalctl -u vp-license -f
```

### Banco de dados

```
PostgreSQL 16
Host: localhost:5432
Banco: keygen_production
Usuário: keygen
```

Tabelas: `licenses`, `activations`, `admin_users`

### Variáveis de ambiente (.env)

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | Connection string PostgreSQL |
| `ADMIN_JWT_SECRET` | Secret para tokens de sessão admin |
| `RSA_PRIVATE_KEY_PATH` | Caminho da chave privada RSA |
| `RSA_PUBLIC_KEY_PATH` | Caminho da chave pública RSA |
| `LICENSE_JWT_EXPIRE_DAYS` | Validade do token (padrão: 7) |
| `ADMIN_JWT_EXPIRE_HOURS` | Sessão admin (padrão: 12h) |

### Segurança

- Chave privada RSA: **nunca sai do servidor**
- Chave pública RSA: embutida no app (pode ser pública)
- Tokens admin: HS256, expiram em 12h
- Tokens de licença: RS256, expiram em 7 dias
- Rate limiting: 30 req/min por IP nos endpoints públicos
- SSL: Let's Encrypt (renovação automática via Certbot)

### Atualizar a chave pública no app

Se precisar gerar novas chaves RSA (ex: comprometimento):

```bash
# No VPS
openssl genrsa -out /var/www/vp-license/keys/private.pem 2048
openssl rsa -in /var/www/vp-license/keys/private.pem -pubout -out /var/www/vp-license/keys/public.pem
cat /var/www/vp-license/keys/public.pem
```

Copiar o conteúdo para `RSA_PUBLIC_KEY_PEM` em `versions/v3/core/license_client.py` e redistribuir o app.

> **Atenção:** trocar as chaves invalida todos os tokens existentes. Os clientes precisarão validar online na próxima inicialização.
