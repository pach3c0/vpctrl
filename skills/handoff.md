# Handoff de Contexto — VP CTRL

Este arquivo foi criado para transferir o contexto e progresso atual do projeto **VP CTRL** para o próximo agente ou sessão.

---

## 1. O que foi feito nesta sessão
1. **Clonagem do Repositório**:
   O repositório `https://github.com/pach3c0/vpctrl.git` foi clonado com sucesso no diretório local `/Users/macbook/Documents/vpcontrol`.

2. **Configuração do Ambiente Virtual**:
   - Criado ambiente virtual Python 3: `python3 -m venv venv`
   - Atualizado o gerenciador de pacotes: `pip install --upgrade pip`
   - Instaladas todas as dependências necessárias para a versão `v3` (GUI PyQt6):
     ```bash
     pip install PyQt6 requests python-osc psutil websockets pyjwt cryptography
     ```
   - *Nota: As bibliotecas `pyjwt` e `cryptography` foram adicionadas para possibilitar a validação e o decodificamento do token de licença (padrão RS256).*

3. **Mapeamento de URLs e Infraestrutura**:
   - **Licensing Server (SaaS)**: Hosted em `https://license.cliquezoom.com.br` (FastAPI + PostgreSQL + Nginx na VPS).
   - **Documentação e Updates**: `https://vpctrl.com.br/docs` e `https://vpctrl.com.br/updates`.

4. **Recuperação de Acesso à VPS (Senha de Admin)**:
   - Identificado o método de reset de senha para o portal de licenças. Para redefinir a senha do admin na VPS, o usuário deve fazer login via SSH e rodar o script no terminal da VPS:
     ```bash
     cd /var/www/vp-license && sudo -u www-data ./venv/bin/python3 -c "
     import database, models, auth
     db = next(database.get_db())
     admin = db.query(models.AdminUser).first()
     if admin:
         admin.password_hash = auth.hash_password('SUA_NOVA_SENHA')
         db.commit()
         print('Usuario:', admin.username)
         print('Senha atualizada com sucesso!')
     "
     ```

---

## 2. Status Atual do Projeto
* **Código Fonte**: A versão atual de produção (`v3`) está limpa e configurada na pasta `versions/v3/`.
* **Execução**: O ambiente virtual local está pronto com todas as dependências instaladas. 
* **Banco Local**: QSettings está limpo. O app exibirá a tela de ativação de licença na primeira execução.

---

## 3. Próximos Passos recomendados para o Agente
1. **Apoiar na Conexão**: Auxiliar o usuário no primeiro login do portal administrativo do SaaS (`https://license.cliquezoom.com.br`) após o reset de senha na VPS.
2. **Gerar e Registrar Licença**:
   - Ajudar a gerar uma nova chave no portal admin (formato `XXXX-XXXX-XXXX-XXXX`).
   - Ativar o aplicativo executando `python3 main.py` dentro de `versions/v3`.
3. **Desenvolvimento / Resolução de Pendências da v3**:
   - **NDI**: Investigar por que a chamada Open NDI não está trocando a mídia.
   - **Lens override sliders**: Revisar o funcionamento dos sliders de lentes na sidebar.
