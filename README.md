# 🧠 English Sentence Correction API

This project is a FastAPI-based backend service that provides English sentence correction and word definition features. It integrates LanguageTool and Gemini LLM for grammar correction and uses PostgreSQL to store correction patterns for analysis.

---

## 🚀 Features

- ✅ **English Grammar Correction** using LanguageTool
- 🤖 **LLM Refinement** via Gemini API (optional)
- 📚 **Word Definitions, Synonyms, Examples, and Phonetics** via Dictionary API
- 🧠 **Error Pattern Tracking** with PostgreSQL
- 🌐 CORS-enabled for frontend integration

---

## 🛠️ Tech Stack

- **FastAPI** – Web framework
- **LanguageTool** – Grammar correction
- **Gemini API** – LLM-based sentence refinement
- **PostgreSQL** – Pattern storage
- **Uvicorn** – ASGI server
- **Docker/Cloud Run** – Deployment-ready

---
## 📈 Architecture Overview

Client
  │
  ├──> /api/define ──> Dictionary API
  │
  └──> /api/correctSentence
         ├──> LanguageTool
         ├──> Gemini API (optional)
         └──> PostgreSQL (store correction pattern)

---

## 📦 Requirements

Install dependencies:

```bash
pip install -r requirements.txt



