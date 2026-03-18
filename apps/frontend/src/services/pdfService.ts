declare global {
  interface Window {
    ['pdfjs-dist/build/pdf']?: {
      GlobalWorkerOptions: {
        workerSrc: string;
      };
      getDocument: (source: { data: ArrayBuffer }) => { promise: Promise<{ numPages: number; getPage: (pageNumber: number) => Promise<any> }> };
    };
  }
}

const PDF_JS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
const PDF_JS_WORKER_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

let pdfJsLoader: Promise<NonNullable<Window['pdfjs-dist/build/pdf']>> | null = null;

async function loadPdfJs() {
  const existing = window['pdfjs-dist/build/pdf'];
  if (existing) {
    existing.GlobalWorkerOptions.workerSrc = PDF_JS_WORKER_SRC;
    return existing;
  }

  if (!pdfJsLoader) {
    pdfJsLoader = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = PDF_JS_SRC;
      script.async = true;
      script.onload = () => {
        const pdfjsLib = window['pdfjs-dist/build/pdf'];
        if (!pdfjsLib) {
          reject(new Error('PDF.js loaded but did not expose the expected API'));
          return;
        }
        pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_JS_WORKER_SRC;
        resolve(pdfjsLib);
      };
      script.onerror = () => {
        pdfJsLoader = null;
        reject(new Error('Failed to load PDF.js'));
      };
      document.head.appendChild(script);
    });
  }

  return pdfJsLoader;
}

export const getPageCount = async (file: File): Promise<number> => {
  const pdfjsLib = await loadPdfJs();
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  return pdf.numPages;
};

export const generateFileHash = async (file: File): Promise<string> => {
  const arrayBuffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
};

export const convertPageToBase64Image = async (file: File, pageNumber: number): Promise<string> => {
  const pdfjsLib = await loadPdfJs();
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const page = await pdf.getPage(pageNumber);
  
  const viewport = page.getViewport({ scale: 2.0 }); 
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  
  if (!context) throw new Error('Could not create canvas context');
  
  canvas.height = viewport.height;
  canvas.width = viewport.width;
  
  await page.render({
    canvasContext: context,
    viewport: viewport,
  }).promise;
  
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1];
};
