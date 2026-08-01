// Yükleme kabul kuralları — backend file_utils.ALLOWED_EXTENSIONS ile hizalı.
// Backend magic-byte doğrulaması asıl kapı; burası sadece kullanıcıya erken uyarı verir.

export const VALID_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "image/tiff",
  "image/jpeg",
  "image/png",
  "application/xml",
  "text/xml",
  "application/zip",
];

// MIME'ı boş/yanlış raporlanan formatlar için uzantı fallback'i (ör. Windows'ta .udf/.tif)
// ".udf.zip": UYAP bazen UDF'i bu adla verir — backend .udf'e normalize eder
// (resolve_upload_suffix + sanitize_filename), diğer .zip'ler kabul edilmez.
export const VALID_EXTENSIONS = [".udf", ".udf.zip", ".tif", ".tiff"];

export const ACCEPT_ATTRIBUTE = ".pdf,.udf,.udf.zip,.doc,.docx,.xls,.xlsx,.tif,.tiff,.jpg,.jpeg,.png";

export function isValidFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return VALID_TYPES.includes(file.type) || VALID_EXTENSIONS.some((ext) => name.endsWith(ext));
}

// --- Sihirbaza özel .eml kabulü ---------------------------------------
// .eml genel beyaz listeye GİRMEZ (davaya belge ekleme / process mail kabul
// etmemeli). Yalnız dava açılış sihirbazının dropzone'u bu sabitleri kullanır;
// dosya backend'te /api/case-intake/expand-eml ile parçalara açılır, kendisi
// listeye girmez.

export const INTAKE_EXTRA_EXTENSIONS = [".eml"];

export const INTAKE_ACCEPT_ATTRIBUTE = ACCEPT_ATTRIBUTE + ",.eml";

export function isEmlFile(file: File): boolean {
  return file.name.toLowerCase().endsWith(".eml");
}

export function isValidIntakeFile(file: File): boolean {
  return isValidFile(file) || isEmlFile(file);
}
