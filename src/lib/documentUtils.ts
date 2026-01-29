// PDF text extraction using pdf.js via CDN (to avoid build issues)
export async function extractTextFromPDF(file: File): Promise<string> {
  console.log("extractTextFromPDF: Starting...");
  
  try {
    // Load pdf.js from CDN
    const pdfjsLib = await loadPdfJs();
    console.log("extractTextFromPDF: PDF.js loaded successfully");
    
    const arrayBuffer = await file.arrayBuffer();
    console.log("extractTextFromPDF: ArrayBuffer size:", arrayBuffer.byteLength);
    
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    console.log("extractTextFromPDF: PDF loaded, pages:", pdf.numPages);
    
    let fullText = '';
    
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items
        .map((item: any) => item.str)
        .join(' ');
      fullText += pageText + '\n\n';
      console.log(`extractTextFromPDF: Page ${i} extracted, length:`, pageText.length);
    }
    
    console.log("extractTextFromPDF: Total text length:", fullText.trim().length);
    return fullText.trim();
  } catch (error) {
    console.error("extractTextFromPDF: Error:", error);
    throw error;
  }
}

// Load pdf.js dynamically from CDN to avoid build issues
async function loadPdfJs(): Promise<any> {
  console.log("loadPdfJs: Starting...");
  
  // Check if already loaded
  if ((window as any).pdfjsLib) {
    console.log("loadPdfJs: Already loaded, using cached");
    return (window as any).pdfjsLib;
  }
  
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    
    script.onload = () => {
      console.log("loadPdfJs: Script loaded");
      const pdfjsLib = (window as any).pdfjsLib;
      if (!pdfjsLib) {
        reject(new Error('PDF.js global object not found after script load'));
        return;
      }
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      console.log("loadPdfJs: Worker configured");
      resolve(pdfjsLib);
    };
    
    script.onerror = (e) => {
      console.error("loadPdfJs: Script load error:", e);
      reject(new Error('PDF.js yüklenemedi - CDN erişim hatası'));
    };
    
    document.head.appendChild(script);
    console.log("loadPdfJs: Script tag added to head");
  });
}

export async function extractTextFromFile(file: File): Promise<string> {
  const fileType = file.type;
  console.log("extractTextFromFile: File type:", fileType, "Name:", file.name);
  
  if (fileType === 'application/pdf') {
    return extractTextFromPDF(file);
  }
  
  if (fileType === 'text/plain') {
    return file.text();
  }
  
  // For DOCX files
  if (fileType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    throw new Error('DOCX dosyaları için henüz destek eklenmedi. Lütfen PDF kullanın.');
  }
  
  throw new Error(`Desteklenmeyen dosya formatı: ${fileType}`);
}

export function generateSHA256Hash(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  
  return crypto.subtle.digest('SHA-256', data).then(hashBuffer => {
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
  });
}
