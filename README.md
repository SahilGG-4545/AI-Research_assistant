# AI Research Assistant Agent

AI Research Assistant Agent is an AI-powered platform designed to help users **discover, analyze, and synthesize academic research papers**.  
It combines **academic search, Retrieval-Augmented Generation (RAG), and agent-based workflows** to transform research topics into structured insights.

The system allows users to search research papers, analyze documents, ask questions over PDFs, compare papers, and generate implementation-ready code.

---

## Key Features

### Research Discovery
- Search academic papers from **Semantic Scholar** and **arXiv**
- Smart ranking and deduplication of results

### Paper Analysis
- Generate structured research reports and download reports
- Ask questions grounded in paper abstracts
- Extract key insights such as methods, strengths, and limitations

### PDF Question Answering (RAG)
- Upload research papers or documents
- Hybrid retrieval using **BM25 + vector embeddings**
- Context-aware answers grounded in document content

### Agent-Based Research Workflows
- Multi-agent pipeline for research analysis
- Paper comparison using structured extraction
- Topic-level analysis of top research papers

### Code Generation
- Generate code implementations from research concepts
- Developer → Reviewer workflow for improved code quality

---

## Architecture

In simple terms, the app works like this: you ask for something in the web page, the backend decides which workflow to run, gathers the right information, asks the AI model to write the result, and sends it back to you.

### Complete Flow 

```text
┌───────────────────────────────────────────────────────────────┐
│                    Browser (Vanilla JS)                       │
│   Search Papers · Upload PDF · Compare · Generate Code        │          
└───────────────────────────────┬───────────────────────────────┘
                                │
                        REST API (JSON)
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                        Flask Backend                          │
│     Routing · Input Validation · Session Management           │
└───────────────┬───────────────────────┬───────────────────────┘
                │                       │
                ▼                       ▼
      ┌───────────────────┐    ┌─────────────────────┐
      │  Paper Search     │    │      PDF Q&A        │
      │  Semantic Scholar │    │  Load + Split PDF   │
      │  arXiv APIs       │    │  Chunk Selection    │
      │  Rank + Merge     │    │  Context Builder    │
      └──────────┬────────┘    └──────────┬──────────┘
                 │                        │
                 └──────────────┬─────────┘
                                │
                                ▼
                 ┌───────────────────────────┐
                 │     Compare / Code Gen    │
                 │  Paper Comparison         │
                 │  Research Code Generator  │
                 └──────────────┬────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                   Groq Inference Engine                       │
│                     LLaMA 3.3 70B                             │
│             Context Processing + Response Gen                 │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                        Agent Layer                            │
│  search_agent · qa_agent · compare_agent · code_agent         │
│  developer → reviewer workflow for generated code             │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                        Final Output                           │
│     UI Results · Download Reports · Code · Trace Logs         │
└───────────────────────────────────────────────────────────────┘

```
---


### 🧱 Tech Stack

| Layer | Technology |
|------|------------|
| **Language** | `Python` |
| **Backend API** | `Flask` |
| **LLM Inference** | `Groq` |
| **Agent Framework** | `AutoGen` |
| **Vector Database** | `ChromaDB` |
| **Embeddings** | `Sentence Transformers` |
| **Retrieval Strategy** | `BM25` + `Hybrid RAG` |
| **Document Processing** | `PyPDF2` |
| **Frontend** | `HTML` · `CSS` · `JavaScript` |

---

# Installation

## Clone the repository

```bash
git clone https://github.com/<your-username>/AI-Research_assistant-main.git
cd AI-Research_assistant-main
```

## Create Virtual Environment

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows
.\.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Configure Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_api_key_here
```

---

# Running the Application

Start the server:

```bash
python flask_app.py
```

Open the application in your browser:

```
http://localhost:5000
```


---

# License

This project is licensed under the **MIT License**.

