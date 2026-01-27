
# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform.

## Structure

- `/backend`: FastAPI Python implementation for document processing and RAG.
  - `app/api`: API endpoints for books, chat, and status management.
  - `app/services`: PDF processing, Gemini OCR integration, and RAG logic.
  - `app/db`: MongoDB connection and repository management.
  - `app/models`: Pydantic schemes and data models.
- `/uyghurocr-api`: Local OCR service using Tesseract and ONNX models.
  - `logic`: OCR and PDF processing logic.
  - `tessdata`: Tesseract language data.
- `/frontend/src`: React frontend source code (served by Vite).
  - `components`: Functional UI components:
    - `Library`: Grid and list views for browsing books.
    - `Reader`: Immersive RTL reading experience with inline editing.
    - `Chat`: Local and Global RAG interfaces.
    - `Admin`: Batch management, reprocessing, and metadata editing.
  - `services`: Frontend API clients (Backend and Direct-to-Gemini OCR).
  - `hooks`: Custom React hooks for global state and data fetching.
- `/data`: Persistent storage for application data (ignored by git).
  - `uploads/`: Original PDF files.
  - `covers/`: Extracted book cover images.
- `/index.tsx`: Main React entry point mounting the App.
- `/vite.config.ts`: Vite configuration with API proxying to the backend.

## Core Features

- **SHA-256 Deduplication**: Files are fingerprinted to avoid redundant OCR costs.
- **RAG-Powered Chat**: High-precision context retrieval for Uyghur documents using Gemini.
- **Global Knowledge Base**: A shared, persistent library of processed Uyghur literature.
- **Real-time Processing**: Background tasks for OCR and embedding extraction.

## Local Development

### Prerequisites

- **Node.js**: v18+
- **Python**: 3.9+
- **MongoDB**: Running locally on `mongodb://localhost:27017`

### Setup

1. **Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_google_gemini_api_key
   GEMINI_MODEL_NAME=gemini-3-flash-preview
   GEMINI_CATEGORIZATION_MODEL=gemini-1.5-flash
   MONGODB_URL=mongodb://localhost:27017
   MAX_PARALLEL_PAGES=5
   ```

2. **Backend Setup**:
   ```bash
   # Create a virtual environment (if not already created)
   python3 -m venv venv

   # Activate the virtual environment
   source venv/bin/activate

   # Install dependencies
   pip install -r backend/requirements.txt

   # Start the FastAPI server
   python3 backend/main.py
   ```
   The backend will run on `http://localhost:8000`.

4. **Local OCR API Setup (Optional)**:
   ```bash
   # Navigate to the OCR API directory
   cd uyghurocr-api

   # Reuse the main venv or create a new one
   # If reusing:
   source ../venv/bin/activate
   pip install -r requirements.txt

   # Start the OCR server (on a different port if needed)
   python3 main.py
   ```
   The local OCR API will run on `http://localhost:8000` (default, consider adjusting if running alongside the main backend).

5. **Frontend Setup**:
   ```bash
   # Install dependencies
   npm install

   # Start the React development server
   npm run dev
   ```
   The frontend will run on `http://localhost:3000`.

## Technology Stack

- **Frontend**: React 19, Vite, Tailwind CSS, Lucide Icons, `@google/genai`.
- **Backend**: Python FastAPI, MongoDB (Motor), PyMuPDF, `numpy`.
- **AI**: Google Gemini (1.5 Flash for OCR and Reasoning).

