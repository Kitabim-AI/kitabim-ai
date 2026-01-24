
# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform.

## Structure

- `/frontend`: Next.js/React frontend application.
- `/backend`: FastAPI Python backend for document storage and management.
- `/services`: Shared logic for OCR extraction and RAG analysis.

## Core Features

- **SHA-256 Deduplication**: Files are fingerprinted to avoid redundant OCR costs.
- **RAG-Powered Chat**: High-precision context retrieval for Uyghur documents.
- **Global Knowledge Base**: A shared, persistent library of processed Uyghur literature.

## Local Development

### Prerequisites

- **Node.js**: v18+
- **Python**: 3.9+
- **MongoDB**: Running locally on `mongodb://localhost:27017`

### Setup

1. **Environment Variables**:
   Create a `.env.local` file in the root directory:
   ```env
   GEMINI_API_KEY=your_google_gemini_api_key
   ```

2. **Backend Setup**:
   ```bash
   # Install dependencies
   python3 -m pip install -r backend/requirements.txt

   # Start the FastAPI server
   python3 backend/main.py
   ```
   The backend will run on `http://localhost:8000`.

3. **Frontend Setup**:
   ```bash
   # Install dependencies
   npm install

   # Start the React development server
   npm run dev
   ```
   The frontend will run on `http://localhost:3000`.

## Technology Stack

- **Frontend**: React, Tailwind CSS, pdf.js, Lucide Icons.
- **Backend**: Python FastAPI, MongoDB (NoSQL).
- **AI**: Google Gemini (Flash Lite for OCR, Gemini 1.5 Flash for Reasoning).

