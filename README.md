<div align="center">

# 🧠 AI Research Assistant

**A production-grade, full-stack AI platform for academic research — powered by Groq, LLaMA 3.3 70B, and multi-agent orchestration.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-black?style=flat-square&logo=flask)](https://flask.palletsprojects.com/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA%203.3%2070B-orange?style=flat-square)](https://groq.com/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)]()

<br/>

> *Search millions of papers · Analyse PDFs with RAG · Generate reports · Write code · Hold intelligent research conversations — all in one beautiful interface.*

<br/>

<img width="1179" height="754" alt="AI Research Assistant - Brave 08_Mar_2026 06_37_20 PM" src="https://github.com/user-attachments/assets/04bffccc-2365-43e3-bb60-b11fb0fbd8b8" />
<img width="1232" height="947" alt="AI Research Assistant - Brave 08_Mar_2026 06_39_33 PM" src="https://github.com/user-attachments/assets/8986e4e6-7e39-474a-932f-f0cb5822d38b" />



</div>

---

## ✨ Why This Project Stands Out

Most AI demos are single-feature wrappers around an LLM API. This is different. It is a **full-stack research intelligence platform** that combines:

- **Multi-source live data retrieval** (Semantic Scholar + arXiv APIs in parallel)
- **Retrieval-Augmented Generation (RAG)** on uploaded PDFs — not just prompting
- **Multi-agent orchestration** via AutoGen for coordinated task execution
- **Sub-second inference** via Groq's LPU hardware for a genuinely snappy UX
- A **professional, animated web UI** built from scratch — no Streamlit, no templates

---

## 🚀 Features

| Feature | Description |
|---|---|
| 🔍 **Multi-Source Paper Search** | Searches Semantic Scholar & arXiv simultaneously using concurrent threads. Deduplicates, ranks by citations, and streams results. |
| 📄 **PDF RAG Q&A** | Upload any PDF. The system chunks, indexes, and performs scored keyword retrieval to answer questions from the exact source text. |
| 📊 **AI Paper Reports** | Generates structured academic reports (Executive Summary, Methodology, Strengths, Limitations, Future Work) from any paper. |
| 💬 **Research Chatbot** | Persistent multi-turn conversation powered by LLaMA 3.3 70B. Full history context window management. |
| 💻 **Code Generator** | Generates production-ready code in Python, JavaScript, TypeScript, Java, or C++ with syntax highlighting and one-click download. |
| ⚖️ **Paper Comparison** | Side-by-side AI analysis of two papers across methodology, results, contributions, or overall quality. |
| 📥 **Export Everything** | Download paper reports, PDF summaries, and generated code — all as files. |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Vanilla JS)                  │
│  Tab UI · Animations · Markdown Rendering · Toasts      │
└───────────────────┬─────────────────────────────────────┘
                    │ REST API (JSON / multipart)
┌───────────────────▼─────────────────────────────────────┐
│                   Flask Backend                          │
│  9 API routes · Session management · Input validation   │
└──────┬──────────────────────────┬────────────────────────┘
       │                          │
┌──────▼──────┐          ┌────────▼────────┐
│ Search APIs │          │  Groq Inference  │
│ Semantic    │          │  LLaMA 3.3 70B  │
│ Scholar     │          │  (< 1s latency) │
│ arXiv       │          └────────┬────────┘
└─────────────┘                   │
                         ┌────────▼────────┐
                         │ AutoGen Agents  │
                         │ search_agent    │
                         │ qa_agent        │
                         │ code_agent      │
                         └─────────────────┘
```

**Key design decisions:**
- Paper searches run in **parallel threads** (`concurrent.futures`) — both sources return simultaneously
- RAG uses **scored keyword chunking** with configurable overlap — no vector DB dependency required
- LRU caching on search endpoints prevents redundant API calls
- Sessions isolate PDF state per user — production-safe multi-user design

---

## 🛠️ Tech Stack

**Backend**
- `Flask 3` — REST API server with session management
- `Groq SDK` — LLaMA 3.3 70B inference (fastest available LLM API)
- `AutoGen` — Multi-agent coordination framework
- `PyPDF2` — PDF text extraction and chunking
- `Requests` — Async-style parallel calls to Semantic Scholar & arXiv

**Frontend**
- Vanilla `HTML5 / CSS3 / JavaScript` — zero framework overhead
- `marked.js` — Real-time Markdown rendering for AI responses
- `highlight.js` — Syntax-highlighted code output (Tokyo Night theme)
- CSS animations: `IntersectionObserver` scroll reveals, glassmorphism cards, animated background orbs, typing indicators
- Google Fonts `Inter` + `JetBrains Mono`

---

## ⚙️ Getting Started

### Prerequisites
- Python 3.10+
- A free [Groq API key](https://console.groq.com/)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/ai-research-assistant.git
cd ai-research-assistant

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Add your GROQ_API_KEY to .env
```

### Environment Variables

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_api_key_here
FLASK_SECRET=your_random_secret_key   # optional, auto-generated if omitted
```

### Run

```bash
python flask_app.py
```

Open **http://localhost:5000** in your browser.

---

## 📁 Project Structure

```
ai-research-assistant/
├── flask_app.py            # Flask app — all API routes & session logic
├── research_assistant.py   # Core AI engine — search, RAG, agents, LLM
├── templates/
│   └── index.html          # Single-page application shell
├── static/
│   ├── css/
│   │   └── style.css       # Full UI stylesheet with animations
│   └── js/
│       └── app.js          # Frontend state machine & API client
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/search` | Search Semantic Scholar + arXiv |
| `POST` | `/api/paper-report` | Generate structured paper report |
| `POST` | `/api/paper-question` | Answer question from paper abstract |
| `POST` | `/api/pdf-upload` | Upload & chunk a PDF |
| `POST` | `/api/pdf-question` | RAG Q&A over uploaded PDF |
| `POST` | `/api/pdf-summary` | Generate structured PDF summary |
| `POST` | `/api/chatbot` | Multi-turn research conversation |
| `POST` | `/api/generate-code` | Generate code in 5 languages |
| `POST` | `/api/compare-papers` | AI comparison of two papers |

---

## 🧩 How RAG Works (Under the Hood)

```
PDF Upload
    │
    ▼
Extract full text (PyPDF2)
    │
    ▼
Chunk text (1000 chars, 200 overlap)
    │
    ▼
Store chunks in server session
    │
    ▼  On question:
Keyword scoring over all chunks
    │
    ▼
Top-K relevant chunks selected
    │
    ▼
Context + Question → Groq LLM
    │
    ▼
Grounded answer (no hallucination from irrelevant context)
```

This approach achieves **grounded, document-faithful answers** without requiring a vector database, embedding model, or external services — making it deployable anywhere.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

**Built with 🔬 curiosity and ☕ coffee**

*If this project helped you, please consider giving it a ⭐*

</div>


