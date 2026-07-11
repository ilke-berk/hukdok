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
export const VALID_EXTENSIONS = [".udf", ".tif", ".tiff"];

export const ACCEPT_ATTRIBUTE = ".pdf,.udf,.doc,.docx,.xls,.xlsx,.tif,.tiff,.jpg,.jpeg,.png";

export function isValidFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return VALID_TYPES.includes(file.type) || VALID_EXTENSIONS.some((ext) => name.endsWith(ext));
}
