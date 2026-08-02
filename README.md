# ⏰ Desligamento Inteligente Pro

Aplicativo desktop para Linux que permite programar o desligamento automático do sistema através de uma interface gráfica simples, moderna e intuitiva.

Desenvolvido em **Python + Tkinter**, com suporte a persistência de agendamentos e distribuição através de pacote **.deb** para sistemas baseados em Debian/Ubuntu.

---

# 🖥️ Interface

<p align="center">
<img src="screenshots/1.png" width="700">
</p>

---

# 🚀 Recursos

✅ Interface gráfica moderna
✅ Agendamento rápido:

* 30 minutos
* 1 hora
* 2 horas
* 4 horas

✅ Agendamento por horário específico
✅ Contador regressivo em tempo real
✅ Cancelamento de desligamento
✅ Persistência do último agendamento
✅ Integração com sistema Linux
✅ Pacote `.deb` para instalação fácil

---

# 📸 Demonstração

## Tela principal

<p align="center">
<img src="screenshots/1.png" width="600">
</p>

## Sistema programado

<p align="center">
<img src="screenshots/2.png" width="600">
</p>

## Contador regressivo

<p align="center">
<img src="screenshots/3.png" width="600">
</p>

---

# 📥 Instalação

## Opção 1 - Instalação pelo pacote `.deb` (recomendado)

Baixe a versão mais recente na página de Releases:

https://github.com/Jackson-077/Desligamento-Inteligente/releases

Instale o pacote:

```bash
sudo apt install ./desligamento-inteligente_1.0_all.deb
```

O instalador irá configurar automaticamente as dependências necessárias.

Após instalar, execute:

```bash
desligamento-inteligente
```

---

# 🧑‍💻 Opção 2 - Executar pelo código fonte

## Clonar o projeto

```bash
git clone https://github.com/Jackson-077/Desligamento-Inteligente.git
```

Entre na pasta:

```bash
cd Desligamento-Inteligente
```

Instale as dependências:

```bash
sudo apt update
sudo apt install python3 python3-tk systemd
```

Dê permissão de execução:

```bash
chmod +x desligamento.py
```

Execute o aplicativo:

```bash
./desligamento.py
```

ou:

```bash
python3 desligamento.py
```

---

# 🛠️ Dependências

* Python 3.10+
* Tkinter
* Systemd

Ubuntu/Debian:

```bash
sudo apt install python3 python3-tk systemd
```

---

# 📁 Estrutura do projeto

```text
Desligamento-Inteligente/
│
├── desligamento.py
├── gerar_deb.sh
├── icon.png
├── README.md
├── LICENSE
└── screenshots/
    ├── 1.png
    ├── 2.png
    └── 3.png
```

---

# 🔧 Desenvolvimento

Para gerar um novo pacote `.deb`:

Dê permissão ao gerador:

```bash
chmod +x gerar_deb.sh
```

Execute:

```bash
./gerar_deb.sh
```

O instalador será criado:

```text
desligamento-inteligente_1.0_all.deb
```

Instale com:

```bash
sudo apt install ./desligamento-inteligente_1.0_all.deb
```

---

# 📝 Licença

Projeto desenvolvido por **Jackson Quequi**.

Uso livre para estudos, melhorias e distribuição conforme os termos definidos na licença do projeto.

---

# ⭐ Contribuição

Sugestões, melhorias e correções são bem-vindas.

Se este projeto foi útil, deixe uma estrela ⭐ no GitHub.

